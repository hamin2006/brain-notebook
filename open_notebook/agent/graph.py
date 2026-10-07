"""Agentic notebook chat: a tool-calling research loop over the notebook.

One graph node runs the loop: the model calls tools (list, grep, search, outline,
read, view) until it can answer or the effort budget runs out, then answers with
citations. Only the user's question and the final answer are checkpointed (plus a
compact trace of the steps): tool traffic and viewed images live only inside the
turn, so history stays small.

Progress is emitted through LangGraph's custom stream: {"type": "step"},
{"type": "step_result"} and {"type": "text_delta"} events, consumed by the
streaming chat endpoint.
"""

import asyncio
import json
from datetime import date
from typing import Annotated, Any, Dict, List, Optional

from ai_prompter import Prompter
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from loguru import logger
from typing_extensions import TypedDict

from open_notebook.agent.scope import AgentScope, load_scope
from open_notebook.agent.tools import build_tools
from open_notebook.ai.provision import provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.exceptions import IncompleteGenerationError, OpenNotebookError
from open_notebook.graphs.checkpoint import get_checkpointer
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content

EFFORT_STEPS = {"quick": 4, "standard": 10, "deep": 20}
DEFAULT_EFFORT = "standard"
HISTORY_MESSAGES = 20
MAX_ANSWER_TOKENS = 8192


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    notebook_id: Optional[str]
    # None means "the whole notebook"; a list (even empty) is the user's selection.
    source_ids: Optional[List[str]]
    note_ids: Optional[List[str]]
    model_override: Optional[str]
    effort: Optional[str]


async def notebook_members(notebook_id: str) -> tuple[List[str], List[str]]:
    record = ensure_record_id(notebook_id)
    sources = await repo_query(
        "SELECT VALUE in FROM reference WHERE out = $nb", {"nb": record}
    )
    notes = await repo_query(
        "SELECT VALUE in FROM artifact WHERE out = $nb", {"nb": record}
    )
    return [str(s) for s in sources], [str(n) for n in notes]


async def _notebook_info(notebook_id: Optional[str]) -> Dict[str, Any]:
    if not notebook_id:
        return {}
    rows = await repo_query(
        "SELECT name, description FROM $nb", {"nb": ensure_record_id(notebook_id)}
    )
    return rows[0] if rows else {}


def _call_key(call: ToolCall) -> str:
    return call["name"] + json.dumps(
        call.get("args") or {}, sort_keys=True, default=str
    )


def _first_line(text: str, n: int = 160) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= n else line[:n] + "…"


async def _stream_step(
    llm, messages: List[BaseMessage], writer, step: int
) -> AIMessage:
    """One model call, streaming its text as it is generated."""
    full = None
    async for chunk in llm.astream(messages):
        full = chunk if full is None else full + chunk
        delta = extract_text_content(chunk.content)
        if delta:
            writer({"type": "text_delta", "step": step, "text": delta})
    if full is None:
        return AIMessage(content="")
    message = message_chunk_to_message(full)
    return (
        message
        if isinstance(message, AIMessage)
        else AIMessage(content=extract_text_content(message.content))
    )


async def _run_tools(
    calls: List[ToolCall],
    tools: Dict[str, Any],
    seen: Dict[str, str],
    writer,
    step: int,
) -> List[ToolMessage]:
    async def run(call: ToolCall) -> ToolMessage:
        name, args = call["name"], call.get("args") or {}
        writer({"type": "step", "step": step, "tool": name, "args": args})
        key = _call_key(call)
        if key in seen:
            result = "You already made this exact call; its result is above. Use it or try something different."
        elif name not in tools:
            result = f"Error: no tool named {name}. Available: {', '.join(tools)}."
        else:
            try:
                result = str(await tools[name].ainvoke(args))
            except Exception as e:  # a broken tool call must not end the turn
                logger.warning(f"Agent tool {name} raised: {e}")
                result = f"Error: {name} failed ({type(e).__name__}: {e}). Fix the arguments or try another tool."
            seen[key] = result
        writer(
            {
                "type": "step_result",
                "step": step,
                "tool": name,
                "summary": _first_line(result),
            }
        )
        return ToolMessage(content=result, tool_call_id=call["id"], name=name)

    return list(await asyncio.gather(*(run(c) for c in calls)))


def _image_message(scope: AgentScope) -> Optional[HumanMessage]:
    if not scope.pending_images:
        return None
    images = scope.pending_images[:]
    scope.pending_images.clear()
    content: List[Any] = [
        {
            "type": "text",
            "text": "Images you asked to view: "
            + "; ".join(i["caption"] for i in images),
        }
    ]
    content += [
        {"type": "image_url", "image_url": {"url": i["data_url"]}} for i in images
    ]
    return HumanMessage(content=content)


async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    writer = get_stream_writer()
    try:
        notebook_id = state.get("notebook_id")
        source_ids, note_ids = state.get("source_ids"), state.get("note_ids")
        if notebook_id and (source_ids is None or note_ids is None):
            all_sources, all_notes = await notebook_members(notebook_id)
            source_ids = all_sources if source_ids is None else source_ids
            note_ids = all_notes if note_ids is None else note_ids
        scope = await load_scope(source_ids or [], note_ids or [])
        tool_list = build_tools(scope)
        tools = {t.name: t for t in tool_list}

        effort = state.get("effort") or DEFAULT_EFFORT
        max_steps = EFFORT_STEPS.get(effort, EFFORT_STEPS[DEFAULT_EFFORT])
        info = await _notebook_info(notebook_id)
        system = Prompter(prompt_template="agent/system").render(
            data={
                "notebook_name": info.get("name"),
                "notebook_description": info.get("description"),
                "document_count": len(scope.sources),
                "note_count": len(scope.notes),
                "today": date.today().isoformat(),
                "max_steps": max_steps,
                "strict": True,
            }
        )
        model_id = config.get("configurable", {}).get("model_id") or state.get(
            "model_override"
        )
        model = await provision_langchain_model(
            system, model_id, "chat", max_tokens=MAX_ANSWER_TOKENS
        )
        llm = model.bind_tools(tool_list)

        working: List[BaseMessage] = [SystemMessage(content=system)] + list(
            state["messages"][-HISTORY_MESSAGES:]
        )
        seen: Dict[str, str] = {}
        trace: List[Dict[str, Any]] = []
        answer = ""
        for step in range(1, max_steps + 1):
            message = await _stream_step(llm, working, writer, step)
            working.append(message)
            if not message.tool_calls:
                answer = extract_text_content(message.content)
                break
            results = await _run_tools(message.tool_calls, tools, seen, writer, step)
            working.extend(results)
            trace += [
                {
                    "tool": c["name"],
                    "args": c.get("args") or {},
                    "result": _first_line(str(r.content)),
                }
                for c, r in zip(message.tool_calls, results)
            ]
            image = _image_message(scope)
            if image is not None:
                working.append(image)
        else:
            # Out of budget: answer from what was gathered, without more tools.
            writer(
                {"type": "step", "step": max_steps + 1, "tool": "answer", "args": {}}
            )
            working.append(
                HumanMessage(
                    content="You have used your research budget. Answer now from the evidence above, "
                    "citing addresses, and say briefly what you could not verify."
                )
            )
            final = await _stream_step(
                model.bind_tools(tool_list, tool_choice="none"),
                working,
                writer,
                max_steps + 1,
            )
            answer = extract_text_content(final.content)

        answer = clean_thinking_content(answer).strip()
        if not answer:
            raise IncompleteGenerationError(
                "The model returned an empty answer. Try again, or pick a different model if this keeps happening."
            )
        logger.info(f"Agent answered in {len(trace)} tool call(s) (effort={effort})")
        return {
            "messages": [
                AIMessage(content=answer, additional_kwargs={"agent_trace": trace})
            ]
        }
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder


_graph = None


async def get_agent_graph():
    """The compiled agent graph with the shared async checkpointer."""
    global _graph
    if _graph is None:
        _graph = build_graph().compile(checkpointer=await get_checkpointer())
    return _graph


def reset_agent_graph() -> None:
    """Drop the compiled graph (tests, or after the checkpointer is closed)."""
    global _graph
    _graph = None

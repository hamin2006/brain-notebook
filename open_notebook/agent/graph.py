"""Agentic notebook chat: a tool-calling research loop over the notebook.

One graph node runs the loop: a cheap research model (the default "tools" model)
calls tools (list, grep, search, outline, read, view) until it has enough or the
effort budget runs out, then the writer (the chat model) composes the cited answer
from the gathered evidence in a single call. Only the user's question and the final answer are checkpointed (plus a
compact trace of the steps): tool traffic and viewed images live only inside the
turn, so history stays small.

Progress is emitted through LangGraph's custom stream: {"type": "step"},
{"type": "step_result"} and {"type": "text_delta"} events, consumed by the
streaming chat endpoint.
"""

import asyncio
import json
from datetime import date
from typing import Annotated, Any, Awaitable, Callable, Dict, List, Optional, Tuple

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
from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from loguru import logger
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from open_notebook.agent.addresses import AddressError, parse_address
from open_notebook.agent.scope import AgentScope, ToolError, load_scope
from open_notebook.agent.tools import AddressList, build_tools
from open_notebook.ai.provision import limit_reasoning, provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.exceptions import IncompleteGenerationError, OpenNotebookError
from open_notebook.graphs.checkpoint import get_checkpointer
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content

EFFORT_STEPS = {"quick": 4, "standard": 10, "deep": 20}
REVIEW_ROUNDS = {"deep": 2}  # sufficiency reviews per turn, by effort
SUBAGENT_STEPS = 5
MAX_DELEGATED_DOCUMENTS = 12
MAX_CONCURRENT_SUBAGENTS = 4
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
    llm, messages: List[BaseMessage], writer, step: int, stream_text: bool = True
) -> AIMessage:
    """One model call, streaming its text as it is generated."""
    full = None
    async for chunk in llm.astream(messages):
        full = chunk if full is None else full + chunk
        delta = extract_text_content(chunk.content)
        if delta and stream_text:
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


async def run_loop(
    model,
    tool_list: List[Any],
    scope: AgentScope,
    working: List[BaseMessage],
    max_steps: int,
    writer,
    reviewer: Optional[Callable[[str], Awaitable[List[str]]]] = None,
    review_rounds: int = 0,
    answer_writer: Optional[Callable[[List[BaseMessage], int], Awaitable[str]]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Call tools until the model answers or the budget runs out. Returns (answer, trace).

    With a reviewer, a finished draft is checked; listed gaps send the model back
    to research (at most `review_rounds` times, budget permitting).

    With an answer_writer, the loop model only researches: its closing reply is
    a findings draft, and answer_writer(messages, step) writes the answer from
    the whole transcript. The research model's text is then not streamed.
    """
    tools = {t.name: t for t in tool_list}
    llm = model.bind_tools(tool_list)
    seen: Dict[str, str] = {}
    trace: List[Dict[str, Any]] = []
    reviews = 0
    for step in range(1, max_steps + 1):
        message = await _stream_step(
            llm, working, writer, step, stream_text=answer_writer is None
        )
        working.append(message)
        if not message.tool_calls:
            answer = extract_text_content(message.content)
            if reviewer and reviews < review_rounds and step < max_steps:
                reviews += 1
                writer({"type": "step", "step": step, "tool": "review", "args": {}})
                missing = await reviewer(answer)
                writer(
                    {
                        "type": "step_result",
                        "step": step,
                        "tool": "review",
                        "summary": "; ".join(missing) or "complete",
                    }
                )
                if missing:
                    trace.append(
                        {"tool": "review", "args": {}, "result": "; ".join(missing)}
                    )
                    working.append(
                        HumanMessage(
                            content="A reviewer found gaps in that draft:\n- "
                            + "\n- ".join(missing)
                            + "\nInvestigate them with the tools, then give the complete answer."
                        )
                    )
                    continue
            if answer_writer is not None:
                return await answer_writer(working, step + 1), trace
            return answer, trace
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

    # Out of budget: answer from what was gathered, without more tools.
    if answer_writer is not None:
        working.append(
            HumanMessage(
                content="The research budget is used up; say briefly what could not be verified."
            )
        )
        return await answer_writer(working, max_steps + 1), trace
    writer({"type": "step", "step": max_steps + 1, "tool": "answer", "args": {}})
    working.append(
        HumanMessage(
            content="You have used your research budget. Answer now from the evidence above, "
            "citing addresses, and say briefly what you could not verify."
        )
    )
    try:
        final = await _stream_step(
            model.bind_tools(tool_list, tool_choice="none"),
            working,
            writer,
            max_steps + 1,
        )
    except Exception as e:
        # Some providers reject tool_choice="none"; answer from flattened evidence.
        logger.warning(
            f"Final answer with tool_choice=none failed ({e}); retrying without tools"
        )
        final = await _stream_step(
            model, _flatten_tool_messages(working), writer, max_steps + 1
        )
    return extract_text_content(final.content), trace


def _flatten_tool_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """The conversation with tool calls and results rewritten as plain text.

    For a model call made without tools, where providers reject messages that
    reference tool calls.
    """
    flat: List[BaseMessage] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            flat.append(
                HumanMessage(content=f"[Result of {message.name}]\n{message.content}")
            )
        elif isinstance(message, AIMessage) and message.tool_calls:
            calls = "; ".join(
                f"{c['name']}({json.dumps(c.get('args') or {})})"
                for c in message.tool_calls
            )
            text = extract_text_content(message.content)
            flat.append(
                AIMessage(content=(text + "\n" if text else "") + f"[Called: {calls}]")
            )
        else:
            flat.append(message)
    return flat


WRITE_INSTRUCTION = (
    "Write the final answer to my last question now, using only the evidence gathered above "
    "(tool results and viewed pages). The research notes are a guide; check them against the "
    "evidence. Cite with the addresses exactly as the tools printed them."
)


def make_answer_writer(
    model, system: str, writer
) -> Callable[[List[BaseMessage], int], Awaitable[str]]:
    """The writer step: one streamed call that turns the research transcript into
    the answer, with the answer rules in place of the researcher's instructions."""

    async def write(messages: List[BaseMessage], step: int) -> str:
        writer({"type": "step", "step": step, "tool": "answer", "args": {}})
        transcript = [
            m
            for m in _flatten_tool_messages(messages)
            if not isinstance(m, SystemMessage)
        ]
        prompt = (
            [SystemMessage(content=system)]
            + transcript
            + [HumanMessage(content=WRITE_INSTRUCTION)]
        )
        final = await _stream_step(model, prompt, writer, step)
        answer = extract_text_content(final.content)
        if not clean_thinking_content(answer).strip():
            # A reasoning model can spend the whole output budget thinking over
            # a long transcript; once more, thinking less.
            logger.warning(
                "Answer writer returned nothing; retrying with low reasoning"
            )
            final = await _stream_step(
                limit_reasoning(model, "low"), prompt, writer, step
            )
            answer = extract_text_content(final.content)
        return answer

    return write


async def review_answer(model, question: str, draft: str) -> List[str]:
    """Gaps a reviewer finds in a draft; [] when sufficient or when the review is unreadable.

    An unreadable review means "we did not ask", not "insufficient" (the
    distinction RAGFlow draws with VerdictUnknown), so it never forces a loop.
    """
    prompt = Prompter(prompt_template="agent/review").render(
        data={"question": question, "answer": draft}
    )
    try:
        reply = await model.ainvoke(prompt)
        text = clean_thinking_content(extract_text_content(reply.content))
        verdict = json.loads(text[text.find("{") : text.rfind("}") + 1])
    except Exception as e:
        logger.warning(f"Answer review skipped: {e}")
        return []
    if verdict.get("sufficient", True):
        return []
    return [str(m) for m in verdict.get("missing") or []][:5]


class DelegateArgs(BaseModel):
    task: str = Field(description="What to find out in each document")
    addresses: AddressList = Field(
        description="Document addresses, one sub-agent each (max 12)"
    )


def make_delegate_tool(model, scope: AgentScope, writer) -> StructuredTool:
    """delegate: one quick sub-agent per document, in parallel, each with a fresh context."""

    async def run_one(address: str, task: str, semaphore: asyncio.Semaphore) -> str:
        try:
            source = scope.source(parse_address(address).record_id)
        except (ToolError, AddressError) as e:
            return f"### {address}\nError: {e}"
        sub_scope = AgentScope(sources={source.id: source}, notes={})
        sub_tools = [t for t in build_tools(sub_scope) if t.name not in ("note",)]
        system = Prompter(prompt_template="agent/subagent").render(
            data={"label": source.label, "source_id": source.id, "task": task}
        )
        async with semaphore:
            answer, _ = await run_loop(
                model,
                sub_tools,
                sub_scope,
                [SystemMessage(content=system), HumanMessage(content=task)],
                SUBAGENT_STEPS,
                lambda event: None,  # sub-agent steps stay internal
            )
        return f'### {source.id} "{source.label}"\n{clean_thinking_content(answer).strip()}'

    async def delegate(task: str, addresses: List[str]) -> str:
        if not addresses:
            return "Error: give one or more document addresses."
        targets = list(dict.fromkeys(addresses))[:MAX_DELEGATED_DOCUMENTS]
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SUBAGENTS)
        results = await asyncio.gather(*(run_one(a, task, semaphore) for a in targets))
        return "\n\n".join(results)

    return StructuredTool.from_function(
        coroutine=delegate,
        name="delegate",
        description=(
            "Run the same task on several documents in parallel, one sub-agent each with a fresh context; "
            "returns a short cited answer per document. Use it to compare documents, trace a concept "
            "across many, or collect something from every document."
        ),
        args_schema=DelegateArgs,
    )


async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    writer = get_stream_writer()
    try:
        notebook_id = state.get("notebook_id")
        source_ids, note_ids = state.get("source_ids"), state.get("note_ids")
        if notebook_id and (source_ids is None or note_ids is None):
            all_sources, all_notes = await notebook_members(notebook_id)
            source_ids = all_sources if source_ids is None else source_ids
            note_ids = all_notes if note_ids is None else note_ids
        scope = await load_scope(source_ids or [], note_ids or [], notebook_id)
        tool_list = build_tools(scope)

        effort = state.get("effort") or DEFAULT_EFFORT
        max_steps = EFFORT_STEPS.get(effort, EFFORT_STEPS[DEFAULT_EFFORT])
        info = await _notebook_info(notebook_id)
        prompt_data = {
            "notebook_name": info.get("name"),
            "notebook_description": info.get("description"),
            "document_count": len(scope.sources),
            "note_count": len(scope.notes),
            "today": date.today().isoformat(),
            "max_steps": max_steps,
            "strict": True,
        }
        prompter = Prompter(prompt_template="agent/system")
        system = prompter.render(data={**prompt_data, "researcher": True})
        answer_system = prompter.render(data=prompt_data)
        # The model the user picked writes the answer; the research loop, which
        # makes many calls over a growing transcript, runs on the "tools" model.
        model_id = config.get("configurable", {}).get("model_id") or state.get(
            "model_override"
        )
        answer_model = await provision_langchain_model(
            answer_system, model_id, "chat", max_tokens=MAX_ANSWER_TOKENS
        )
        model = await provision_langchain_model(
            system, None, "tools", max_tokens=MAX_ANSWER_TOKENS
        )

        tool_list = tool_list + [make_delegate_tool(model, scope, writer)]
        working: List[BaseMessage] = [SystemMessage(content=system)] + list(
            state["messages"][-HISTORY_MESSAGES:]
        )
        question = extract_text_content(state["messages"][-1].content)
        reviewer = (
            (lambda draft: review_answer(model, question, draft))
            if REVIEW_ROUNDS.get(effort)
            else None
        )
        answer, trace = await run_loop(
            model,
            tool_list,
            scope,
            working,
            max_steps,
            writer,
            reviewer=reviewer,
            review_rounds=REVIEW_ROUNDS.get(effort, 0),
            answer_writer=make_answer_writer(answer_model, answer_system, writer),
        )

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


_ephemeral_graph = None


def get_ephemeral_agent_graph():
    """The agent graph without a checkpointer, for one-off questions (Ask)."""
    global _ephemeral_graph
    if _ephemeral_graph is None:
        _ephemeral_graph = build_graph().compile()
    return _ephemeral_graph


async def knowledge_base_scope(notebook_ids: List[str]) -> tuple[List[str], List[str]]:
    """Sources and notes of the given notebooks, or of the whole knowledge base."""
    if not notebook_ids:
        sources: List[Any] = await repo_query("SELECT VALUE id FROM source")
        notes: List[Any] = await repo_query("SELECT VALUE id FROM note")
        return [str(s) for s in sources], [str(n) for n in notes]
    source_ids: List[str] = []
    note_ids: List[str] = []
    for notebook_id in notebook_ids:
        sources, notes = await notebook_members(notebook_id)
        source_ids += [s for s in sources if s not in source_ids]
        note_ids += [n for n in notes if n not in note_ids]
    return source_ids, note_ids


def reset_agent_graph() -> None:
    """Drop the compiled graph (tests, or after the checkpointer is closed)."""
    global _graph
    _graph = None

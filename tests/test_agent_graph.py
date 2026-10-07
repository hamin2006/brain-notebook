"""The agent loop: tool calls, streaming events, dedupe, budget, images, errors."""

import json
from typing import Any, List
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from open_notebook.agent.graph import build_graph
from open_notebook.agent.scope import AgentScope, ScopedSource
from open_notebook.exceptions import IncompleteGenerationError


class ScriptedModel:
    """Streams scripted replies; each reply is text and/or tool calls."""

    def __init__(self, replies: List[dict]):
        self.replies = replies
        self.calls: List[List[Any]] = []
        self.tool_choice = None

    def bind_tools(self, tools, tool_choice=None):
        bound = ScriptedModel.__new__(ScriptedModel)
        bound.__dict__ = self.__dict__  # share the script and call log
        bound.tool_choice = tool_choice
        self.last_tool_choice = tool_choice
        return bound

    async def astream(self, messages):
        self.calls.append(list(messages))
        reply = self.replies.pop(0)
        text = reply.get("text", "")
        for piece in [text[: len(text) // 2], text[len(text) // 2 :]] if text else [""]:
            yield AIMessageChunk(content=piece)
        for i, (name, args) in enumerate(reply.get("tools", [])):
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": name,
                        "args": json.dumps(args),
                        "id": f"call_{len(self.calls)}_{i}",
                        "index": i,
                    }
                ],
            )


def _tool(name, fn):
    return StructuredTool.from_function(coroutine=fn, name=name, description=name)


async def _run(model, tools, scope=None, effort="standard"):
    scope = scope or AgentScope(
        sources={"source:l4": ScopedSource("source:l4", "Lecture 4")}, notes={}
    )
    graph = build_graph().compile(checkpointer=InMemorySaver())
    events, final = [], None
    with (
        patch(
            "open_notebook.agent.graph.provision_langchain_model",
            new=AsyncMock(return_value=model),
        ),
        patch(
            "open_notebook.agent.graph.load_scope", new=AsyncMock(return_value=scope)
        ),
        patch("open_notebook.agent.graph.build_tools", return_value=tools),
        patch(
            "open_notebook.agent.graph._notebook_info",
            new=AsyncMock(return_value={"name": "AI 360"}),
        ),
    ):
        async for mode, chunk in graph.astream(  # type: ignore[call-overload]
            {"messages": [HumanMessage(content="What does Adam combine?")], "notebook_id": "notebook:x",
             "source_ids": ["source:l4"], "note_ids": [], "effort": effort},
            {"configurable": {"thread_id": "t1"}},
            stream_mode=["custom", "values"],
        ):  # fmt: skip
            if mode == "custom":
                events.append(chunk)
            else:
                final = chunk
    return events, final


@pytest.mark.asyncio
async def test_searches_then_answers_with_trace_and_events():
    search_calls = []

    async def search(query: str = ""):
        search_calls.append(query)
        return 'Passages (best first):\n- source:l4#p94 "Lecture 4": Adam combines momentum and RMSProp'

    model = ScriptedModel(
        [
            {"tools": [("search", {"query": "Adam"})]},
            {"text": "Adam combines momentum and RMSProp [source:l4#p94]."},
        ]
    )
    events, final = await _run(model, [_tool("search", search)])

    answer = final["messages"][-1]
    assert answer.content == "Adam combines momentum and RMSProp [source:l4#p94]."
    assert answer.additional_kwargs["agent_trace"][0]["tool"] == "search"
    assert search_calls == ["Adam"]
    kinds = [e["type"] for e in events]
    assert kinds[:2] == ["step", "step_result"] and "text_delta" in kinds
    assert (
        "".join(
            e["text"] for e in events if e["type"] == "text_delta" and e["step"] == 2
        )
        == answer.content
    )
    # Tool traffic is not checkpointed: only the question and the answer.
    assert [m.type for m in final["messages"]] == ["human", "ai"]


@pytest.mark.asyncio
async def test_repeated_identical_calls_are_not_rerun():
    runs = []

    async def grep(pattern: str):
        runs.append(pattern)
        return "1 match(es)"

    model = ScriptedModel(
        [
            {"tools": [("grep", {"pattern": "adam"})]},
            {"tools": [("grep", {"pattern": "adam"})]},
            {"text": "Done [source:l4#p94]."},
        ]
    )
    await _run(model, [_tool("grep", grep)])
    assert runs == ["adam"]
    repeat = model.calls[2][-1]
    assert "already made this exact call" in repeat.content


@pytest.mark.asyncio
async def test_budget_exhaustion_forces_an_answer_without_tools():
    async def search(query: str = ""):
        return f"result for {query}"

    model = ScriptedModel(
        [{"tools": [("search", {"query": f"q{i}"})]} for i in range(4)]
        + [{"text": "Best answer so far."}]
    )
    events, final = await _run(model, [_tool("search", search)], effort="quick")
    assert final["messages"][-1].content == "Best answer so far."
    assert model.last_tool_choice == "none"
    assert "used your research budget" in model.calls[-1][-1].content


@pytest.mark.asyncio
async def test_viewed_images_reach_the_next_model_call():
    scope = AgentScope(
        sources={"source:l6": ScopedSource("source:l6", "Lecture 6")}, notes={}
    )

    async def view(address: str):
        scope.pending_images.append(
            {"caption": address, "data_url": "data:image/png;base64,AAAA"}
        )
        return "Showing it."

    model = ScriptedModel(
        [
            {"tools": [("view", {"address": "source:l6#p48"})]},
            {"text": "The 1x1 convolution feeds it [source:l6#p48]."},
        ]
    )
    await _run(model, [_tool("view", view)], scope=scope)
    image_message = model.calls[1][-1]
    assert isinstance(image_message, HumanMessage)
    image_block: Any = image_message.content[1]
    assert image_block["image_url"]["url"].startswith("data:image/png")
    assert scope.pending_images == []


@pytest.mark.asyncio
async def test_empty_answer_raises():
    with pytest.raises(IncompleteGenerationError):
        await _run(ScriptedModel([{"text": ""}]), [])


@pytest.mark.asyncio
async def test_a_failing_tool_becomes_an_error_message():
    async def read(address: str):
        raise RuntimeError("database hiccup")

    model = ScriptedModel(
        [
            {"tools": [("read", {"address": "source:l4#p1"})]},
            {"text": "Could not read it."},
        ]
    )
    _, final = await _run(model, [_tool("read", read)])
    assert final["messages"][-1].content == "Could not read it."
    assert (
        "Error: read failed (RuntimeError: database hiccup)"
        in model.calls[1][-1].content
    )

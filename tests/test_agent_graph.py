"""The agent loop: tool calls, streaming events, dedupe, budget, images, errors,
and the research model / answer writer split."""

import json
from typing import Any, List, Optional
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import (
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from open_notebook.agent.graph import build_graph, run_loop
from open_notebook.agent.scope import AgentScope, ScopedSource
from open_notebook.exceptions import IncompleteGenerationError


class ScriptedModel:
    """Streams scripted replies; each reply is text and/or tool calls."""

    def __init__(self, replies: List[dict], reviews: Optional[List[str]] = None):
        self.replies = replies
        self.reviews = reviews or []
        self.calls: List[List[Any]] = []
        self.tool_choice = None

    async def ainvoke(self, prompt):  # the deep-mode reviewer
        from langchain_core.messages import AIMessage

        return AIMessage(content=self.reviews.pop(0))

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


def _writer(text="The answer [source:l4#p94]."):
    return ScriptedModel([{"text": text}])


async def _run(
    model,
    tools,
    scope=None,
    effort="standard",
    writer=None,
    notebook=None,
    history=None,
):
    """Run the graph with `model` as the research ("tools") model and `writer`
    as the answer ("chat") model."""
    scope = scope or AgentScope(
        sources={"source:l4": ScopedSource("source:l4", "Lecture 4")}, notes={}
    )
    writer = writer or _writer()
    graph = build_graph().compile(checkpointer=InMemorySaver())
    events, final = [], None

    async def provision(content, model_id, default_type, **kwargs):
        return model if default_type == "tools" else writer

    with (
        patch(
            "open_notebook.agent.graph.provision_langchain_model",
            new=AsyncMock(side_effect=provision),
        ),
        patch(
            "open_notebook.agent.graph.load_scope", new=AsyncMock(return_value=scope)
        ),
        patch("open_notebook.agent.graph.build_tools", return_value=tools),
        patch(
            "open_notebook.agent.graph._notebook_info",
            new=AsyncMock(return_value=notebook or {"name": "AI 360"}),
        ),
    ):
        async for mode, chunk in graph.astream(  # type: ignore[call-overload]
            {"messages": (history or []) + [HumanMessage(content="What does Adam combine?")], "notebook_id": "notebook:x",
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
            {"text": "- momentum + RMSProp [source:l4#p94]"},  # research findings
        ]
    )
    writer = _writer("Adam combines momentum and RMSProp [source:l4#p94].")
    events, final = await _run(model, [_tool("search", search)], writer=writer)

    answer = final["messages"][-1]
    assert answer.content == "Adam combines momentum and RMSProp [source:l4#p94]."
    assert answer.additional_kwargs["agent_trace"][0]["tool"] == "search"
    assert search_calls == ["Adam"]
    kinds = [e["type"] for e in events]
    assert kinds[:2] == ["step", "step_result"] and "text_delta" in kinds
    assert {"type": "step", "step": 3, "tool": "answer", "args": {}} in events
    # Only the writer's text is streamed, never the research findings.
    assert "".join(e["text"] for e in events if e["type"] == "text_delta") == (
        answer.content
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
async def test_budget_exhaustion_hands_the_evidence_to_the_writer():
    async def search(query: str = ""):
        return f"result for {query}"

    model = ScriptedModel(
        [{"tools": [("search", {"query": f"q{i}"})]} for i in range(4)]
    )
    writer = _writer("Best answer so far.")
    _, final = await _run(
        model, [_tool("search", search)], effort="quick", writer=writer
    )
    assert final["messages"][-1].content == "Best answer so far."
    assert len(model.calls) == 4  # no extra research call after the budget
    written = writer.calls[0]
    assert any("budget is used up" in str(m.content) for m in written)
    assert any("result for q3" in str(m.content) for m in written)


@pytest.mark.asyncio
async def test_writer_gets_a_flat_transcript_with_the_answer_rules():
    async def search(query: str = ""):
        return "Passages: source:l4#p94 Adam"

    model = ScriptedModel(
        [
            {"tools": [("search", {"query": "Adam"})]},
            {"text": "- found [source:l4#p94]"},
        ]
    )
    writer = _writer()
    await _run(model, [_tool("search", search)], writer=writer)

    research_system = model.calls[0][0]
    assert "Another writer composes the final answer" in research_system.content
    written = writer.calls[0]
    assert isinstance(written[0], SystemMessage)
    assert "# The answer" in written[0].content
    assert "Another writer" not in written[0].content
    assert sum(isinstance(m, SystemMessage) for m in written) == 1
    assert not any(
        isinstance(m, ToolMessage) or getattr(m, "tool_calls", None) for m in written
    )
    assert any("[Result of search]" in str(m.content) for m in written)
    assert "- found [source:l4#p94]" in str(written[-2].content)
    assert "Write the final answer" in written[-1].content


@pytest.mark.asyncio
async def test_empty_writer_reply_is_retried_once():
    model = ScriptedModel([{"text": "- found [source:l4#p94]"}])
    writer = ScriptedModel([{"text": "<think>long</think>"}, {"text": "Answer."}])
    with patch(
        "open_notebook.agent.graph.limit_reasoning", side_effect=lambda m, e: m
    ) as limit:
        _, final = await _run(model, [], writer=writer)
    assert final["messages"][-1].content == "Answer."
    limit.assert_called_once_with(writer, "low")
    assert len(writer.calls) == 2


@pytest.mark.asyncio
async def test_budget_exhaustion_without_a_writer_answers_without_tools():
    async def search(query: str = ""):
        return f"result for {query}"

    model = ScriptedModel(
        [{"tools": [("search", {"query": f"q{i}"})]} for i in range(4)]
        + [{"text": "Best answer so far."}]
    )
    scope = AgentScope(sources={}, notes={})
    answer, _ = await run_loop(
        model,
        [_tool("search", search)],
        scope,
        [HumanMessage(content="q")],
        4,
        lambda e: None,
    )
    assert answer == "Best answer so far."
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
    writer = _writer()
    await _run(model, [_tool("view", view)], scope=scope, writer=writer)
    image_message = model.calls[1][-1]
    assert isinstance(image_message, HumanMessage)
    image_block: Any = image_message.content[1]
    assert image_block["image_url"]["url"].startswith("data:image/png")
    assert scope.pending_images == []
    # The writer sees the viewed page too.
    assert image_message in writer.calls[0]


@pytest.mark.asyncio
async def test_empty_answer_raises():
    with pytest.raises(IncompleteGenerationError):
        await _run(
            ScriptedModel([{"text": "findings"}]),
            [],
            writer=ScriptedModel([{"text": ""}, {"text": ""}]),  # retry is empty too
        )


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
    await _run(model, [_tool("read", read)])
    assert (
        "Error: read failed (RuntimeError: database hiccup)"
        in model.calls[1][-1].content
    )


@pytest.mark.asyncio
async def test_deep_mode_review_sends_the_agent_back_for_gaps():
    reads = []

    async def read(address: str):
        reads.append(address)
        return "--- p94 ---\nAdam: alpha = 0.001, beta1 = 0.9, beta2 = 0.999"

    model = ScriptedModel(
        [
            {"text": "Adam uses momentum."},  # draft 1: incomplete
            {"tools": [("read", {"address": "source:l4#p94"})]},
            {
                "text": "Adam uses alpha = 0.001, beta1 = 0.9, beta2 = 0.999 [source:l4#p94]."
            },
        ],
        reviews=[
            '{"sufficient": false, "missing": ["the default hyperparameters"]}',
            '{"sufficient": true, "missing": []}',
        ],
    )
    events, final = await _run(model, [_tool("read", read)], effort="deep")
    assert final["messages"][-1].content == "The answer [source:l4#p94]."
    assert reads == ["source:l4#p94"]
    gap_prompt = model.calls[1][-1]
    assert "the default hyperparameters" in gap_prompt.content
    assert [
        e["summary"]
        for e in events
        if e.get("tool") == "review" and e["type"] == "step_result"
    ] == [
        "the default hyperparameters",
        "complete",
    ]


@pytest.mark.asyncio
async def test_unreadable_review_does_not_force_another_round():
    model = ScriptedModel([{"text": "Answer [source:l4#p1]."}], reviews=["not json"])
    _, final = await _run(model, [], effort="deep")
    assert final["messages"][-1].content == "The answer [source:l4#p94]."
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_delegate_runs_one_scoped_subagent_per_document():
    from open_notebook.agent.graph import make_delegate_tool

    scope = AgentScope(
        sources={
            "source:l3": ScopedSource("source:l3", "Lecture 3"),
            "source:l4": ScopedSource("source:l4", "Lecture 4"),
        },
        notes={},
    )
    seen_scopes = []

    def fake_build_tools(sub_scope):
        seen_scopes.append(set(sub_scope.sources))
        return []

    model = ScriptedModel(
        [
            {"text": "L3 treats dropout as regularization [source:l3#p123]."},
            {"text": "L4 calls dropout implicit regularization [source:l4#p61]."},
        ]
    )
    with patch("open_notebook.agent.graph.build_tools", side_effect=fake_build_tools):
        tool = make_delegate_tool(model, scope, lambda e: None)
        out = await tool.ainvoke(
            {
                "task": "How is dropout presented?",
                "addresses": ["source:l3", "source:l4", "source:nope"],
            }
        )
    assert seen_scopes == [{"source:l3"}, {"source:l4"}]
    assert '### source:l3 "Lecture 3"' in out and "[source:l4#p61]" in out
    assert "### source:nope\nError:" in out


@pytest.mark.asyncio
async def test_final_answer_falls_back_when_tool_choice_none_is_rejected():
    async def search(query: str = ""):
        return f"result for {query}"

    class PickyModel(ScriptedModel):
        def bind_tools(self, tools, tool_choice=None):
            if tool_choice == "none":
                raise ValueError("tool_choice none not supported")
            return super().bind_tools(tools, tool_choice)

    model = PickyModel(
        [{"tools": [("search", {"query": f"q{i}"})]} for i in range(4)]
        + [{"text": "Answer from evidence."}]
    )
    scope = AgentScope(sources={}, notes={})
    answer, _ = await run_loop(
        model,
        [_tool("search", search)],
        scope,
        [HumanMessage(content="q")],
        4,
        lambda e: None,
    )
    assert answer == "Answer from evidence."
    flattened = model.calls[-1]
    assert not any(getattr(m, "tool_calls", None) for m in flattened)
    assert any("[Result of search]" in str(m.content) for m in flattened)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grounding, rule, instruction",
    [
        (None, "Use only the notebook", "using only the evidence"),
        ("strict", "Use only the notebook", "using only the evidence"),
        ("general", "may add general knowledge", "you may add general knowledge"),
    ],
)
async def test_notebook_grounding_sets_the_answer_rules(grounding, rule, instruction):
    writer = _writer()
    await _run(
        ScriptedModel([{"text": "- findings"}]),
        [],
        writer=writer,
        notebook={"name": "AI 360", "grounding": grounding},
    )
    written = writer.calls[0]
    assert rule in written[0].content
    assert instruction in written[-1].content


def _turns(n):
    from langchain_core.messages import AIMessage

    out: List[Any] = []
    for i in range(n):
        out += [HumanMessage(content=f"question {i}"), AIMessage(content=f"answer {i}")]
    return out


@pytest.mark.asyncio
async def test_old_turns_are_compacted_into_a_summary():
    # 11 earlier turns + the question = 23 messages; 3 fall out of the window.
    model = ScriptedModel([{"text": "- findings"}], reviews=["They asked about Adam."])
    writer = _writer()
    _, final = await _run(model, [], writer=writer, history=_turns(11))

    assert final["summary"] == "They asked about Adam."
    assert final["summarized"] == 3
    written = writer.calls[0]
    assert (
        "# Earlier in this conversation\nThey asked about Adam." in written[0].content
    )
    # The full history stays in the checkpoint for the UI.
    assert len(final["messages"]) == 24


@pytest.mark.asyncio
async def test_short_conversations_are_not_compacted():
    model = ScriptedModel([{"text": "- findings"}])  # no summary reply scripted
    _, final = await _run(model, [], history=_turns(3))
    assert final.get("summary") is None


@pytest.mark.asyncio
async def test_failed_compaction_keeps_the_previous_summary():
    from open_notebook.agent.graph import compact_history

    class Broken:
        async def ainvoke(self, prompt):
            raise RuntimeError("provider down")

    assert await compact_history(Broken(), "old", _turns(1)) == "old"

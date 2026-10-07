"""Streaming agent chat endpoint: SSE event order and scope from the request."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from api.routers.chat import ExecuteChatRequest, _scope_from_request
from open_notebook.agent.graph import AgentState


def _streaming_graph(seen_state: dict):
    async def node(state):
        seen_state.update(state)
        writer = get_stream_writer()
        writer({"type": "step", "step": 1, "tool": "search", "args": {"query": "adam"}})
        writer(
            {"type": "step_result", "step": 1, "tool": "search", "summary": "Passages"}
        )
        writer({"type": "text_delta", "step": 2, "text": "Adam combines "})
        writer({"type": "text_delta", "step": 2, "text": "momentum and RMSProp."})
        trace = [{"tool": "search", "args": {"query": "adam"}, "result": "Passages"}]
        return {
            "messages": AIMessage(
                content="Adam combines momentum and RMSProp.",
                additional_kwargs={"agent_trace": trace},
            )
        }

    builder = StateGraph(AgentState)
    builder.add_node("agent", node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=InMemorySaver())


def test_stream_emits_steps_deltas_answer_complete():
    from fastapi.testclient import TestClient

    from api.main import app

    seen: dict = {}
    graph = _streaming_graph(seen)
    session = MagicMock(model_override=None, save=AsyncMock())
    with (
        patch("api.routers.chat.get_agent_graph", new=AsyncMock(return_value=graph)),
        patch(
            "api.routers.chat.get_session_or_404",
            new=AsyncMock(return_value=("chat_session:s", session)),
        ),
        patch(
            "api.routers.chat.repo_query",
            new=AsyncMock(return_value=[{"out": "notebook:nb"}]),
        ),
    ):
        response = TestClient(app).post(
            "/api/chat/execute/stream",
            json={
                "session_id": "chat_session:s",
                "message": "What is Adam?",
                "context": {},
                "effort": "quick",
            },
        )
    events = [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == [
        "step",
        "step_result",
        "text_delta",
        "text_delta",
        "ai_message",
        "complete",
    ]
    assert events[4]["message"]["trace"][0]["tool"] == "search"
    assert seen["notebook_id"] == "notebook:nb" and seen["effort"] == "quick"
    assert (
        seen["source_ids"] is None
    )  # nothing selected: the agent uses the whole notebook
    session.save.assert_awaited()


def test_scope_from_request_prefers_explicit_ids_then_context():
    explicit = ExecuteChatRequest(
        session_id="s", message="m", context={}, source_ids=["source:a"], note_ids=[]
    )
    assert _scope_from_request(explicit) == (["source:a"], [])
    from_context = ExecuteChatRequest(
        session_id="s",
        message="m",
        context={
            "sources": [{"id": "source:b", "title": "B"}],
            "notes": [{"id": "note:n"}],
        },
    )
    assert _scope_from_request(from_context) == (["source:b"], ["note:n"])
    assert _scope_from_request(
        ExecuteChatRequest(session_id="s", message="m", context={})
    ) == (None, None)


def test_context_is_optional():
    # The chat UI sends only source_ids / note_ids; a required `context` made every
    # turn fail with 422.
    request = ExecuteChatRequest(
        session_id="s", message="m", source_ids=["source:a"], note_ids=[]
    )
    assert request.context == {}
    assert _scope_from_request(request) == (["source:a"], [])

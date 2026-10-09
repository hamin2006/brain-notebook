"""Ask runs the research agent and speaks the Ask page's event format."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from open_notebook.agent.graph import AgentState


def _graph(seen: dict):
    async def node(state):
        seen.update(state)
        writer = get_stream_writer()
        writer({"type": "step", "step": 1, "tool": "search", "args": {"query": "adam"}})
        writer(
            {"type": "step_result", "step": 1, "tool": "search", "summary": "Passages"}
        )
        writer(
            {
                "type": "step",
                "step": 2,
                "tool": "view",
                "args": {"address": "source:l4#p94"},
            }
        )
        return {
            "messages": AIMessage(
                content="Adam combines momentum and RMSProp [source:l4#p94]."
            )
        }

    builder = StateGraph(AgentState)
    builder.add_node("agent", node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile()


@pytest.mark.asyncio
async def test_stream_maps_agent_steps_to_strategy_and_answer():
    from api.routers.search import stream_ask_response

    seen: dict = {}
    model = MagicMock(id="model:chat")
    with (
        patch(
            "open_notebook.agent.graph.get_ephemeral_agent_graph",
            return_value=_graph(seen),
        ),
        patch(
            "open_notebook.agent.graph.knowledge_base_scope",
            new=AsyncMock(return_value=(["source:l4"], ["note:n"])),
        ) as scope,
    ):
        events = [
            json.loads(chunk[len("data: ") :])
            async for chunk in stream_ask_response(
                "What is Adam?", model, model, model, ["notebook:nb"]
            )
        ]

    scope.assert_awaited_once_with(["notebook:nb"])
    assert [e["type"] for e in events] == [
        "strategy",
        "strategy",
        "final_answer",
        "complete",
    ]
    assert events[1]["searches"] == [
        {"term": "adam", "instructions": "search"},
        {"term": "a document p. 94", "instructions": "view"},  # never a record id
    ]
    assert events[2]["content"].endswith("[source:l4#p94].")
    assert seen["source_ids"] == ["source:l4"] and seen["notebook_id"] == "notebook:nb"
    assert seen["model_override"] == "model:chat"

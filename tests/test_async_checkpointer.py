"""The async checkpointer shares the sync SqliteSaver's file and schema."""

import sqlite3
from typing import Annotated

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from open_notebook.graphs.checkpoint import close_checkpointer, get_checkpointer


class State(TypedDict):
    messages: Annotated[list, add_messages]


def _builder():
    def reply(state: State) -> dict:
        return {"messages": AIMessage(content=f"echo {len(state['messages'])}")}

    builder = StateGraph(State)
    builder.add_node("reply", reply)
    builder.add_edge(START, "reply")
    builder.add_edge("reply", END)
    return builder


@pytest_asyncio.fixture
async def checkpoint_file(tmp_path):
    yield str(tmp_path / "checkpoints.sqlite")
    await close_checkpointer()


@pytest.mark.asyncio
async def test_returns_one_shared_instance(checkpoint_file):
    first = await get_checkpointer(checkpoint_file)
    second = await get_checkpointer(checkpoint_file)
    assert first is second


@pytest.mark.asyncio
async def test_reads_threads_written_by_the_sync_saver(checkpoint_file):
    config = {"configurable": {"thread_id": "chat_session:legacy"}}
    sync_graph = _builder().compile(
        checkpointer=SqliteSaver(
            sqlite3.connect(checkpoint_file, check_same_thread=False)
        )
    )
    sync_graph.invoke({"messages": [HumanMessage(content="hi")]}, config)

    async_graph = _builder().compile(
        checkpointer=await get_checkpointer(checkpoint_file)
    )
    state = await async_graph.aget_state(config)
    assert [m.content for m in state.values["messages"]] == ["hi", "echo 1"]

    await async_graph.ainvoke({"messages": [HumanMessage(content="again")]}, config)
    state = await async_graph.aget_state(config)
    assert [m.content for m in state.values["messages"]][-1] == "echo 3"


@pytest.mark.asyncio
async def test_close_allows_reopening(checkpoint_file):
    first = await get_checkpointer(checkpoint_file)
    await close_checkpointer()
    second = await get_checkpointer(checkpoint_file)
    assert first is not second

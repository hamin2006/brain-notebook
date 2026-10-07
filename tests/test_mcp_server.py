"""The MCP server exposes the agent's research tools and `ask`."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from api import mcp_server
from open_notebook.agent.scope import AgentScope, ScopedSource

SCOPE = AgentScope(
    sources={"source:l4": ScopedSource("source:l4", "Lecture 4")},
    notes={},
    notebook_id="notebook:x",
)


def _text(result) -> str:
    content = result[0] if isinstance(result, tuple) else result
    return "\n".join(getattr(c, "text", "") for c in content)


@pytest.mark.asyncio
async def test_tools_are_listed():
    names = {t.name for t in await mcp_server.mcp.list_tools()}
    assert names == {
        "list_notebooks", "ask", "list_documents", "grep", "search",
        "outline", "read", "graph", "view",
    }  # fmt: skip


def test_endpoint_is_mounted_on_the_api():
    from api.main import app

    assert any(getattr(r, "path", None) == "/mcp" for r in app.routes)


@pytest.mark.asyncio
async def test_tool_calls_run_in_the_notebook_scope():
    grep = AsyncMock(return_value="2 match(es)")
    with (
        patch.object(mcp_server, "_scope", new=AsyncMock(return_value=SCOPE)) as scope,
        patch.object(mcp_server.agent_tools, "tool_grep", new=grep),
    ):
        result = await mcp_server.mcp.call_tool(
            "grep", {"pattern": "adam", "notebook": "AI 360"}
        )
    assert _text(result) == "2 match(es)"
    scope.assert_awaited_once_with("AI 360")
    grep.assert_awaited_once_with(SCOPE, pattern="adam", addresses=None)


@pytest.mark.asyncio
async def test_unknown_notebook_names_the_choices():
    rows = [{"id": "notebook:x", "name": "AI 360"}]
    with patch.object(mcp_server, "repo_query", new=AsyncMock(return_value=rows)):
        result = await mcp_server.mcp.call_tool(
            "read", {"address": "source:l4#p1", "notebook": "Biology"}
        )
    assert "No notebook named 'Biology'. Notebooks: 'AI 360'" in _text(result)


@pytest.mark.asyncio
async def test_notebook_names_resolve_case_insensitively():
    rows = [{"id": "notebook:x", "name": "AI 360"}]
    with patch.object(mcp_server, "repo_query", new=AsyncMock(return_value=rows)):
        assert await mcp_server._notebook_id("ai 360 ") == "notebook:x"
        assert await mcp_server._notebook_id("notebook:y") == "notebook:y"
        assert await mcp_server._notebook_id(None) is None


@pytest.mark.asyncio
async def test_view_returns_the_page_image():
    scope = AgentScope(sources=SCOPE.sources, notes={})

    async def fake_view(s, address):
        s.pending_images.append(
            {"caption": address, "data_url": "data:image/png;base64,iVBORw0KGgo="}
        )
        return "Showing source:l4#p3."

    with (
        patch.object(mcp_server, "_scope", new=AsyncMock(return_value=scope)),
        patch.object(mcp_server.agent_tools, "tool_view", new=fake_view),
    ):
        result = await mcp_server.mcp.call_tool("view", {"address": "source:l4#p3"})
    content: Any = result[0] if isinstance(result, tuple) else result
    assert content[0].text == "Showing source:l4#p3."
    assert content[1].type == "image" and content[1].mimeType == "image/png"


@pytest.mark.asyncio
async def test_ask_runs_the_agent():
    from langchain_core.messages import AIMessage

    graph = AsyncMock()
    graph.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content="Adam [source:l4#p94].")]}
    )
    with (
        patch.object(mcp_server, "_notebook_id", new=AsyncMock(return_value="notebook:x")),
        patch("open_notebook.agent.graph.get_ephemeral_agent_graph", return_value=graph),
    ):  # fmt: skip
        result = await mcp_server.mcp.call_tool(
            "ask", {"question": "What does Adam combine?", "notebook": "AI 360"}
        )
    assert "Adam [source:l4#p94]." in _text(result)
    state = graph.ainvoke.await_args.args[0]
    assert state["notebook_id"] == "notebook:x" and state["effort"] == "standard"

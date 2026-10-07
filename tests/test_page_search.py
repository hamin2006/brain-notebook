"""Visual page search: page-image embeddings and search(level="page")."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from open_notebook.agent import retrieval
from open_notebook.agent.scope import AgentScope, ScopedSource, ToolError
from open_notebook.agent.tools import tool_search

SCOPE = AgentScope(
    sources={"source:l6": ScopedSource("source:l6", "Lecture 6")}, notes={}
)


@pytest.mark.asyncio
async def test_page_hits_merge_pages_of_one_build():
    rows = [
        {"source": "source:l6", "page": 47, "text": "Inception", "caption": None, "score": 0.91},
        {"source": "source:l6", "page": 48, "text": "Inception module 1x1", "caption": "diagram", "score": 0.91},
        {"source": "source:l6", "page": 79, "text": "ResNet", "caption": None, "score": 0.52},
    ]  # fmt: skip
    with patch.object(retrieval, "per_source", new=AsyncMock(return_value=rows)):
        hits = await retrieval.page_hits(SCOPE, [0.1], 5)
    assert [(h["page_start"], h["page_end"]) for h in hits] == [(47, 48), (79, 79)]
    assert hits[0]["text"] == "Inception module 1x1"


@pytest.mark.asyncio
async def test_page_search_by_description():
    hits = [
        {"source": "source:l6", "page_start": 47, "page_end": 48, "text": "Inception", "caption": "Inception module diagram", "score": 0.9}
    ]  # fmt: skip
    embed = AsyncMock(return_value=[[0.1, 0.2]])
    with (
        patch.object(
            retrieval, "page_embedding_model", new=AsyncMock(return_value="g")
        ),
        patch.object(retrieval, "page_hits", new=AsyncMock(return_value=hits)),
        patch("open_notebook.ai.openrouter.embed_multimodal", new=embed),
    ):
        out = await tool_search(SCOPE, query="parallel conv branches", level="page")
    assert 'source:l6#p47-48 "Lecture 6": Inception module diagram' in out
    assert embed.await_args.args[1][0]["content"][0]["text"] == "parallel conv branches"


@pytest.mark.asyncio
async def test_page_search_like_excludes_the_page_itself():
    hits = [
        {"source": "source:l6", "page_start": 48, "page_end": 48, "text": "self", "caption": None, "score": 1.0},
        {"source": "source:l6", "page_start": 79, "page_end": 79, "text": "ResNet block", "caption": None, "score": 0.7},
    ]  # fmt: skip
    with (
        patch.object(
            retrieval, "page_embedding_model", new=AsyncMock(return_value="g")
        ),
        patch.object(
            retrieval, "page_image_embedding", new=AsyncMock(return_value=[0.3])
        ),
        patch.object(retrieval, "page_hits", new=AsyncMock(return_value=hits)),
    ):
        out = await tool_search(SCOPE, like="source:l6#p48", level="page")
    assert "- source:l6#p48" not in out and "- source:l6#p79" in out


@pytest.mark.asyncio
async def test_page_search_off_is_a_tool_error():
    with patch.object(
        retrieval, "page_embedding_model", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(ToolError, match="turned off"):
            await tool_search(SCOPE, query="diagram", level="page")


@pytest.mark.asyncio
async def test_embed_pages_renders_each_build_once_and_stores_ranges():
    from commands import page_embedding_commands as cmd

    rows = [
        {"page": 1, "text": "Title slide", "embedded": False},
        {"page": 2, "text": "Bullets: a", "embedded": False},
        {"page": 3, "text": "Bullets: a b", "embedded": False},  # build of p2
        {"page": 4, "text": "Other", "embedded": True},
    ]
    writes = []

    async def fake_query(sql, params=None):
        if sql.startswith("SELECT"):
            return rows
        writes.append((params["a"], params["b"], params["v"]))
        return []

    rendered = []
    with (
        patch.object(
            cmd.AgentSettings,
            "load",
            new=AsyncMock(return_value=SimpleNamespace(page_embedding_model="g")),
        ),
        patch.object(
            cmd.Source,
            "get",
            new=AsyncMock(
                return_value=MagicMock(asset=MagicMock(file_path="/x/l6.pdf"))
            ),
        ),
        patch.object(cmd, "repo_query", new=fake_query),
        patch.object(
            cmd,
            "render_page_png",
            side_effect=lambda path, page, side: rendered.append(page) or b"png",
        ),
        patch.object(
            cmd, "embed_multimodal", new=AsyncMock(return_value=[[1.0], [2.0]])
        ),
    ):
        out = await cmd.embed_pages_command(cmd.EmbedPagesInput(source_id="source:l6"))
    assert rendered == [1, 3]  # p4 is already embedded; p2-3 is one build
    assert writes == [(1, 1, [1.0]), (2, 3, [2.0])]
    assert out.pages_embedded == 3


@pytest.mark.asyncio
async def test_embed_pages_does_nothing_when_off():
    from commands import page_embedding_commands as cmd

    with patch.object(
        cmd.AgentSettings,
        "load",
        new=AsyncMock(return_value=SimpleNamespace(page_embedding_model="")),
    ):
        out = await cmd.embed_pages_command(cmd.EmbedPagesInput(source_id="source:l6"))
    assert out.pages_embedded == 0


@pytest.mark.asyncio
async def test_page_search_by_attached_image():
    scope = AgentScope(
        sources=SCOPE.sources, notes={}, attachments=["data:image/png;base64,BBBB"]
    )
    embed = AsyncMock(return_value=[[0.5]])
    with (
        patch.object(
            retrieval, "page_embedding_model", new=AsyncMock(return_value="g")
        ),
        patch.object(retrieval, "page_hits", new=AsyncMock(return_value=[])),
        patch("open_notebook.ai.openrouter.embed_multimodal", new=embed),
    ):
        await tool_search(scope, image="attachment:1")  # level becomes page
        with pytest.raises(ToolError, match="attached: attachment:1"):
            await tool_search(scope, image="attachment:2")
    item = embed.await_args_list[0].args[1][0]
    assert item["content"][0]["image_url"]["url"] == "data:image/png;base64,BBBB"


def test_chat_request_accepts_only_image_data_urls():
    from pydantic import ValidationError

    from api.routers.chat import ExecuteChatRequest

    base = {"session_id": "s", "message": "m", "context": {}}
    assert ExecuteChatRequest(**base, images=["data:image/png;base64,AA"]).images
    with pytest.raises(ValidationError):
        ExecuteChatRequest(**base, images=["https://example.com/x.png"])
    with pytest.raises(ValidationError):
        ExecuteChatRequest(**base, images=["data:image/png;base64,AA"] * 5)

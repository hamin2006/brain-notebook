"""Optional reranking of search candidates (agentic RAG plan, Phase 5)."""

from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.agent import retrieval

HITS = [{"id": f"h{i}", "content": f"passage {i}"} for i in range(5)]


async def _rerank(query="adam defaults", hits=HITS, limit=3):
    return await retrieval.rerank(query, hits, lambda h: h["content"], limit)


@pytest.mark.asyncio
async def test_rerank_reorders_and_truncates():
    with (
        patch.object(retrieval, "rerank_model", new=AsyncMock(return_value="m")),
        patch(
            "open_notebook.ai.openrouter.rerank",
            new=AsyncMock(return_value=[(3, 0.9), (0, 0.5), (4, 0.1)]),
        ) as call,
    ):
        out = await _rerank()
    assert [h["id"] for h in out] == ["h3", "h0", "h4"]
    call.assert_awaited_once_with("m", "adam defaults", [h["content"] for h in HITS], 3)


@pytest.mark.asyncio
async def test_rerank_off_keeps_the_fused_order():
    with patch.object(retrieval, "rerank_model", new=AsyncMock(return_value=None)):
        out = await _rerank()
    assert [h["id"] for h in out] == ["h0", "h1", "h2"]


@pytest.mark.asyncio
async def test_rerank_failure_keeps_the_fused_order():
    with (
        patch.object(retrieval, "rerank_model", new=AsyncMock(return_value="m")),
        patch(
            "open_notebook.ai.openrouter.rerank",
            new=AsyncMock(side_effect=RuntimeError("503")),
        ),
    ):
        out = await _rerank()
    assert [h["id"] for h in out] == ["h0", "h1", "h2"]


@pytest.mark.asyncio
async def test_like_searches_without_text_are_not_reranked():
    model = AsyncMock(return_value="m")
    with patch.object(retrieval, "rerank_model", new=model):
        out = await _rerank(query="")
    assert len(out) == 3
    model.assert_not_awaited()


@pytest.mark.asyncio
async def test_openrouter_rerank_request_and_response():
    from open_notebook.ai import openrouter

    post = AsyncMock(
        return_value={
            "results": [
                {"index": 1, "relevance_score": 0.8},
                {"index": 0, "relevance_score": 0.2},
            ]
        }
    )
    with patch.object(openrouter, "_post", new=post):
        out = await openrouter.rerank("voyageai/rerank-3-lite", "q", ["a", "b"], 5)
    assert out == [(1, 0.8), (0, 0.2)]
    post.assert_awaited_once_with(
        "/rerank",
        {
            "model": "voyageai/rerank-3-lite",
            "query": "q",
            "documents": ["a", "b"],
            "top_n": 2,
        },
    )


@pytest.mark.asyncio
async def test_openrouter_without_a_key_is_a_configuration_error():
    from open_notebook.ai import openrouter
    from open_notebook.exceptions import ConfigurationError

    with patch.object(openrouter, "get_api_key", new=AsyncMock(return_value=None)):
        with pytest.raises(ConfigurationError):
            await openrouter.rerank("m", "q", ["a"], 1)

"""Vision captions for visual PDF pages."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from commands.page_commands import CaptionPagesInput, caption_pages_command
from open_notebook.graphs.source import SourceState, save_source
from open_notebook.utils.pdf_pages import (
    PdfPage,
    pages_needing_captions,
    render_page_png,
)

SOURCE_ID = "source:deck"


def test_pages_needing_captions_picks_visual_groups_once():
    pages = [
        PdfPage(1, "Title", image_ratio=0.0),
        PdfPage(2, "Momentum", image_ratio=0.6),  # build start...
        PdfPage(3, "Momentum\n- gains speed", image_ratio=0.6),  # ...build end
        PdfPage(4, "", image_ratio=0.9),  # image-only slide
        PdfPage(5, "Text only slide", image_ratio=0.1),
    ]
    assert pages_needing_captions(pages) == [3, 4]


def test_render_page_png(tmp_path):
    path = tmp_path / "deck.pdf"
    Image.new("RGB", (800, 450), "white").save(path, "PDF")
    png = render_page_png(str(path), 1, max_side=400)
    assert png.startswith(b"\x89PNG")
    with pytest.raises(ValueError):
        render_page_png(str(path), 2)


def _fake_source(tmp_path):
    path = tmp_path / "deck.pdf"
    Image.new("RGB", (800, 450), "white").save(
        path, "PDF", save_all=True, append_images=[Image.new("RGB", (800, 450))] * 2
    )
    source = MagicMock(id=SOURCE_ID, title="Lecture 4", vectorize=AsyncMock())
    source.asset.file_path = str(path)
    return source


@pytest.mark.asyncio
async def test_caption_job_captions_visual_pages_and_embeds_once(tmp_path):
    source = _fake_source(tmp_path)
    rows = [
        {"page": 1, "text": "Adam", "image_ratio": 0.9, "caption": None},
        {"page": 2, "text": "Plain text slide", "image_ratio": 0.0, "caption": None},
        {"page": 3, "text": "", "image_ratio": 0.9, "caption": None},
    ]
    updates = []

    async def fake_query(query, params=None):
        if query.startswith("SELECT"):
            return rows
        updates.append(params)
        return []

    replies = {1: "Adam update rule: $m_k = ...$", 3: "NO_VISUAL_CONTENT"}

    async def fake_caption(model, path, title, page):
        return (
            None
            if replies[page.number] == "NO_VISUAL_CONTENT"
            else replies[page.number]
        )

    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch("commands.page_commands.repo_query", new=fake_query),
        patch("commands.page_commands.provision_langchain_model", new=AsyncMock()),
        patch("commands.page_commands._caption_page", new=fake_caption),
        patch("commands.page_commands.submit_command") as submit,
    ):
        result = await caption_pages_command(CaptionPagesInput(source_id=SOURCE_ID))

    assert result.pages_captioned == 1
    assert [u["page"] for u in updates] == [1]
    source.vectorize.assert_awaited_once()
    submit.assert_called_once_with(
        "open_notebook", "analyze_source", {"source_id": SOURCE_ID}
    )


@pytest.mark.asyncio
async def test_caption_job_survives_a_failing_page(tmp_path):
    source = _fake_source(tmp_path)
    rows = [
        {"page": 1, "text": "", "image_ratio": 0.9, "caption": None},
        {"page": 2, "text": "", "image_ratio": 0.9, "caption": None},
    ]

    async def fake_caption(model, path, title, page):
        if page.number == 1:
            raise RuntimeError("image refused")
        return "Diagram of a residual block"

    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch(
            "commands.page_commands.repo_query", new=AsyncMock(side_effect=[rows, []])
        ),
        patch("commands.page_commands.provision_langchain_model", new=AsyncMock()),
        patch("commands.page_commands._caption_page", new=fake_caption),
        patch("commands.page_commands.submit_command") as submit,
    ):
        result = await caption_pages_command(CaptionPagesInput(source_id=SOURCE_ID))

    assert result.success and result.pages_captioned == 1
    source.vectorize.assert_awaited_once()
    submit.assert_called_once()  # analysis still queued after a failed page


@pytest.mark.asyncio
async def test_save_source_queues_captions_instead_of_embedding_for_visual_pdfs():
    source = MagicMock(
        id=SOURCE_ID,
        title="Lecture 4",
        full_text="text",
        vectorize=AsyncMock(),
        save=AsyncMock(),
    )
    state = {
        "content_state": {"file_path": "/tmp/deck.pdf"},
        "extraction": MagicMock(content="--- Page 1 ---\nAdam", title="deck.pdf"),
        "source_id": SOURCE_ID,
        "embed": True,
        "pages": [PdfPage(1, "Adam", image_ratio=0.9)],
    }
    with (
        patch(
            "open_notebook.graphs.source.Source.get", new=AsyncMock(return_value=source)
        ),
        patch("open_notebook.graphs.source._store_pages", new=AsyncMock()) as store,
        patch("open_notebook.graphs.source.submit_command") as submit,
    ):
        await save_source(cast(SourceState, state))

    store.assert_awaited_once()
    submit.assert_called_once_with(
        "open_notebook", "caption_pages", {"source_id": SOURCE_ID, "embed": True}
    )
    source.vectorize.assert_not_awaited()

"""Page-aware ingestion: PDFs keep pages, chunks carry page ranges, and a failed
transformation no longer fails the source."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from commands.embedding_commands import EmbedSourceInput, embed_source_command
from open_notebook.exceptions import IncompleteGenerationError, RateLimitError
from open_notebook.graphs.source import (
    SourceState,
    TransformationState,
    content_process,
    transform_content,
)
from open_notebook.utils.pdf_pages import PdfPage

SOURCE_ID = "source:paged"


class _FakeSource:
    id = SOURCE_ID
    title = "Lecture 4"
    full_text = "--- Page 1 ---\nOptimization"
    asset = None


@pytest.mark.asyncio
async def test_embedding_uses_page_groups_and_records_page_ranges():
    page_rows = [
        {"page": 1, "text": "Optimization", "caption": None},
        {"page": 2, "text": "Momentum\n- heavy ball", "caption": None},
        {"page": 3, "text": "Momentum\n- heavy ball\n- gains speed", "caption": None},
        {"page": 4, "text": "", "caption": "Slide shows the Adam update rule."},
    ]
    inserted: list = []

    async def fake_query(query, params=None):
        return page_rows if query.startswith("SELECT page, text, caption") else []

    async def fake_insert(table, records):
        inserted.extend(records)

    with (
        patch(
            "commands.embedding_commands.Source.get",
            new=AsyncMock(return_value=_FakeSource()),
        ),
        patch("commands.embedding_commands.repo_query", new=fake_query),
        patch("commands.embedding_commands.repo_insert", new=fake_insert),
        patch(
            "commands.embedding_commands.generate_embeddings",
            new=AsyncMock(side_effect=lambda chunks, **_: [[0.1]] * len(chunks)),
        ),
    ):
        await embed_source_command(EmbedSourceInput(source_id=SOURCE_ID))

    assert [(r["page_start"], r["page_end"]) for r in inserted] == [
        (1, 1),
        (2, 3),
        (4, 4),
    ]
    assert inserted[1]["content"].startswith("Lecture 4 — pp. 2–3\n")
    assert "Adam update rule" in inserted[2]["content"]  # caption stands in for text


@pytest.mark.asyncio
async def test_pdf_uses_page_extraction_instead_of_content_core(tmp_path):
    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    pages = [PdfPage(1, "Gradient descent " * 20), PdfPage(2, "Momentum " * 20)]
    state = {"content_state": {"file_path": str(pdf)}}
    with (
        patch("open_notebook.graphs.source.extract_pdf_pages", return_value=pages),
        patch("open_notebook.graphs.source.extract_content", new=AsyncMock()) as cc,
    ):
        result = await content_process(cast(SourceState, state))
    cc.assert_not_awaited()
    assert result["pages"] == pages
    assert result["extraction"].content.startswith("--- Page 1 ---\nGradient descent")
    assert result["extraction"].title == "deck.pdf"


@pytest.mark.asyncio
async def test_scanned_pdf_falls_back_to_content_core(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    extraction = MagicMock(content="OCR text", title="scan.pdf")
    state = {"content_state": {"file_path": str(pdf)}}
    with (
        patch(
            "open_notebook.graphs.source.extract_pdf_pages",
            return_value=[PdfPage(1, "")],
        ),
        patch(
            "open_notebook.graphs.source.extract_content",
            new=AsyncMock(return_value=extraction),
        ),
    ):
        result = await content_process(cast(SourceState, state))
    assert result["extraction"] is extraction
    assert result["pages"] == [PdfPage(1, "")]  # still stored, for viewing and captions


def _transform_state():
    source = MagicMock(id=SOURCE_ID, full_text="text", add_insight=AsyncMock())
    return cast(
        TransformationState,
        {"source": source, "transformation": MagicMock(title="Dense Summary")},
    ), source


@pytest.mark.asyncio
async def test_permanent_generation_failure_does_not_fail_the_source():
    state, source = _transform_state()
    with patch(
        "open_notebook.graphs.source.transform_graph.ainvoke",
        new=AsyncMock(
            side_effect=IncompleteGenerationError(
                "The model reached its generation limit"
            )
        ),
    ):
        assert await transform_content(state) is None
    source.add_insight.assert_not_awaited()


@pytest.mark.asyncio
async def test_transient_generation_failure_still_propagates_for_retry():
    state, _ = _transform_state()
    with patch(
        "open_notebook.graphs.source.transform_graph.ainvoke",
        new=AsyncMock(side_effect=RateLimitError("slow down")),
    ):
        with pytest.raises(RateLimitError):
            await transform_content(state)

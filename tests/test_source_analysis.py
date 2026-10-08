"""Document analysis: outline normalization, section text, and the analyze job."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from commands.analyze_commands import AnalyzeSourceInput, analyze_source_command
from open_notebook.utils.pdf_pages import PageGroup
from open_notebook.utils.sections import (
    PlannedSection,
    Section,
    normalize_sections,
    page_index,
    section_text,
)

GROUPS = [
    PageGroup(1, 1, "Title"),
    PageGroup(2, 5, "Momentum\n- heavy ball"),
    PageGroup(6, 10, "Adam"),
]


def _spans(sections):
    return [(s.page_start, s.page_end, s.title) for s in sections]


def test_normalize_repairs_gaps_overlaps_and_range():
    planned = [
        PlannedSection(title="Optimizers", start_page=2, end_page=7),
        PlannedSection(
            title="Adam", start_page=6, end_page=99
        ),  # overlaps, beyond the end
    ]
    assert _spans(normalize_sections(planned, GROUPS, 10)) == [
        (1, 5, "Optimizers"),  # extended back to page 1
        (6, 10, "Adam"),  # clipped to the document
    ]


def test_normalize_falls_back_to_page_windows():
    sections = normalize_sections([], GROUPS, 10)
    assert sections[0].page_start == 1 and sections[-1].page_end == 10


def test_page_index_and_section_text():
    assert page_index(GROUPS).splitlines()[1] == "pp. 2-5: Momentum"
    text = section_text(GROUPS, Section(index=0, title="t", page_start=2, page_end=10))
    assert text.startswith("[pp. 2-5]\nMomentum") and "[pp. 6-10]\nAdam" in text
    assert "Title" not in text


def _source():
    source = MagicMock(
        id="source:l4", title="AI 360 Lecture 4.pdf", add_insight=AsyncMock()
    )
    source.asset.file_path = None
    return source


@pytest.fixture(autouse=True)
def submitted():
    """Jobs analyze_source submits (page embeddings), instead of a real queue."""
    with patch("commands.analyze_commands.submit_command") as submit:
        yield submit


PAGE_ROWS = [
    {"page": 1, "text": "AI 360 Lecture 4: Losses, Optimizers", "caption": None},
    {"page": 2, "text": "Regularization", "caption": None},
    {"page": 3, "text": "", "caption": "Adam update rule with defaults alpha=0.001"},
]
OUTLINE_JSON = json.dumps(
    {
        "metadata": {"doc_type": "lecture", "title": "Losses"},
        "sections": [{"title": "Losses", "start_page": 1, "end_page": 3}],
    }
)


@pytest.mark.asyncio
async def test_analyze_writes_sections_metadata_and_summary(submitted, stage_writes):
    outline = {
        "metadata": {
            "doc_type": "lecture",
            "title": "Losses, Optimizers",
            "course": "AI 360",
            "sequence": 4,
            "topics": ["Adam"],
        },
        "sections": [
            {"title": "Regularization", "start_page": 1, "end_page": 2},
            {"title": "Optimizers", "start_page": 3, "end_page": 3},
        ],
    }
    replies = iter(
        [json.dumps(outline), "Regularization summary", "Optimizer summary", "Overview"]
    )
    writes: list = []
    summaries: list = []  # (index, summary, jobs queued by then)

    async def fake_query(query, params=None):
        if query.startswith("SELECT page, text, caption"):
            return PAGE_ROWS
        if query.startswith("UPDATE source_section"):
            summaries.append((params["index"], params["summary"], submitted.call_count))
        writes.append((query.split()[0], params))
        return []

    inserted: list = []
    source = _source()
    with (
        patch(
            "commands.analyze_commands.Source.get", new=AsyncMock(return_value=source)
        ),
        patch("commands.analyze_commands.repo_query", new=fake_query),
        patch(
            "commands.analyze_commands.repo_insert",
            new=AsyncMock(side_effect=lambda t, rows: inserted.extend(rows)),
        ),
        patch(
            "commands.analyze_commands._complete",
            new=AsyncMock(side_effect=lambda *a, **k: next(replies)),
        ),
        patch(
            "commands.analyze_commands.generate_embeddings",
            new=AsyncMock(return_value=[[0.1], [0.2]]),
        ),
    ):
        result = await analyze_source_command(AnalyzeSourceInput(source_id="source:l4"))

    assert result.sections == 2
    assert [w[2]["status"] for w in stage_writes if w[1] == "analyze"][-1] == "done"
    assert [c.args for c in submitted.call_args_list] == [
        ("open_notebook", "embed_pages", {"source_id": "source:l4"}),
        ("open_notebook", "extract_concepts", {"source_id": "source:l4"}),
    ]
    # Sections are written first, so page images and concepts start while the
    # summaries are written; the summaries then fill the same rows in place.
    assert [
        (r["title"], r["page_start"], r["page_end"], r["summary"]) for r in inserted
    ] == [("Regularization", 1, 2, ""), ("Optimizers", 3, 3, "")]
    assert summaries == [
        (0, "Regularization summary", 2),
        (1, "Optimizer summary", 2),
    ]
    metadata = next(
        p["metadata"] for verb, p in writes if verb == "UPDATE" and "metadata" in p
    )
    assert (
        metadata["sequence"] == 4
        and metadata["course"] == "AI 360"
        and metadata["page_count"] == 3
    )
    source.add_insight.assert_awaited_once_with("Document Summary", "Overview")


@pytest.mark.asyncio
async def test_analyze_survives_unparseable_outline(stage_writes):
    replies = iter(["not json at all", "summary"])
    inserted: list = []
    with (
        patch(
            "commands.analyze_commands.Source.get",
            new=AsyncMock(return_value=_source()),
        ),
        patch(
            "commands.analyze_commands.repo_query",
            new=AsyncMock(
                side_effect=lambda q, p=None: PAGE_ROWS
                if q.startswith("SELECT")
                else []
            ),
        ),
        patch(
            "commands.analyze_commands.repo_insert",
            new=AsyncMock(side_effect=lambda t, rows: inserted.extend(rows)),
        ),
        patch(
            "commands.analyze_commands._complete",
            new=AsyncMock(side_effect=lambda *a, **k: next(replies, "Overview")),
        ),
        patch(
            "commands.analyze_commands.generate_embeddings",
            new=AsyncMock(return_value=[[0.1]]),
        ),
    ):
        result = await analyze_source_command(AnalyzeSourceInput(source_id="source:l4"))
    assert result.success and result.sections == 1
    assert inserted[0]["page_start"] == 1 and inserted[0]["page_end"] == 3
    # Usable, but recorded as failed so the stage is retried.
    failed = stage_writes[-1][2]
    assert failed["status"] == "failed"
    assert "outline could not be read" in failed["error"]


@pytest.mark.asyncio
async def test_analyze_records_fallback_summaries_as_failed(stage_writes):
    replies = iter([OUTLINE_JSON, "", ""])  # outline, then two empty summaries
    with (
        patch(
            "commands.analyze_commands.Source.get",
            new=AsyncMock(return_value=_source()),
        ),
        patch(
            "commands.analyze_commands.repo_query",
            new=AsyncMock(
                side_effect=lambda q, p=None: PAGE_ROWS
                if q.startswith("SELECT")
                else []
            ),
        ),
        patch("commands.analyze_commands.repo_insert", new=AsyncMock()),
        patch(
            "commands.analyze_commands._complete",
            new=AsyncMock(side_effect=lambda *a, **k: next(replies, "")),
        ),
        patch(
            "commands.analyze_commands.generate_embeddings",
            new=AsyncMock(return_value=[[0.1]]),
        ),
    ):
        result = await analyze_source_command(AnalyzeSourceInput(source_id="source:l4"))
    assert result.success
    failed = stage_writes[-1][2]
    assert failed["status"] == "failed"
    assert "1 of 1 section summaries are plain extracts" in failed["error"]
    assert "document summary" in failed["error"]
    assert failed["detail"]["extract_sections"] == [0]


@pytest.mark.asyncio
async def test_analyze_skips_sources_without_pages():
    with (
        patch(
            "commands.analyze_commands.Source.get",
            new=AsyncMock(return_value=_source()),
        ),
        patch("commands.analyze_commands.repo_query", new=AsyncMock(return_value=[])),
        patch("commands.analyze_commands._complete", new=AsyncMock()) as complete,
    ):
        result = await analyze_source_command(
            AnalyzeSourceInput(source_id="source:web")
        )
    assert result.success and result.sections == 0
    complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_section_summary_is_retried_then_falls_back():
    from commands.analyze_commands import summarize_sections
    from open_notebook.utils.pdf_pages import PdfPage

    pages = [PdfPage(1, "Regularization\naltering optimization"), PdfPage(2, "Dropout")]
    sections = [
        Section(index=0, title="Regularization", page_start=1, page_end=1),
        Section(index=1, title="Dropout", page_start=2, page_end=2),
    ]
    replies = {"Regularization": ["", ""], "Dropout": ["", "Dropout summary"]}

    async def fake_complete(prompt, max_tokens, json_mode=False):
        key = "Regularization" if '"Regularization"' in prompt else "Dropout"
        return replies[key].pop(0)

    with patch("commands.analyze_commands._complete", new=fake_complete):
        summaries = await summarize_sections("Lecture 4", pages, sections)
    assert summaries[1] == "Dropout summary"  # retried with more room
    assert summaries[0].startswith("Regularization (pp. 1-1): ")  # extract fallback
    assert "altering optimization" in summaries[0]

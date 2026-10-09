"""Cheat sheets: recall-item parsing, page budget, layout checks, revision and .tex export."""

import json
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.utils.cheat_sheet import (
    SheetOptions,
    budget_chars,
    build_layout,
    layout_chars,
    markdown_to_tex,
    parse_recall_items,
    pool_lines,
    revision_lines,
    short_ids,
    to_tex,
)

ITEMS: List[Dict[str, Any]] = [
    {"id": "recall_item:a", "source": "source:l5", "kind": "method", "title": "Ratio test", "body": r"$L=\lim|a_{n+1}/a_n|$; $L<1$ converges", "priority": 1, "page_start": 5, "page_end": 5},
    {"id": "recall_item:b", "source": "source:l6", "kind": "method", "title": "Ratio test", "body": r"$L<1$ abs. conv.", "priority": 2, "page_start": 2, "page_end": 3},
    {"id": "recall_item:c", "source": "source:l6", "kind": "formula", "title": "Geometric series", "body": r"$\sum ar^n=\frac{a}{1-r}$", "priority": 3, "page_start": 4, "page_end": 4},
]  # fmt: skip
BY_ID: Dict[str, Dict[str, Any]] = {i["id"]: i for i in ITEMS}
IDS = short_ids(ITEMS)


def test_recall_items_are_cleaned_and_pages_clamped_to_the_section():
    raw = json.dumps(
        {
            "items": [
                {"kind": "Test", "title": " Ratio  test ", "body": r"$L=\lim$", "priority": 9, "page_start": 2, "page_end": 40},
                {"kind": "test", "title": "ratio test", "body": "dup", "priority": 1},
                {"kind": "nonsense", "title": "Series", "body": "a formal sum", "priority": "x"},
                {"kind": "formula", "title": "", "body": "no title"},
            ]
        }
    ).replace(r"\\lim", r"\lim")  # fmt: skip
    items = parse_recall_items(f"```json\n{raw}\n```", 4, 9)
    assert [i["title"] for i in items] == ["Ratio test", "Series"]
    ratio, series = items
    assert ratio["kind"] == "method" and ratio["priority"] == 3
    assert (ratio["page_start"], ratio["page_end"]) == (4, 9)
    assert ratio["body"] == r"$L=\lim$"  # LaTeX survives unescaped JSON
    assert series["kind"] == "definition" and series["priority"] == 2
    assert (series["page_start"], series["page_end"]) == (4, 4)


def test_unreadable_extraction_raises():
    with pytest.raises(ValueError):
        parse_recall_items("I could not find anything.", 1, 3)


def test_budget_grows_with_pages_smaller_type_and_scale():
    two_pages = budget_chars(SheetOptions(pages=2, columns=3))
    assert budget_chars(SheetOptions(pages=1, columns=3)) * 2 == two_pages
    assert budget_chars(SheetOptions(pages=2, columns=4)) > two_pages
    assert budget_chars(SheetOptions(pages=2, columns=2)) < two_pages
    assert budget_chars(SheetOptions(pages=2, columns=3, scale=0.8)) == int(
        two_pages * 0.8
    )


def test_options_keep_known_kinds_in_order():
    assert SheetOptions(kinds=["pitfall", "formula"]).kinds == ["formula", "pitfall"]


def test_pool_lists_items_with_short_ids_and_drops_minor_items_when_tight():
    labels = {"source:l5": "Lecture 5", "source:l6": "Lecture 6"}
    text = pool_lines(ITEMS, IDS, labels)
    assert text.splitlines()[0].startswith("r1 · method · p1 · Ratio test · ")
    assert text.splitlines()[1].endswith("Lecture 6 pp.2-3")
    tight = pool_lines(ITEMS, IDS, labels, max_chars=len(text) - 10)
    assert "Geometric series" not in tight and "r2" in tight


def test_layout_drops_lines_without_known_items_and_cites_from_items():
    raw = json.dumps(
        {
            "title": "Series",
            "topics": [
                {"title": "Tests", "lines": [
                    {"items": ["r1", "r2"], "text": "**Ratio test**: $L<1$ converges"},
                    {"items": ["r99"], "text": "invented"},
                    {"items": [], "text": "no items"},
                ]},
                {"title": "Empty", "lines": [{"items": ["zz"], "text": "x"}]},
            ],
        }
    )  # fmt: skip
    layout = build_layout(raw, IDS, BY_ID, "fallback")
    assert layout["title"] == "Series" and layout["dropped_lines"] == 3
    [topic] = layout["topics"]
    [line] = topic["lines"]
    assert line["id"] == "l1" and topic["id"] == "t1"
    assert line["items"] == ["recall_item:a", "recall_item:b"]
    assert line["cites"] == [
        {"source": "source:l5", "page_start": 5, "page_end": 5},
        {"source": "source:l6", "page_start": 2, "page_end": 3},
    ]
    assert layout_chars(layout) == len("Tests") + len(line["text"])


def test_a_layout_without_cited_lines_is_an_error():
    with pytest.raises(ValueError):
        build_layout(
            '{"topics": [{"title": "T", "lines": [{"text": "x"}]}]}', IDS, BY_ID, "t"
        )


PREVIOUS: Dict[str, Any] = {
    "title": "Series",
    "topics": [
        {"id": "t1", "title": "Tests", "lines": [
            {"id": "l1", "text": "ratio", "items": ["recall_item:a"], "kind": "method", "cites": [{"source": "source:l5", "page_start": 5, "page_end": 5}]},
            {"id": "l2", "text": "my own words", "items": ["recall_item:b"], "kind": "method", "cites": [], "edited": True},
            {"id": "l3", "text": "keep me", "items": ["recall_item:b"], "kind": "method", "cites": [], "pinned": True},
            {"id": "l7", "text": "drop me", "items": ["recall_item:b"], "kind": "method", "cites": []},
        ]},
    ],
}  # fmt: skip


def test_revision_keeps_ids_protects_edited_and_pinned_lines_and_numbers_new_ones():
    raw = json.dumps(
        {
            "topics": [
                {"title": "Tests", "lines": [
                    {"line": "l1", "text": "**Ratio test** shorter"},
                    {"line": "l2", "text": "the model rewrote this"},
                    {"items": ["r3"], "text": "**Geometric**: $\\frac{a}{1-r}$"},
                ]},
            ],
            "comments": [{"id": "c1", "note": "Shortened the ratio test."}],
        }
    )  # fmt: skip
    layout = build_layout(raw, IDS, BY_ID, "fallback", previous=PREVIOUS)
    lines = {line["id"]: line for line in layout["topics"][0]["lines"]}
    assert lines["l1"]["text"] == "**Ratio test** shorter"
    assert lines["l1"]["cites"] == PREVIOUS["topics"][0]["lines"][0]["cites"]
    assert lines["l2"]["text"] == "my own words"  # edited: verbatim
    assert lines["l3"]["text"] == "keep me"  # pinned, left out by the model: put back
    assert "l7" not in lines  # dropped as asked
    assert lines["l8"]["items"] == ["recall_item:c"]  # new ids follow the highest
    assert layout["title"] == "Series"
    assert layout["comment_notes"] == {"c1": "Shortened the ratio test."}


def test_revision_lines_show_ids_flags_and_item_refs():
    text = revision_lines(PREVIOUS, {v: k for k, v in IDS.items()})
    assert text.splitlines()[0] == "## Tests"
    assert "- l2: my own words  <edited; items r2>" in text
    assert "- l3: keep me  <pinned; items r2>" in text


def test_line_text_loses_echoed_ids_and_item_ranges_expand():
    raw = json.dumps(
        {"topics": [{"title": "T", "lines": [
            {"items": "r1-r3", "text": "(items r1, r2, r4) · **Table**: $x$"},
            {"items": ["r2"], "text": "- l9: **Root** $y$  <pinned; items r2>"},
        ]}]}
    )  # fmt: skip
    first, second = build_layout(raw, IDS, BY_ID, "t")["topics"][0]["lines"]
    assert first["text"] == "**Table**: $x$"
    assert first["items"] == ["recall_item:a", "recall_item:b", "recall_item:c"]
    assert second["text"] == "**Root** $y$"


def test_markdown_to_tex_escapes_prose_and_keeps_math():
    out = markdown_to_tex(r"**Ratio test**: $L=\lim_{n} a_n$ & 50% of *cases*")
    assert out == r"\textbf{Ratio test}: $L=\lim_{n} a_n$ \& 50\% of \emph{cases}"


def test_tex_document_has_columns_topics_and_optional_citations():
    layout = build_layout(
        json.dumps({"topics": [{"title": "Tests", "lines": [{"items": ["r1"], "text": "**Ratio**"}]}]}),
        IDS, BY_ID, "Series sheet",
    )  # fmt: skip
    labels = {"source:l5": "Lecture 5"}
    tex = to_tex(layout, SheetOptions(columns=4, paper="a4"), labels)
    assert r"\begin{multicols*}{4}" in tex and "a4paper" in tex
    assert r"\textbf{Ratio}\par" in tex and "Lecture 5" not in tex
    assert "Lecture 5 p.~5" in to_tex(layout, SheetOptions(), labels, citations=True)


# ---------------------------------------------------------------- the job


def _reply(content: str, cost: float = 0.001):
    return SimpleNamespace(
        content=content,
        response_metadata={
            "model_name": "m",
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost},
        },
    )


@pytest.mark.asyncio
async def test_build_composes_from_items_and_records_version_and_cost():
    from commands import cheat_sheet_commands as job

    sheet = {
        "id": "cheat_sheet:s",
        "title": "Series",
        "sources": ["source:l5"],
        "options": {"pages": 1},
        "current_version": None,
    }
    composed = json.dumps(
        {"title": "Series", "topics": [{"title": "Tests", "lines": [{"items": ["r1"], "text": "**Ratio**"}]}]}
    )  # fmt: skip
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=_reply(composed, 0.004)))
    updates = []
    with (
        patch.object(job, "load_sheet", new=AsyncMock(return_value=sheet)),
        patch.object(job, "stale_section_count", new=AsyncMock(return_value=0)),
        patch.object(job, "sheet_items", new=AsyncMock(return_value=ITEMS)),
        patch.object(job, "source_labels", new=AsyncMock(return_value={"source:l5": "L5"})),
        patch.object(job, "provision_langchain_model", new=AsyncMock(return_value=model)),
        patch.object(job, "update_sheet", new=AsyncMock(side_effect=lambda i, f: updates.append(f))),
        patch.object(job, "save_version", new=AsyncMock()) as save,
    ):  # fmt: skip
        number = await job._build(job.BuildCheatSheetInput(sheet_id="cheat_sheet:s"))
    assert number == 1
    _, _, layout = save.call_args.args
    assert layout["topics"][0]["lines"][0]["items"] == ["recall_item:a"]
    final = updates[-1]
    assert final["status"] == "done" and final["current_version"] == 1
    assert final["detail"]["usage"]["cost"] == 0.004
    # Default kinds leave the geometric "formula" item in and nothing else out.
    assert final["detail"]["items"] == 3
    assert [u["status"] for u in updates if "status" in u] == [
        "extracting",
        "composing",
        "done",
    ]


@pytest.mark.asyncio
async def test_build_fails_clearly_when_there_are_no_items():
    from commands import cheat_sheet_commands as job

    sheet: Dict[str, Any] = {"id": "cheat_sheet:s", "title": "S", "sources": ["source:l5"], "options": {}, "current_version": None}  # fmt: skip
    with (
        patch.object(job, "load_sheet", new=AsyncMock(return_value=sheet)),
        patch.object(job, "stale_section_count", new=AsyncMock(return_value=0)),
        patch.object(job, "sheet_items", new=AsyncMock(return_value=[])),
        patch.object(job, "update_sheet", new=AsyncMock()),
    ):  # fmt: skip
        with pytest.raises(ValueError, match="No formulas"):
            await job._build(job.BuildCheatSheetInput(sheet_id="cheat_sheet:s"))


@pytest.mark.asyncio
async def test_a_section_whose_reply_cannot_be_read_is_reported_not_stored():
    from commands import cheat_sheet_commands as job

    model = SimpleNamespace(ainvoke=AsyncMock(return_value=_reply("no json here")))
    section = job.Section(index=2, title="Tests", page_start=1, page_end=3)
    usage = job.Usage()
    assert await job._extract_section(model, "L5", section, "text", usage) is None
    assert model.ainvoke.await_count == 2  # one retry
    assert usage.summary()["models"]["m"]["calls"] == 2

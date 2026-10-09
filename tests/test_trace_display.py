"""Research-trace text names documents and pages, never record ids."""

from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.agent.display import (
    display_step,
    display_trace,
    humanize,
    step_subject,
)

TITLES = {"source:kwj1": "AI 360 - Lecture 6.pdf", "note:n1": "My exam notes"}


def test_addresses_become_titles_with_pages_sections_and_layers():
    assert humanize("source:kwj1#p73-81", TITLES) == "AI 360 - Lecture 6.pdf pp. 73–81"
    assert humanize("Showing source:kwj1#p76. The image follows", TITLES) == (
        "Showing AI 360 - Lecture 6.pdf p. 76. The image follows"
    )
    assert humanize("source:kwj1#s3", TITLES) == "AI 360 - Lecture 6.pdf section 4"
    assert humanize("source:kwj1/summary", TITLES) == "AI 360 - Lecture 6.pdf (summary)"
    assert (
        humanize("[note:n1] and source_insight:x9", TITLES)
        == "[My exam notes] and an insight"
    )
    assert humanize("source:gone#p2", TITLES) == "a document p. 2"
    assert (
        humanize("41 match(es) for /residual/", TITLES) == "41 match(es) for /residual/"
    )


def test_step_subject_follows_the_ui_argument_order():
    assert (
        step_subject({"address": "source:kwj1#p76"}, TITLES)
        == "AI 360 - Lecture 6.pdf p. 76"
    )
    assert (
        step_subject({"query": "skip connection", "source": "source:kwj1"}, TITLES)
        == "skip connection"
    )
    assert step_subject({"sequence": 4}, TITLES) == "#4"
    assert step_subject({}, TITLES) is None


def test_display_step_keeps_raw_args_for_counting():
    step = {
        "tool": "read",
        "args": {"address": "source:kwj1#p73-81"},
        "result": 'source:kwj1#p73-81 "AI 360"',
    }
    shown = display_step(step, TITLES)
    assert shown["args"] == step["args"]
    assert shown["subject"] == "AI 360 - Lecture 6.pdf pp. 73–81"
    assert "source:" not in shown["result"]


@pytest.mark.asyncio
async def test_stored_traces_look_up_titles_once():
    query = AsyncMock(
        return_value=[{"id": "source:kwj1", "title": "AI 360 - Lecture 6.pdf"}]
    )
    with patch("open_notebook.agent.display.repo_query", new=query):
        trace = await display_trace(
            [
                {
                    "tool": "view",
                    "args": {"address": "source:kwj1#p76"},
                    "result": "Showing source:kwj1#p76.",
                },
                {
                    "tool": "grep",
                    "args": {"pattern": "residual"},
                    "result": "41 match(es)",
                },
            ]
        )
    assert query.await_count == 1
    assert trace[0]["subject"] == "AI 360 - Lecture 6.pdf p. 76"
    assert trace[0]["result"] == "Showing AI 360 - Lecture 6.pdf p. 76."
    assert trace[1]["subject"] == "residual"

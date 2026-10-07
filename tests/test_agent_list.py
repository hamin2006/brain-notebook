"""The list tool reports documents that only a doc_type filter hid."""

from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.agent import retrieval
from open_notebook.agent.scope import AgentScope, ScopedSource
from open_notebook.agent.tools import tool_list


def _source(sid, title, doc_type, sequence, pages, course="AI 360"):
    meta = {
        "doc_type": doc_type,
        "course": course,
        "sequence": sequence,
        "page_count": pages,
    }
    return ScopedSource(sid, title, metadata=meta)


SCOPE = AgentScope(
    sources={
        "source:l2": _source("source:l2", "Lecture 2", "slides", 2, 162),
        "source:l3": _source("source:l3", "Lecture 3", "lecture", 3, 132),
        "source:p": _source("source:p", "A paper", "paper", None, 12, course=None),
    },
    notes={},
)
ROWS = [{"id": sid, "summary": ""} for sid in SCOPE.sources]


@pytest.mark.asyncio
async def test_type_filter_mentions_hidden_documents():
    with patch.object(retrieval, "document_rows", new=AsyncMock(return_value=ROWS)):
        out = await tool_list(SCOPE, doc_type="lecture", course="AI 360")
    assert out.startswith("1 document(s):") and "source:l3" in out
    assert (
        "Not shown: 1 otherwise matching document(s) of other types: slides (1)" in out
    )
    assert "source:p" not in out  # excluded by the course filter, not the type


@pytest.mark.asyncio
async def test_no_type_filter_lists_everything_by_pages():
    with patch.object(retrieval, "document_rows", new=AsyncMock(return_value=ROWS)):
        out = await tool_list(SCOPE, sort="pages")
    lines = out.splitlines()
    assert lines[0] == "3 document(s):" and "source:l2" in lines[1]
    assert "Not shown" not in out

"""Section planning for paged sources (outline, metadata, summaries).

The outline step shows the model one line per page group ("pp. 12-15: <first
line>") and asks for document metadata plus topic sections with page ranges.
Models get page ranges subtly wrong (gaps, overlaps, out of range), so
`normalize_sections` turns whatever comes back into contiguous sections that
cover every page, falling back to fixed windows when nothing usable remains.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from open_notebook.utils.pdf_pages import PageGroup

MAX_SECTION_CHARS = 12_000
FALLBACK_GROUPS_PER_SECTION = 8
INDEX_LINE_CHARS = 90


class DocumentMetadata(BaseModel):
    doc_type: str = Field(
        description="One of: lecture (slides or notes for a class session), paper, book, notes, article, report, other"
    )
    title: str = Field(description="Human-readable title, without file extension")
    course: Optional[str] = Field(
        None, description="Course or series name, if the document belongs to one"
    )
    sequence: Optional[int] = Field(
        None,
        description="Number of this document within its series (e.g. 4 for 'Lecture 4'), else null",
    )
    date: Optional[str] = Field(None, description="Date if stated (YYYY-MM-DD or year)")
    authors: List[str] = Field(default_factory=list)
    topics: List[str] = Field(
        default_factory=list, description="Up to 8 main topics, short noun phrases"
    )


class PlannedSection(BaseModel):
    title: str
    start_page: int
    end_page: int


class OutlinePlan(BaseModel):
    metadata: DocumentMetadata
    sections: List[PlannedSection] = Field(
        description="Topic sections in page order covering the whole document"
    )


class Section(BaseModel):
    index: int
    title: str
    page_start: int
    page_end: int


def page_index(groups: List[PageGroup]) -> str:
    """One line per page group for the outline prompt."""
    lines = []
    for group in groups:
        where = (
            f"p. {group.start}"
            if group.start == group.end
            else f"pp. {group.start}-{group.end}"
        )
        first = next(
            (line.strip() for line in group.text.splitlines() if line.strip()),
            "(no text)",
        )
        lines.append(f"{where}: {first[:INDEX_LINE_CHARS]}")
    return "\n".join(lines)


def _fallback_sections(groups: List[PageGroup]) -> List[Section]:
    sections: List[Section] = []
    for i in range(0, len(groups), FALLBACK_GROUPS_PER_SECTION):
        chunk = groups[i : i + FALLBACK_GROUPS_PER_SECTION]
        sections.append(
            Section(
                index=len(sections),
                title=f"Pages {chunk[0].start}-{chunk[-1].end}",
                page_start=chunk[0].start,
                page_end=chunk[-1].end,
            )
        )
    return sections


def normalize_sections(
    planned: List[PlannedSection], groups: List[PageGroup], page_count: int
) -> List[Section]:
    """Contiguous, non-overlapping sections covering pages 1..page_count."""
    if not groups:
        return []
    starts = sorted(
        {
            min(max(s.start_page, 1), page_count): s.title.strip() or "Untitled section"
            for s in planned
            if s.end_page >= s.start_page
        }.items()
    )
    if not starts:
        return _fallback_sections(groups)
    if starts[0][0] != 1:
        starts[0] = (1, starts[0][1])  # extend the first section back to page 1
    sections: List[Section] = []
    for i, (start, title) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else page_count
        sections.append(Section(index=i, title=title, page_start=start, page_end=end))
    return sections


def section_text(groups: List[PageGroup], section: Section) -> str:
    """Text of the page groups inside a section, page-marked and capped."""
    parts = [
        f"[pp. {g.start}-{g.end}]\n{g.text}"
        if g.start != g.end
        else f"[p. {g.start}]\n{g.text}"
        for g in groups
        if g.text.strip() and section.page_start <= g.start <= section.page_end
    ]
    text = "\n\n".join(parts)
    return (
        text if len(text) <= MAX_SECTION_CHARS else text[:MAX_SECTION_CHARS] + "\n[...]"
    )

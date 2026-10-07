"""What one agent turn may read: the notebook's sources and notes the user left in context.

Loaded once per turn and passed to every tool, so tools never reach outside the
user's selection. Also carries images queued by `view` for the next model call.
"""

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from open_notebook.database.repository import ensure_record_id, repo_query

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".gif", ".bmp"}


async def per_source(
    sql: str, source_ids: List[Any], **params: Any
) -> List[Dict[str, Any]]:
    """Run `sql` (filtering on `source = $s`) once per source and concatenate.

    `WHERE source IN $ids` returns no rows on source_page and source_section
    (SurrealDB v2: both have a composite unique index on (source, ...), and the
    planner mishandles IN against it), while equality works. Querying per
    source keeps those lookups correct.
    """
    results = await asyncio.gather(
        *(repo_query(sql, {"s": sid, **params}) for sid in source_ids)
    )
    return [row for rows in results for row in rows]


class ToolError(Exception):
    """A tool call the model can fix by changing its arguments."""


@dataclass
class ScopedSource:
    id: str
    title: str
    file_path: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    page_count: int = 0

    @property
    def kind(self) -> str:
        if self.file_path:
            suffix = Path(self.file_path).suffix.lower()
            if suffix in PDF_SUFFIXES:
                return "pdf"
            if suffix in IMAGE_SUFFIXES:
                return "image"
            return "file"
        return "web" if self.url else "text"

    @property
    def has_original(self) -> bool:
        return bool(self.file_path) and Path(str(self.file_path)).is_file()

    @property
    def label(self) -> str:
        meta = self.metadata or {}
        return meta.get("title") or self.title


@dataclass
class ScopedNote:
    id: str
    title: str


@dataclass
class AgentScope:
    sources: Dict[str, ScopedSource]
    notes: Dict[str, ScopedNote]
    pending_images: List[Dict[str, str]] = field(default_factory=list)
    notebook_id: Optional[str] = None  # where `note` saves
    # Images the user attached to this turn (data URLs), addressed attachment:1..N.
    attachments: List[str] = field(default_factory=list)

    def attachment(self, ref: str) -> str:
        match = re.fullmatch(r"attachment:(\d+)", ref.strip())
        index = int(match.group(1)) if match else 0
        if not 1 <= index <= len(self.attachments):
            available = (
                ", ".join(
                    f"attachment:{i}" for i in range(1, len(self.attachments) + 1)
                )
                or "none"
            )
            raise ToolError(
                f"No image {ref!r} in this message (attached: {available})."
            )
        return self.attachments[index - 1]

    def source(self, record_id: str) -> ScopedSource:
        found = self.sources.get(record_id)
        if not found:
            raise ToolError(
                f"{record_id} is not a source in this notebook's context. "
                "Use list to see the available documents."
            )
        return found

    def note(self, record_id: str) -> ScopedNote:
        found = self.notes.get(record_id)
        if not found:
            raise ToolError(f"{record_id} is not a note in this notebook's context.")
        return found


async def load_scope(
    source_ids: List[str], note_ids: List[str], notebook_id: Optional[str] = None
) -> AgentScope:
    sources: Dict[str, ScopedSource] = {}
    if source_ids:
        ids = [ensure_record_id(s) for s in source_ids]
        rows = await repo_query(
            "SELECT id, title, asset, metadata FROM source WHERE id IN $ids",
            {"ids": ids},
        )
        counts = await per_source(
            "SELECT source, count() AS n FROM source_page WHERE source = $s GROUP BY source",
            ids,
        )
        page_counts = {str(c["source"]): c["n"] for c in counts}
        for row in rows:
            asset = row.get("asset") or {}
            sid = str(row["id"])
            sources[sid] = ScopedSource(
                id=sid,
                title=row.get("title") or "Untitled source",
                file_path=asset.get("file_path"),
                url=asset.get("url"),
                metadata=row.get("metadata") or {},
                page_count=page_counts.get(sid, 0),
            )
    notes: Dict[str, ScopedNote] = {}
    if note_ids:
        rows = await repo_query(
            "SELECT id, title FROM note WHERE id IN $ids",
            {"ids": [ensure_record_id(n) for n in note_ids]},
        )
        notes = {
            str(r["id"]): ScopedNote(str(r["id"]), r.get("title") or "Untitled note")
            for r in rows
        }
    return AgentScope(sources=sources, notes=notes, notebook_id=notebook_id)

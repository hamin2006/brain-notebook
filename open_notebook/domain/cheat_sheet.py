"""Cheat sheet records: sheets, versions, comments and the recall items they draw on.

Plain queries rather than ObjectModel: a sheet's status, detail and versions
are written by the build job and read by the API, and nothing needs the
model layer's embedding hooks. See plans/cheat-sheet.md.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.exceptions import NotFoundError

SHEET_FIELDS = (
    "id, notebook, title, sources, options, status, error, detail, "
    "current_version, created, updated"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _plain(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row)
    for key in ("id", "notebook", "sheet", "source"):
        if key in row and row[key] is not None:
            row[key] = str(row[key])
    if "sources" in row:
        row["sources"] = [str(s) for s in row["sources"] or []]
    return row


async def create_sheet(
    notebook_id: str, title: str, source_ids: List[str], options: Dict[str, Any]
) -> Dict[str, Any]:
    rows = await repo_query(
        "CREATE cheat_sheet CONTENT {notebook: $nb, title: $title, sources: $sources, "
        "options: $options, status: 'queued', detail: {}, created: time::now(), "
        "updated: time::now()} RETURN " + SHEET_FIELDS,
        {
            "nb": ensure_record_id(notebook_id),
            "title": title,
            "sources": [ensure_record_id(s) for s in source_ids],
            "options": options,
        },
    )
    return _plain(rows[0])


async def load_sheet(sheet_id: str) -> Dict[str, Any]:
    rows = await repo_query(
        f"SELECT {SHEET_FIELDS} FROM $id", {"id": ensure_record_id(sheet_id)}
    )
    if not rows:
        raise NotFoundError(f"Cheat sheet {sheet_id} not found")
    return _plain(rows[0])


async def list_sheets(notebook_id: str) -> List[Dict[str, Any]]:
    rows = await repo_query(
        f"SELECT {SHEET_FIELDS} FROM cheat_sheet WHERE notebook = $nb ORDER BY created DESC",
        {"nb": ensure_record_id(notebook_id)},
    )
    return [_plain(r) for r in rows]


async def update_sheet(sheet_id: str, fields: Dict[str, Any]) -> None:
    sets = "".join(f"{k} = ${k}, " for k in fields)
    await repo_query(
        f"UPDATE $id SET {sets}updated = time::now()",
        {"id": ensure_record_id(sheet_id), **fields},
    )


async def delete_sheet(sheet_id: str) -> None:
    await load_sheet(sheet_id)
    await repo_query("DELETE $id", {"id": ensure_record_id(sheet_id)})


async def save_version(sheet_id: str, number: int, layout: Dict[str, Any]) -> None:
    await repo_query(
        "CREATE cheat_sheet_version CONTENT {sheet: $s, number: $n, layout: $layout, "
        "created: time::now()}",
        {"s": ensure_record_id(sheet_id), "n": number, "layout": layout},
    )


async def list_versions(sheet_id: str) -> List[Dict[str, Any]]:
    rows = await repo_query(
        "SELECT number, created FROM cheat_sheet_version WHERE sheet = $s ORDER BY number",
        {"s": ensure_record_id(sheet_id)},
    )
    return rows


async def load_version(sheet_id: str, number: int) -> Dict[str, Any]:
    rows = await repo_query(
        "SELECT id, number, layout, created FROM cheat_sheet_version "
        "WHERE sheet = $s AND number = $n",
        {"s": ensure_record_id(sheet_id), "n": number},
    )
    if not rows:
        raise NotFoundError(f"Version {number} of {sheet_id} not found")
    return _plain(rows[0])


async def update_layout(sheet_id: str, number: int, layout: Dict[str, Any]) -> None:
    """Hand edits and pins change the version in place (no model involved)."""
    await repo_query(
        "UPDATE cheat_sheet_version SET layout = $layout WHERE sheet = $s AND number = $n",
        {"s": ensure_record_id(sheet_id), "n": number, "layout": layout},
    )
    await update_sheet(sheet_id, {})


# ---------------------------------------------------------------- comments


async def list_comments(sheet_id: str) -> List[Dict[str, Any]]:
    rows = await repo_query(
        "SELECT id, sheet, version, line, text, status, note, created "
        "FROM cheat_sheet_comment WHERE sheet = $s ORDER BY created",
        {"s": ensure_record_id(sheet_id)},
    )
    return [_plain(r) for r in rows]


async def add_comment(
    sheet_id: str, version: int, line: Optional[str], text: str
) -> Dict[str, Any]:
    rows = await repo_query(
        "CREATE cheat_sheet_comment CONTENT {sheet: $s, version: $v, line: $line, "
        "text: $text, status: 'open', created: time::now()} "
        "RETURN id, sheet, version, line, text, status, note, created",
        {"s": ensure_record_id(sheet_id), "v": version, "line": line, "text": text},
    )
    return _plain(rows[0])


async def load_comment(sheet_id: str, comment_id: str) -> Dict[str, Any]:
    rows = await repo_query(
        "SELECT id, sheet, version, line, text, status, note, created FROM $id",
        {"id": ensure_record_id(comment_id)},
    )
    if not rows or str(rows[0]["sheet"]) != str(ensure_record_id(sheet_id)):
        raise NotFoundError("Comment not found")
    return _plain(rows[0])


async def update_comment(comment_id: str, fields: Dict[str, Any]) -> None:
    sets = ", ".join(f"{k} = ${k}" for k in fields)
    await repo_query(
        f"UPDATE $id SET {sets}", {"id": ensure_record_id(comment_id), **fields}
    )


async def delete_comment(comment_id: str) -> None:
    await repo_query("DELETE $id", {"id": ensure_record_id(comment_id)})


# ---------------------------------------------------------------- items and sources


async def sheet_items(source_ids: List[str]) -> List[Dict[str, Any]]:
    """Recall items of the sources in the given order, each in section and item order."""
    items: List[Dict[str, Any]] = []
    for sid in source_ids:
        rows = await repo_query(
            "SELECT id, source, section, index, kind, title, body, priority, "
            "page_start, page_end FROM recall_item WHERE source = $s "
            "ORDER BY section, index",
            {"s": ensure_record_id(sid)},
        )
        items += [_plain(r) for r in rows]
    return items


def _short_title(title: str) -> str:
    return re.sub(r"\.(pdf|pptx?|docx?)$", "", title.strip(), flags=re.IGNORECASE)


async def source_labels(source_ids: List[str]) -> Dict[str, str]:
    """Readable names of sources, as the library shows them (the source title,
    else the analyzed title)."""
    labels: Dict[str, str] = {}
    for sid in source_ids:
        rows = await repo_query(
            "SELECT id, title, metadata FROM $id", {"id": ensure_record_id(sid)}
        )
        if rows:
            meta = rows[0].get("metadata") or {}
            labels[str(rows[0]["id"])] = _short_title(
                rows[0].get("title") or meta.get("title") or "Untitled"
            )
    return labels

"""Cheat sheets: create, build, review and export (plans/cheat-sheet.md).

Builds run in the worker (`build_cheat_sheet`); these endpoints create the
sheet, queue builds (compose, Shorten / Add more, Revise), and handle the
review that needs no model: comments, hand edits, pins and the `.tex` export.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel, Field
from surreal_commands import submit_command

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain import cheat_sheet as sheets
from open_notebook.exceptions import InvalidInputError, NotFoundError
from open_notebook.utils.cheat_sheet import Kind, SheetOptions, to_tex

router = APIRouter()

BUILDING = ("queued", "extracting", "composing")
# Shorten and Add more change the budget by these factors.
SHORTEN_FACTOR = 0.8
ADD_MORE_FACTOR = 1.2


class CreateCheatSheetRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    source_ids: Optional[List[str]] = None
    pages: int = Field(2, ge=1, le=2)
    columns: int = Field(3, ge=2, le=4)
    kinds: Optional[List[Kind]] = None
    instructions: str = Field("", max_length=2000)
    paper: str = Field("letter", pattern="^(letter|a4)$")


class UpdateCheatSheetRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)


class ResizeRequest(BaseModel):
    direction: str = Field(pattern="^(shorten|more)$")


class CommentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    line: Optional[str] = Field(None, max_length=20)


class UpdateCommentRequest(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=2000)
    status: Optional[str] = Field(None, pattern="^(open|addressed)$")


class UpdateLineRequest(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=2000)
    pinned: Optional[bool] = None


async def _notebook_sources(notebook_id: str) -> List[Dict[str, Any]]:
    """The notebook's sources in course order (series, then sequence, then title)."""
    rows = await repo_query(
        "SELECT in.id AS id, in.title AS title, in.metadata AS metadata "
        "FROM reference WHERE out = $nb",
        {"nb": ensure_record_id(notebook_id)},
    )

    def order(row: Dict[str, Any]) -> tuple:
        meta = row.get("metadata") or {}
        seq = meta.get("sequence")
        return (
            str(meta.get("course") or ""),
            seq if isinstance(seq, int) else 10**6,
            str(row.get("title") or ""),
        )

    return sorted([{**r, "id": str(r["id"])} for r in rows if r.get("id")], key=order)


def _submit(sheet_id: str, mode: str) -> None:
    import commands.cheat_sheet_commands  # noqa: F401  (registers the command)

    command_id = submit_command(
        "open_notebook", "build_cheat_sheet", {"sheet_id": sheet_id, "mode": mode}
    )
    logger.info(f"Submitted build_cheat_sheet ({mode}) {command_id} for {sheet_id}")


async def _start_build(sheet: Dict[str, Any], mode: str) -> Dict[str, Any]:
    if sheet["status"] in BUILDING:
        raise InvalidInputError("This cheat sheet is already being built")
    await sheets.update_sheet(sheet["id"], {"status": "queued", "error": None})
    _submit(sheet["id"], mode)
    return await sheets.load_sheet(sheet["id"])


async def _current_layout(sheet: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    number = sheet.get("current_version")
    if not number:
        raise InvalidInputError("The cheat sheet has no version yet")
    version = await sheets.load_version(sheet["id"], number)
    return number, version["layout"]


@router.post("/notebooks/{notebook_id}/cheat-sheets")
async def create_cheat_sheet(notebook_id: str, request: CreateCheatSheetRequest):
    notebook = await repo_query(
        "SELECT id, name FROM $id", {"id": ensure_record_id(notebook_id)}
    )
    if not notebook:
        raise NotFoundError("Notebook not found")
    in_notebook = await _notebook_sources(notebook_id)
    known = {s["id"] for s in in_notebook}
    if request.source_ids:
        wanted = {str(ensure_record_id(s)) for s in request.source_ids}
        unknown = wanted - known
        if unknown:
            raise InvalidInputError("Some sources are not in this notebook")
        # Keep course order whatever order the client sent.
        source_ids = [s["id"] for s in in_notebook if s["id"] in wanted]
    else:
        source_ids = [s["id"] for s in in_notebook]
    if not source_ids:
        raise InvalidInputError("Pick at least one document")
    options = SheetOptions(
        pages=request.pages,
        columns=request.columns,
        kinds=request.kinds or SheetOptions().kinds,
        instructions=request.instructions,
        paper=request.paper,  # type: ignore[arg-type]
    )
    title = (
        request.title or ""
    ).strip() or f"{notebook[0].get('name') or 'Course'} cheat sheet"
    sheet = await sheets.create_sheet(
        notebook_id, title, source_ids, options.model_dump()
    )
    _submit(sheet["id"], "compose")
    return sheet


@router.get("/notebooks/{notebook_id}/cheat-sheets")
async def list_cheat_sheets(notebook_id: str):
    return await sheets.list_sheets(notebook_id)


@router.get("/notebooks/{notebook_id}/cheat-sheets/sources")
async def cheat_sheet_sources(notebook_id: str):
    """The notebook's documents in course order, for picking a sheet's sources."""
    return [
        {"id": s["id"], "title": s.get("title") or "Untitled"}
        for s in await _notebook_sources(notebook_id)
    ]


@router.get("/cheat-sheets/{sheet_id}")
async def get_cheat_sheet(sheet_id: str, version: Optional[int] = Query(None)):
    """The sheet with one version's layout (the current one by default), its
    versions, comments and the names of the documents it cites."""
    sheet = await sheets.load_sheet(sheet_id)
    number = version or sheet.get("current_version")
    layout = None
    if number:
        layout = (await sheets.load_version(sheet_id, number))["layout"]
    return {
        **sheet,
        "version": number,
        "layout": layout,
        "versions": await sheets.list_versions(sheet_id),
        "comments": await sheets.list_comments(sheet_id),
        "source_names": await sheets.source_labels(sheet["sources"]),
    }


@router.patch("/cheat-sheets/{sheet_id}")
async def update_cheat_sheet(sheet_id: str, request: UpdateCheatSheetRequest):
    await sheets.load_sheet(sheet_id)
    if request.title is not None:
        await sheets.update_sheet(sheet_id, {"title": request.title.strip()})
    return await sheets.load_sheet(sheet_id)


@router.delete("/cheat-sheets/{sheet_id}")
async def delete_cheat_sheet(sheet_id: str):
    await sheets.delete_sheet(sheet_id)
    return {"deleted": True}


@router.post("/cheat-sheets/{sheet_id}/rebuild")
async def rebuild_cheat_sheet(sheet_id: str):
    """Compose again from the items (a failed build, or new documents processed)."""
    return await _start_build(await sheets.load_sheet(sheet_id), "compose")


@router.post("/cheat-sheets/{sheet_id}/resize")
async def resize_cheat_sheet(sheet_id: str, request: ResizeRequest):
    """Shorten (the sheet overflows) or Add more (room is left): revise the
    current version to a smaller or larger budget."""
    sheet = await sheets.load_sheet(sheet_id)
    options = SheetOptions(**sheet["options"])
    factor = SHORTEN_FACTOR if request.direction == "shorten" else ADD_MORE_FACTOR
    options.scale = round(min(max(options.scale * factor, 0.3), 2.0), 3)
    await sheets.update_sheet(sheet_id, {"options": options.model_dump()})
    sheet["options"] = options.model_dump()
    # A revision of the current version, so pinned and edited lines stay.
    return await _start_build(sheet, request.direction)


@router.post("/cheat-sheets/{sheet_id}/revise")
async def revise_cheat_sheet(sheet_id: str):
    sheet = await sheets.load_sheet(sheet_id)
    await _current_layout(sheet)
    if not any(c["status"] == "open" for c in await sheets.list_comments(sheet_id)):
        raise InvalidInputError("Add a comment to revise the sheet")
    return await _start_build(sheet, "revise")


# ---------------------------------------------------------------- lines


def _find_line(layout: Dict[str, Any], line_id: str) -> Dict[str, Any]:
    for topic in layout.get("topics", []):
        for line in topic["lines"]:
            if line["id"] == line_id:
                return line
    raise NotFoundError("Line not found")


@router.patch("/cheat-sheets/{sheet_id}/lines/{line_id}")
async def update_line(sheet_id: str, line_id: str, request: UpdateLineRequest):
    """Edit a line by hand or pin it; revisions keep edited and pinned lines verbatim."""
    sheet = await sheets.load_sheet(sheet_id)
    if sheet["status"] in BUILDING:
        raise InvalidInputError("Wait for the build to finish")
    number, layout = await _current_layout(sheet)
    line = _find_line(layout, line_id)
    if request.text is not None and request.text.strip() != line["text"]:
        line["text"] = request.text.strip()
        line["edited"] = True
    if request.pinned is not None:
        line["pinned"] = request.pinned
    await sheets.update_layout(sheet_id, number, layout)
    return line


@router.delete("/cheat-sheets/{sheet_id}/lines/{line_id}")
async def delete_line(sheet_id: str, line_id: str):
    sheet = await sheets.load_sheet(sheet_id)
    if sheet["status"] in BUILDING:
        raise InvalidInputError("Wait for the build to finish")
    number, layout = await _current_layout(sheet)
    _find_line(layout, line_id)
    for topic in layout["topics"]:
        topic["lines"] = [x for x in topic["lines"] if x["id"] != line_id]
    layout["topics"] = [t for t in layout["topics"] if t["lines"]]
    await sheets.update_layout(sheet_id, number, layout)
    return {"deleted": True}


# ---------------------------------------------------------------- comments


@router.get("/cheat-sheets/{sheet_id}/comments")
async def list_comments(sheet_id: str):
    await sheets.load_sheet(sheet_id)
    return await sheets.list_comments(sheet_id)


@router.post("/cheat-sheets/{sheet_id}/comments")
async def add_comment(sheet_id: str, request: CommentRequest):
    sheet = await sheets.load_sheet(sheet_id)
    number, layout = await _current_layout(sheet)
    if request.line:
        _find_line(layout, request.line)
    return await sheets.add_comment(
        sheet_id, number, request.line, request.text.strip()
    )


@router.patch("/cheat-sheets/{sheet_id}/comments/{comment_id}")
async def update_comment(sheet_id: str, comment_id: str, request: UpdateCommentRequest):
    comment = await sheets.load_comment(sheet_id, comment_id)
    fields: Dict[str, Any] = {}
    if request.text is not None:
        fields["text"] = request.text.strip()
    if request.status is not None:
        fields["status"] = request.status
    if fields:
        await sheets.update_comment(comment["id"], fields)
    return await sheets.load_comment(sheet_id, comment_id)


@router.delete("/cheat-sheets/{sheet_id}/comments/{comment_id}")
async def delete_comment(sheet_id: str, comment_id: str):
    comment = await sheets.load_comment(sheet_id, comment_id)
    await sheets.delete_comment(comment["id"])
    return {"deleted": True}


# ---------------------------------------------------------------- export


@router.get("/cheat-sheets/{sheet_id}/tex")
async def export_tex(
    sheet_id: str,
    version: Optional[int] = Query(None),
    citations: bool = Query(False),
):
    """The sheet as a standalone LaTeX document, built from the layout."""
    sheet = await sheets.load_sheet(sheet_id)
    number = version or sheet.get("current_version")
    if not number:
        raise InvalidInputError("The cheat sheet has no version yet")
    layout = (await sheets.load_version(sheet_id, number))["layout"]
    labels = await sheets.source_labels(sheet["sources"])
    tex = to_tex(layout, SheetOptions(**sheet["options"]), labels, citations)
    filename = (
        "".join(
            ch if ch.isalnum() or ch in "-_" else "-" for ch in sheet["title"]
        ).strip("-")[:80]
        or "cheat-sheet"
    )
    return Response(
        content=tex,
        media_type="application/x-tex",
        headers={"Content-Disposition": f'attachment; filename="{filename}.tex"'},
    )

"""Cheat sheet jobs: recall-item extraction, composing and revising (plans/cheat-sheet.md).

build_cheat_sheet (one job per build, Shorten / Add more or Revise; the
budget multiplier those set is in the sheet's options):

1. Recall items: every outline section of the sheet's sources whose items are
   missing or from an older RECALL_ITEMS_VERSION is read by the tools model,
   one call per section, and its items replace the section's rows. Items are
   cached across sheets; analysis rewrites the section rows, which clears
   their recall_version, so a new outline is read again.
2. Compose (or revise): the chat model lays the items out as topics and lines
   within the page budget. Lines cite items; citations come from the items.
3. The layout is stored as the sheet's next version.

The sheet row carries the status (queued, extracting, composing, done,
failed), progress, failed sections and the run's tokens and cost.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ai_prompter import Prompter
from langchain_core.output_parsers.pydantic import PydanticOutputParser
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command

from open_notebook.ai.provision import limit_reasoning, provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.cheat_sheet import (
    load_sheet,
    save_version,
    sheet_items,
    source_labels,
    update_sheet,
)
from open_notebook.exceptions import ConfigurationError, NotFoundError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.cheat_sheet import (
    MAX_ITEMS_PER_SECTION,
    ComposedSheet,
    RecallExtraction,
    SheetOptions,
    budget_chars,
    build_layout,
    layout_chars,
    parse_recall_items,
    pool_lines,
    revision_lines,
    short_ids,
    used_items,
)
from open_notebook.utils.pdf_pages import PdfPage, group_builds
from open_notebook.utils.sections import Section, section_text
from open_notebook.utils.text_utils import extract_text_content

# Bump when the extraction prompt or parsing changes what items a section
# yields; sections read with an older version are read again on the next build.
#   1: initial
RECALL_ITEMS_VERSION = 1

CHEAT_SHEET_RETRY_CONFIG = {
    "max_attempts": 2,
    "wait_strategy": "exponential_jitter",
    "wait_min": 2,
    "wait_max": 30,
    "stop_on": [ValueError, ConfigurationError, NotFoundError],
    "retry_log_level": "warning",
}
MAX_CONCURRENT_SECTIONS = int(os.environ.get("OPEN_NOTEBOOK_SECTION_CONCURRENCY", "10"))
# A composed sheet this far over budget is recomposed once with a tighter one.
OVERFLOW_RETRY_RATIO = 1.3


class BuildCheatSheetInput(CommandInput):
    sheet_id: str
    # "compose" builds from the items; "revise" applies open comments to the
    # current version.
    mode: str = "compose"


class BuildCheatSheetOutput(CommandOutput):
    success: bool
    sheet_id: str
    version: Optional[int] = None
    processing_time: float
    error_message: Optional[str] = None


class Usage:
    """Tokens and billed cost of a build, per model (OpenRouter reports cost)."""

    def __init__(self) -> None:
        self.models: Dict[str, Dict[str, float]] = {}

    def add(self, reply: Any) -> None:
        meta = getattr(reply, "response_metadata", None) or {}
        usage = meta.get("token_usage") or {}
        name = str(meta.get("model_name") or "unknown")
        entry = self.models.setdefault(
            name, {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        )
        entry["calls"] += 1
        entry["input"] += usage.get("prompt_tokens") or 0
        entry["output"] += usage.get("completion_tokens") or 0
        entry["cost"] += float(usage.get("cost") or 0)

    def summary(self) -> Dict[str, Any]:
        return {
            "models": self.models,
            "cost": round(sum(m["cost"] for m in self.models.values()), 6),
        }


async def _invoke(model: Any, prompt: str, usage: Usage) -> str:
    reply = await model.ainvoke(prompt)
    usage.add(reply)
    return clean_thinking_content(extract_text_content(reply.content)).strip()


# ---------------------------------------------------------------- 1. recall items


async def _extract_section(
    model: Any, title: str, section: Section, text: str, usage: Usage
) -> Optional[List[Dict[str, Any]]]:
    """The section's recall items, or None when no reply could be read."""
    parser: PydanticOutputParser[RecallExtraction] = PydanticOutputParser(
        pydantic_object=RecallExtraction
    )
    prompt = Prompter(prompt_template="cheat_sheet/recall_items", parser=parser).render(  # type: ignore[arg-type]
        data={
            "title": title,
            "section_title": section.title,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "text": text,
            "max_items": MAX_ITEMS_PER_SECTION,
        }
    )
    error: Exception = ValueError("no attempt")
    for _ in range(2):  # one retry: replies vary
        try:
            raw = await _invoke(model, prompt, usage)
            return parse_recall_items(raw, section.page_start, section.page_end)
        except Exception as e:
            error = e
    logger.warning(f"Recall items failed for section {section.index}: {error}")
    return None


def item_key(source_id: str, section: int, index: int) -> str:
    """Record key of a recall item, one per (source, section, position): a
    re-read section overwrites its rows."""
    return f"{str(source_id).split(':', 1)[-1]}_{section}_{index}"


async def _store_section_items(
    record: Any, section: int, items: List[Dict[str, Any]]
) -> None:
    """Replace a section's items and mark it read, in one transaction."""
    rows = [
        {
            "key": item_key(str(record), section, i),
            "data": {
                **item,
                "source": record,
                "section": section,
                "index": i,
                "version": RECALL_ITEMS_VERSION,
            },
        }
        for i, item in enumerate(items)
    ]
    await repo_query(
        "BEGIN TRANSACTION; "
        "DELETE recall_item WHERE source = $s AND section = $section AND id NOTINSIDE $ids; "
        "FOR $row IN $rows { UPSERT type::thing('recall_item', $row.key) CONTENT $row.data RETURN NONE; }; "
        "UPDATE source_section SET recall_version = $version "
        "WHERE source = $s AND index = $section; "
        "COMMIT TRANSACTION;",
        {
            "s": record,
            "section": section,
            "ids": [ensure_record_id(f"recall_item:{r['key']}") for r in rows],
            "rows": rows,
            "version": RECALL_ITEMS_VERSION,
        },
    )


async def ensure_recall_items(
    source_id: str,
    model: Any,
    semaphore: asyncio.Semaphore,
    usage: Usage,
    on_section_done: Any = None,
) -> Tuple[int, List[int]]:
    """Extract items for the source's sections that have none at the current
    version. Returns (sections read, indexes of sections that failed)."""
    record = ensure_record_id(source_id)
    section_rows = await repo_query(
        "SELECT index, title, page_start, page_end, recall_version FROM source_section "
        "WHERE source = $s ORDER BY index",
        {"s": record},
    )
    # A new outline with fewer sections leaves items of the old ones behind.
    await repo_query(
        "DELETE recall_item WHERE source = $s AND section >= $n",
        {"s": record, "n": len(section_rows)},
    )
    stale = [r for r in section_rows if r.get("recall_version") != RECALL_ITEMS_VERSION]
    if not stale:
        return 0, []
    page_rows = await repo_query(
        "SELECT page, text, caption FROM source_page WHERE source = $s ORDER BY page",
        {"s": record},
    )
    groups = group_builds(
        [
            PdfPage(
                r["page"],
                "\n".join(p for p in (r.get("text"), r.get("caption")) if p),
            )
            for r in page_rows
        ]
    )
    labels = await source_labels([source_id])
    title = labels.get(str(record)) or "Untitled"

    async def one(row: Dict[str, Any]) -> Optional[int]:
        section = Section(
            index=row["index"],
            title=row["title"],
            page_start=row["page_start"],
            page_end=row["page_end"],
        )
        text = section_text(groups, section)
        items: Optional[List[Dict[str, Any]]] = []
        if text.strip():
            async with semaphore:
                items = await _extract_section(model, title, section, text, usage)
        if items is not None:
            await _store_section_items(record, section.index, items)
        if on_section_done:
            await on_section_done()
        return None if items is not None else section.index

    results = await asyncio.gather(*(one(r) for r in stale))
    return len(stale), [i for i in results if i is not None]


async def stale_section_count(source_ids: List[str]) -> int:
    """Sections the next build must read (for progress)."""
    total = 0
    for sid in source_ids:
        rows = await repo_query(
            "SELECT count() AS n FROM source_section WHERE source = $s "
            "AND (recall_version = NONE OR recall_version != $v) GROUP ALL",
            {"s": ensure_record_id(sid), "v": RECALL_ITEMS_VERSION},
        )
        total += rows[0]["n"] if rows else 0
    return total


# ---------------------------------------------------------------- 2. compose


async def _compose(
    sheet: Dict[str, Any],
    options: SheetOptions,
    items: List[Dict[str, Any]],
    labels: Dict[str, str],
    usage: Usage,
    previous: Optional[Dict[str, Any]] = None,
    comments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ids = short_ids(items)
    items_by_id = {str(i["id"]): i for i in items}
    model = limit_reasoning(
        await provision_langchain_model(
            "", None, "chat", max_tokens=16000, structured=dict(type="json")
        ),
        3072,
    )
    parser: PydanticOutputParser[ComposedSheet] = PydanticOutputParser(
        pydantic_object=ComposedSheet
    )

    def prompt_for(budget: int) -> str:
        data: Dict[str, Any] = {
            "title": sheet["title"],
            "pages": options.pages,
            "columns": options.columns,
            "budget": budget,
            "kinds": ", ".join(options.kinds),
            "instructions": options.instructions.strip(),
        }
        if previous is None:
            data["pool"] = pool_lines(items, ids, labels)
            template = "cheat_sheet/compose"
        else:
            unused = [i for i in items if str(i["id"]) not in used_items(previous)]
            data["current"] = revision_lines(previous, {v: k for k, v in ids.items()})
            data["comments"] = comments or []
            data["pool"] = pool_lines(unused, ids, labels)
            template = "cheat_sheet/revise"
        return Prompter(prompt_template=template, parser=parser).render(data=data)  # type: ignore[arg-type]

    async def attempt(budget: int) -> Dict[str, Any]:
        error: Exception = ValueError("no attempt")
        for _ in range(2):  # one retry: replies vary
            try:
                raw = await _invoke(model, prompt_for(budget), usage)
                return build_layout(
                    raw, ids, items_by_id, sheet["title"], previous=previous
                )
            except ValueError as e:
                error = e
        raise ValueError(f"The model's sheet could not be read: {error}")

    budget = budget_chars(options)
    layout = await attempt(budget)
    if layout_chars(layout) > budget * OVERFLOW_RETRY_RATIO:
        logger.info(
            f"Cheat sheet {sheet['id']} composed {layout_chars(layout)} chars for a "
            f"budget of {budget}; recomposing tighter"
        )
        tighter = int(budget * budget / layout_chars(layout))
        layout = await attempt(tighter)
    layout["budget_chars"] = budget
    layout["chars"] = layout_chars(layout)
    return layout


# ---------------------------------------------------------------- the job


@command("build_cheat_sheet", app="open_notebook", retry=CHEAT_SHEET_RETRY_CONFIG)
async def build_cheat_sheet_command(
    input_data: BuildCheatSheetInput,
) -> BuildCheatSheetOutput:
    start = time.time()
    sheet_id = input_data.sheet_id
    try:
        version = await _build(input_data)
        return BuildCheatSheetOutput(
            success=True,
            sheet_id=sheet_id,
            version=version,
            processing_time=time.time() - start,
        )
    except Exception as e:
        logger.error(f"Cheat sheet {sheet_id} failed: {e}")
        try:
            await update_sheet(sheet_id, {"status": "failed", "error": str(e)[:500]})
        except Exception:
            pass
        raise


async def _build(input_data: BuildCheatSheetInput) -> int:
    sheet = await load_sheet(input_data.sheet_id)
    options = SheetOptions(**(sheet.get("options") or {}))
    source_ids = [str(s) for s in sheet["sources"]]
    usage = Usage()
    detail: Dict[str, Any] = {"mode": input_data.mode}
    started = time.time()

    # 1. recall items
    total = await stale_section_count(source_ids)
    detail.update({"sections_total": total, "sections_done": 0})
    await update_sheet(
        input_data.sheet_id, {"status": "extracting", "error": None, "detail": detail}
    )
    failed: List[Dict[str, Any]] = []
    if total:
        model = limit_reasoning(
            await provision_langchain_model(
                "", None, "tools", max_tokens=4096, structured=dict(type="json")
            )
        )
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SECTIONS)
        lock = asyncio.Lock()
        last_write = [0.0]

        async def progress() -> None:
            async with lock:
                detail["sections_done"] += 1
                if time.time() - last_write[0] > 2 or detail["sections_done"] == total:
                    last_write[0] = time.time()
                    await update_sheet(input_data.sheet_id, {"detail": detail})

        results = await asyncio.gather(
            *(
                ensure_recall_items(sid, model, semaphore, usage, progress)
                for sid in source_ids
            )
        )
        for sid, (_, bad) in zip(source_ids, results):
            failed += [{"source": sid, "section": i} for i in bad]
    detail["failed_sections"] = failed
    detail["extract_seconds"] = round(time.time() - started, 1)

    # 2. compose or revise
    items = [i for i in await sheet_items(source_ids) if i["kind"] in options.kinds]
    if not items:
        raise ValueError(
            "No formulas, definitions or other items were found in the selected "
            "documents (have they finished processing?)"
        )
    labels = await source_labels(source_ids)
    await update_sheet(input_data.sheet_id, {"status": "composing", "detail": detail})
    compose_start = time.time()
    previous: Optional[Dict[str, Any]] = None
    comments: List[Dict[str, Any]] = []
    if input_data.mode == "revise":
        previous, comments = await _revision_inputs(sheet)
    layout = await _compose(sheet, options, items, labels, usage, previous, comments)
    detail["compose_seconds"] = round(time.time() - compose_start, 1)

    # 3. store
    number = (sheet.get("current_version") or 0) + 1
    addressed = layout.pop("comment_notes", {})
    await save_version(input_data.sheet_id, number, layout)
    for comment in comments:
        await repo_query(
            "UPDATE $id SET status = 'addressed', note = $note",
            {
                "id": ensure_record_id(comment["id"]),
                "note": (addressed.get(comment["key"]) or "Applied in this version")[
                    :300
                ],
            },
        )
    detail.update(
        {
            "items": len(items),
            "usage": usage.summary(),
            "seconds": round(time.time() - started, 1),
        }
    )
    await update_sheet(
        input_data.sheet_id,
        {"status": "done", "current_version": number, "detail": detail, "error": None},
    )
    logger.info(
        f"Cheat sheet {input_data.sheet_id} v{number}: {layout['chars']} chars "
        f"(budget {layout['budget_chars']}), {len(items)} items, "
        f"{len(failed)} failed sections, ${usage.summary()['cost']:.4f}"
    )
    return number


async def _revision_inputs(
    sheet: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not sheet.get("current_version"):
        raise ValueError("The sheet has no version to revise")
    rows = await repo_query(
        "SELECT layout FROM cheat_sheet_version WHERE sheet = $s AND number = $n",
        {"s": ensure_record_id(sheet["id"]), "n": sheet["current_version"]},
    )
    if not rows:
        raise NotFoundError("The sheet's current version is missing")
    comments = await repo_query(
        "SELECT id, line, text, created FROM cheat_sheet_comment "
        "WHERE sheet = $s AND status = 'open' ORDER BY created",
        {"s": ensure_record_id(sheet["id"])},
    )
    for i, c in enumerate(comments):
        c["key"] = f"c{i + 1}"
    return rows[0]["layout"], comments

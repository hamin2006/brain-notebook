"""Ingestion tracking and versioned reprocessing.

A source goes through background stages, each a worker job:

    extract (process_source) → caption (caption_pages) → embed (embed_source)
                                                       → analyze (analyze_source)
                                                           → page_images (embed_pages)
                                                           → concepts (extract_concepts)

Each stage records its state in `source_stage` (one row per source and stage):
queued / running / done / skipped / failed, with timestamps, the stage version
that produced the current output, an error and a small detail object. The API
reads these rows to show progress; a source is ingested when every stage it
needs is done or skipped.

Stage versions: bump a stage's entry in STAGE_VERSIONS when a change to its
code or prompt should reach sources that were already ingested. When the
worker starts, `plan_reprocessing` finds sources whose recorded version is
older and queues each from its earliest outdated stage; downstream stages
re-run only when that stage's output changed (see caption_pages).
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from surreal_commands import submit_command
from surrealdb import RecordID

from open_notebook.database.repository import ensure_record_id, repo_query

STAGES = ("extract", "caption", "embed", "analyze", "page_images", "concepts")
PAGED_ONLY = {"caption", "analyze", "page_images", "concepts"}

# Version history (bump with a one-line reason):
#   extract 2: page shape counts and garbled-text flags; (cid:N) removed from text
#   caption 2: drawn diagrams and garbled math are captioned; garbled pages get
#              a transcribe-the-math prompt
STAGE_VERSIONS: Dict[str, int] = {
    "extract": 2,
    "caption": 2,
    "embed": 1,
    "analyze": 1,
    "page_images": 1,
    "concepts": 1,
}
# Sources ingested before tracking existed have no rows; their output is
# treated as version 1 of every stage they have.
LEGACY_VERSION = 1

STAGE_COMMANDS: Dict[str, str] = {
    "extract": "process_source",
    "caption": "caption_pages",
    "embed": "embed_source",
    "analyze": "analyze_source",
    "page_images": "embed_pages",
    "concepts": "extract_concepts",
}

FINISHED = ("done", "skipped")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(source_id: str) -> str:
    return str(source_id).split(":", 1)[-1]


def stage_record(source_id: str, stage: str) -> RecordID:
    return RecordID("source_stage", f"{_key(source_id)}_{stage}")


async def _set(source_id: str, stage: str, fields: Dict[str, Any]) -> None:
    try:
        await repo_query(
            "UPSERT $id MERGE $fields",
            {
                "id": stage_record(source_id, stage),
                "fields": {
                    "source": ensure_record_id(source_id),
                    "stage": stage,
                    "updated": _now(),
                    **fields,
                },
            },
        )
    except Exception as e:  # tracking must never fail the work it tracks
        logger.warning(f"Could not record stage {stage} of {source_id}: {e}")


async def stage_queued(source_id: str, stage: str) -> None:
    await _set(
        source_id,
        stage,
        {
            "status": "queued",
            "queued_at": _now(),
            "started_at": None,
            "finished_at": None,
            "error": None,
        },
    )


async def stage_running(source_id: str, stage: str) -> None:
    await _set(
        source_id,
        stage,
        {"status": "running", "started_at": _now(), "finished_at": None, "error": None},
    )


async def stage_done(
    source_id: str,
    stage: str,
    detail: Optional[Dict[str, Any]] = None,
    skipped: bool = False,
) -> None:
    await _set(
        source_id,
        stage,
        {
            "status": "skipped" if skipped else "done",
            "finished_at": _now(),
            "version": STAGE_VERSIONS[stage],
            "detail": detail or {},
            "error": None,
        },
    )


async def stage_failed(source_id: str, stage: str, error: str) -> None:
    await _set(
        source_id,
        stage,
        {"status": "failed", "finished_at": _now(), "error": error[:500]},
    )


class StageRun:
    """What a tracked stage reports: details for the UI, or that it was skipped."""

    def __init__(self) -> None:
        self.detail: Dict[str, Any] = {}
        self.skipped = False

    def skip(self, reason: str) -> None:
        self.skipped = True
        self.detail["reason"] = reason


@asynccontextmanager
async def tracked(source_id: str, stage: str) -> AsyncIterator[StageRun]:
    """Record a stage as running, then done/skipped, or failed on an exception.

    A retried job passes through here again, so a transient failure is
    overwritten by the next attempt's state.
    """
    await stage_running(source_id, stage)
    run = StageRun()
    try:
        yield run
    except BaseException as e:
        await stage_failed(source_id, stage, f"{type(e).__name__}: {e}")
        raise
    await stage_done(source_id, stage, run.detail, skipped=run.skipped)


async def submit_stage(stage: str, source_id: str, **args: Any) -> str:
    """Queue a stage's job for a source and record it as queued."""
    await stage_queued(source_id, stage)
    return str(
        submit_command(
            "open_notebook", STAGE_COMMANDS[stage], {"source_id": source_id, **args}
        )
    )


# --- Status -----------------------------------------------------------------


@dataclass
class StageState:
    stage: str
    status: (
        str  # pending (not reached yet) | queued | running | done | skipped | failed
    )
    version: Optional[int] = None
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


def expected_stages(paged: bool) -> List[str]:
    return [s for s in STAGES if paged or s not in PAGED_ONLY]


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


async def _per_source(sql: str, source_ids: List[str]) -> List[Dict[str, Any]]:
    """Run `sql` (filtering on `source = $s`) per source, a few at a time.

    `WHERE source IN $ids` returns no rows on tables with a composite unique
    index on (source, ...) such as source_page (SurrealDB v2), so lookups
    go one source at a time, as `agent.scope.per_source` does.
    """
    semaphore = asyncio.Semaphore(8)

    async def one(sid: str) -> List[Dict[str, Any]]:
        async with semaphore:
            return await repo_query(sql, {"s": ensure_record_id(sid)})

    results = await asyncio.gather(*(one(sid) for sid in source_ids))
    return [row for rows in results for row in rows]


async def _paged_sources(source_ids: List[str]) -> set:
    rows = await _per_source(
        "SELECT source FROM source_page WHERE source = $s AND page = 1", source_ids
    )
    return {str(r["source"]) for r in rows}


async def ingestion_states(source_ids: List[str]) -> Dict[str, List[StageState]]:
    """Every expected stage of each source, in pipeline order.

    Sources ingested before tracking have no rows: their stages read as done
    (untracked) unless the source is still being processed.
    """
    if not source_ids:
        return {}
    rows = await _per_source("SELECT * FROM source_stage WHERE source = $s", source_ids)
    by_source: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        by_source.setdefault(str(row["source"]), {})[row["stage"]] = row
    paged = await _paged_sources(source_ids)
    states: Dict[str, List[StageState]] = {}
    for sid in source_ids:
        recorded = by_source.get(sid, {})
        is_paged = sid in paged or any(s in PAGED_ONLY for s in recorded)
        result = []
        for stage in expected_stages(is_paged):
            entry = recorded.get(stage)
            if entry is None:
                status = "done" if not recorded else "pending"
                result.append(
                    StageState(stage, status, LEGACY_VERSION if not recorded else None)
                )
                continue
            result.append(
                StageState(
                    stage=stage,
                    status=entry.get("status") or "pending",
                    version=entry.get("version"),
                    queued_at=_iso(entry.get("queued_at")),
                    started_at=_iso(entry.get("started_at")),
                    finished_at=_iso(entry.get("finished_at")),
                    error=entry.get("error"),
                    detail=entry.get("detail"),
                )
            )
        states[sid] = result
    return states


def is_complete(stages: List[StageState]) -> bool:
    return all(s.status in FINISHED for s in stages)


def has_failed(stages: List[StageState]) -> bool:
    return any(s.status == "failed" for s in stages)


# --- Reprocessing -----------------------------------------------------------


def first_outdated(stages: List[StageState]) -> Optional[str]:
    """The earliest stage whose output predates the current version.

    None while any stage is unfinished (queued, running, pending or failed):
    in-progress work is never restarted, and failures are retried explicitly.
    """
    if not is_complete(stages):
        return None
    for state in stages:
        if (state.version or 0) < STAGE_VERSIONS[state.stage]:
            return state.stage
    return None


async def plan_reprocessing() -> Dict[str, str]:
    """Source id → the stage to restart it from, for every outdated source."""
    source_ids = [str(s) for s in await repo_query("SELECT VALUE id FROM source")]
    states = await ingestion_states(source_ids)
    plan = {}
    for sid, stages in states.items():
        stage = first_outdated(stages)
        if stage:
            plan[sid] = stage
    return plan


async def reprocess(source_id: str, stage: str) -> None:
    """Restart a source from `stage` without re-running upstream work.

    Extraction is redone in place by the caption job (`refresh`), which keeps
    the source's text, insights and captions; re-running process_source would
    duplicate insights and repeat content-core extraction.
    """
    if stage in ("extract", "caption"):
        await submit_stage(
            "caption", source_id, refresh=stage == "extract", reprocess=True
        )
    else:
        await submit_stage(stage, source_id)

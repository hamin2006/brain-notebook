"""Ingestion progress: which background stages each source has finished, how
long they took, and what failed (open_notebook/domain/ingestion.py)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from open_notebook.agent.graph import notebook_members
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.ingestion import (
    FINISHED,
    STAGE_VERSIONS,
    StageState,
    has_failed,
    ingestion_states,
    is_complete,
    reprocess,
    restart_point,
    sources_with_live_jobs,
    without_stale_claims,
)
from open_notebook.exceptions import InvalidInputError, NotFoundError

router = APIRouter()


class StageStatus(BaseModel):
    stage: str
    status: str
    version: Optional[int] = None
    current_version: int
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    seconds: Optional[float] = None  # run time (start → finish)
    error: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


class SourceIngestion(BaseModel):
    source_id: str
    title: Optional[str] = None
    complete: bool
    failed: bool
    current_stage: Optional[str] = None  # first stage not finished yet
    stages: List[StageStatus]


class NotebookIngestion(BaseModel):
    complete: bool
    sources: int
    sources_complete: int
    sources_failed: int
    active: Dict[str, int]  # stage → sources currently queued or running it
    items: List[SourceIngestion]


def _seconds(start: Optional[str], end: Optional[str]) -> Optional[float]:
    if not start or not end:
        return None
    try:
        return round(
            (
                datetime.fromisoformat(end) - datetime.fromisoformat(start)
            ).total_seconds(),
            1,
        )
    except ValueError:
        return None


def _source_ingestion(
    source_id: str, title: Optional[str], stages: List[StageState]
) -> SourceIngestion:
    return SourceIngestion(
        source_id=source_id,
        title=title,
        complete=is_complete(stages),
        failed=has_failed(stages),
        current_stage=next((s.stage for s in stages if s.status not in FINISHED), None),
        stages=[
            StageStatus(
                stage=s.stage,
                status=s.status,
                version=s.version,
                current_version=STAGE_VERSIONS[s.stage],
                queued_at=s.queued_at,
                started_at=s.started_at,
                finished_at=s.finished_at,
                seconds=_seconds(s.started_at, s.finished_at),
                error=s.error,
                detail=s.detail,
            )
            for s in stages
        ],
    )


async def _titles(source_ids: List[str]) -> Dict[str, Optional[str]]:
    if not source_ids:
        return {}
    rows = await repo_query(
        "SELECT id, title FROM $records",
        {"records": [ensure_record_id(s) for s in source_ids]},
    )
    return {str(r["id"]): r.get("title") for r in rows}


def _source_record(source_id: str) -> str:
    return source_id if source_id.startswith("source:") else f"source:{source_id}"


@router.get("/sources/{source_id}/ingestion", response_model=SourceIngestion)
async def source_ingestion(source_id: str) -> SourceIngestion:
    source_id = _source_record(source_id)
    titles = await _titles([source_id])
    if source_id not in titles:
        raise NotFoundError("Source not found")
    states = await ingestion_states([source_id])
    return _source_ingestion(source_id, titles[source_id], states[source_id])


@router.get("/notebooks/{notebook_id}/ingestion", response_model=NotebookIngestion)
async def notebook_ingestion(notebook_id: str) -> NotebookIngestion:
    found = await repo_query(
        "SELECT VALUE id FROM $nb", {"nb": ensure_record_id(notebook_id)}
    )
    if not found:
        raise NotFoundError("Notebook not found")
    source_ids, _ = await notebook_members(notebook_id)
    titles = await _titles(source_ids)
    states = await ingestion_states(source_ids)
    items = [_source_ingestion(sid, titles.get(sid), states[sid]) for sid in source_ids]
    active: Dict[str, int] = {}
    for item in items:
        for stage in item.stages:
            if stage.status in ("queued", "running"):
                active[stage.stage] = active.get(stage.stage, 0) + 1
    return NotebookIngestion(
        complete=all(i.complete for i in items),
        sources=len(items),
        sources_complete=sum(i.complete for i in items),
        sources_failed=sum(i.failed for i in items),
        active=active,
        items=items,
    )


@router.post("/sources/{source_id}/ingestion/retry", response_model=SourceIngestion)
async def retry_ingestion(source_id: str) -> SourceIngestion:
    """Re-run a source from its first failed stage (or a stalled or outdated one).

    A failed extraction of a source without pages is retried with
    `POST /sources/{id}/retry`, which re-reads the original content.
    """
    source_id = _source_record(source_id)
    titles = await _titles([source_id])
    if source_id not in titles:
        raise NotFoundError("Source not found")
    stages = (await ingestion_states([source_id]))[source_id]
    live = source_id in await sources_with_live_jobs()
    restart = restart_point(without_stale_claims(stages, live))
    if restart is None:
        if any(s.status == "failed" for s in stages):
            raise InvalidInputError(
                "Extraction failed; retry the source itself (POST /sources/{id}/retry)"
            )
        raise InvalidInputError("Nothing to retry: every stage is done or in progress")
    await reprocess(source_id, restart)
    states = await ingestion_states([source_id])
    return _source_ingestion(source_id, titles[source_id], states[source_id])

"""Ingestion tracking: stage states, versioned reprocessing, worker recovery."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from commands import worker
from commands.page_commands import CaptionPagesInput, caption_pages_command
from open_notebook.domain import ingestion
from open_notebook.domain.ingestion import (
    STAGE_VERSIONS,
    StageState,
    first_outdated,
    ingestion_states,
    is_complete,
    stage_record,
    tracked,
)
from open_notebook.graphs.source import SourceState, save_source
from open_notebook.utils.pdf_pages import PdfPage

SOURCE_ID = "source:deck"


def _status_writes(calls, stage):
    return [fields.get("status") for _, s, fields in calls if s == stage]


# --- tracked ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tracked_records_running_then_done_with_version_and_detail(stage_writes):
    async with tracked(SOURCE_ID, "analyze") as run:
        run.detail = {"sections": 4}
    assert _status_writes(stage_writes, "analyze") == ["running", "done"]
    done = stage_writes[-1][2]
    assert done["version"] == STAGE_VERSIONS["analyze"]
    assert done["detail"] == {"sections": 4}


@pytest.mark.asyncio
async def test_tracked_records_skips_and_failures(stage_writes):
    async with tracked(SOURCE_ID, "concepts") as run:
        run.skip("concept graph is off")
    with pytest.raises(RuntimeError):
        async with tracked(SOURCE_ID, "page_images"):
            raise RuntimeError("rate limited")
    assert _status_writes(stage_writes, "concepts") == ["running", "skipped"]
    assert _status_writes(stage_writes, "page_images") == ["running", "failed"]
    assert "rate limited" in stage_writes[-1][2]["error"]


@pytest.mark.real_stage_writes
@pytest.mark.asyncio
async def test_stage_writes_upsert_one_row_per_source_and_stage():
    query = AsyncMock(return_value=[])
    with patch("open_notebook.domain.ingestion.repo_query", new=query):
        await ingestion.stage_queued(SOURCE_ID, "caption")
    assert query.await_args is not None
    sql, params = query.await_args.args
    assert sql.startswith("UPSERT $id MERGE")
    assert params["id"] == stage_record(SOURCE_ID, "caption")
    assert params["fields"]["status"] == "queued"


@pytest.mark.real_stage_writes
@pytest.mark.asyncio
async def test_a_failing_stage_write_never_fails_the_work():
    with patch(
        "open_notebook.domain.ingestion.repo_query",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        async with tracked(SOURCE_ID, "analyze"):
            pass  # no exception escapes


# --- states and versions ----------------------------------------------------


def _fake_db(stage_rows, paged_ids):
    async def fake_per_source(sql, source_ids):
        if "source_stage" in sql:
            return [r for r in stage_rows if r["source"] in source_ids]
        return [{"source": s} for s in source_ids if s in paged_ids]

    return patch("open_notebook.domain.ingestion._per_source", new=fake_per_source)


@pytest.mark.asyncio
async def test_untracked_sources_read_as_legacy_done():
    with _fake_db([], {SOURCE_ID}):
        states = await ingestion_states([SOURCE_ID, "source:web"])
    paged, web = states[SOURCE_ID], states["source:web"]
    assert [s.stage for s in paged] == list(ingestion.STAGES)
    assert [s.stage for s in web] == ["extract", "embed"]
    assert all(s.status == "done" and s.version == 1 for s in paged + web)


@pytest.mark.asyncio
async def test_tracked_sources_show_pending_stages_until_reached():
    rows = [
        {"source": SOURCE_ID, "stage": "extract", "status": "done", "version": 2},
        {"source": SOURCE_ID, "stage": "caption", "status": "running"},
    ]
    with _fake_db(rows, {SOURCE_ID}):
        stages = (await ingestion_states([SOURCE_ID]))[SOURCE_ID]
    assert [s.status for s in stages] == [
        "done",
        "running",
        "pending",
        "pending",
        "pending",
        "pending",
    ]
    assert not is_complete(stages)


def _states(**versions):
    return [
        StageState(stage, "done", versions.get(stage, STAGE_VERSIONS[stage]))
        for stage in ingestion.STAGES
    ]


def test_first_outdated_is_the_earliest_stage_behind_its_version():
    assert first_outdated(_states()) is None
    assert first_outdated(_states(caption=1, concepts=0)) == "caption"
    assert first_outdated(_states(extract=1)) == "extract"
    in_progress = _states(caption=1)
    in_progress[3] = StageState("analyze", "running")
    assert first_outdated(in_progress) is None  # never interrupt running work


@pytest.mark.asyncio
async def test_reprocess_restarts_from_the_outdated_stage():
    with patch("open_notebook.domain.ingestion.submit_command") as submit:
        await ingestion.reprocess(SOURCE_ID, "extract")
        await ingestion.reprocess(SOURCE_ID, "concepts")
    assert submit.call_args_list[0].args == (
        "open_notebook",
        "caption_pages",
        {"source_id": SOURCE_ID, "refresh": True, "reprocess": True},
    )
    assert submit.call_args_list[1].args[1] == "extract_concepts"


# --- caption job reprocessing -------------------------------------------------


def _fake_source(tmp_path):
    path = tmp_path / "deck.pdf"
    Image.new("RGB", (400, 300), "white").save(path, "PDF")
    source = MagicMock(id=SOURCE_ID, title="Lecture 4", vectorize=AsyncMock())
    source.asset.file_path = str(path)
    return source


def _page_rows(**caption):
    return [
        {
            "page": 1,
            "text": "Reduce tree",
            "image_ratio": 0.0,
            "shapes": 150,
            "garbled": False,
            **caption,
        },
        {"page": 2, "text": "Summary", "image_ratio": 0.0, "shapes": 0},
        {"page": 3, "text": "More", "image_ratio": 0.0, "shapes": 0},
    ]


@pytest.mark.asyncio
async def test_reprocessing_without_new_captions_stops_the_chain(tmp_path):
    source = _fake_source(tmp_path)
    rows = _page_rows(caption=None, caption_version=STAGE_VERSIONS["caption"])
    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch("commands.page_commands.repo_query", new=AsyncMock(return_value=rows)),
        patch("commands.page_commands._caption_page") as caption,
        patch("commands.page_commands.submit_command") as submit,
    ):
        await caption_pages_command(
            CaptionPagesInput(source_id=SOURCE_ID, reprocess=True)
        )
    caption.assert_not_called()  # already checked at this caption version
    source.vectorize.assert_not_awaited()
    submit.assert_not_called()


@pytest.mark.asyncio
async def test_reprocessing_with_a_new_caption_re_embeds_and_re_analyzes(
    tmp_path, stage_writes
):
    source = _fake_source(tmp_path)
    rows = _page_rows(caption=None, caption_version=1)  # checked with an old version

    async def fake_query(query, params=None):
        return rows if query.startswith("SELECT") else []

    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch("commands.page_commands.repo_query", new=fake_query),
        patch("commands.page_commands.provision_langchain_model", new=AsyncMock()),
        patch(
            "commands.page_commands._caption_page",
            new=AsyncMock(return_value="A reduction tree"),
        ),
        patch("commands.page_commands.submit_command") as submit,
    ):
        result = await caption_pages_command(
            CaptionPagesInput(source_id=SOURCE_ID, reprocess=True)
        )
    assert result.pages_captioned == 1
    source.vectorize.assert_awaited_once()
    submit.assert_called_once_with(
        "open_notebook", "analyze_source", {"source_id": SOURCE_ID}
    )
    assert _status_writes(stage_writes, "caption")[-1] == "done"
    assert _status_writes(stage_writes, "analyze") == ["queued"]


@pytest.mark.asyncio
async def test_refresh_re_extracts_pages_in_place_and_tracks_extract(
    tmp_path, stage_writes
):
    source = _fake_source(tmp_path)
    rows = _page_rows(caption="kept", caption_version=1)
    updates = []

    async def fake_query(query, params=None):
        if query.startswith("SELECT page, text FROM"):
            return [{"page": 1, "text": "old text"}]
        if query.startswith("SELECT"):
            return rows
        updates.append((query, params))
        return []

    with (
        patch("commands.page_commands.Source.get", new=AsyncMock(return_value=source)),
        patch("commands.page_commands.repo_query", new=fake_query),
        patch(
            "commands.page_commands.extract_pdf_pages",
            return_value=[PdfPage(1, "new text", shapes=3, garbled=True)],
        ),
        patch("commands.page_commands.submit_command") as submit,
    ):
        await caption_pages_command(
            CaptionPagesInput(source_id=SOURCE_ID, refresh=True, reprocess=True)
        )
    sql, params = updates[0]
    assert "SET text = $text" in sql and "caption" not in sql  # captions kept
    assert params["text"] == "new text" and params["garbled"] is True
    assert _status_writes(stage_writes, "extract") == ["running", "done"]
    submit.assert_called_once()  # text changed: re-embed and re-analyze


# --- save_source records skipped stages --------------------------------------


@pytest.mark.asyncio
async def test_text_only_pdf_skips_captions_and_records_it(stage_writes):
    source = MagicMock(
        id=SOURCE_ID, title="Notes", full_text="text", vectorize=AsyncMock()
    )
    source.save = AsyncMock()
    state = {
        "content_state": {"file_path": "/tmp/notes.pdf"},
        "extraction": MagicMock(content="--- Page 1 ---\nText", title="notes.pdf"),
        "source_id": SOURCE_ID,
        "embed": False,
        "pages": [PdfPage(1, "Text only")],
    }
    with (
        patch(
            "open_notebook.graphs.source.Source.get", new=AsyncMock(return_value=source)
        ),
        patch("open_notebook.graphs.source._store_pages", new=AsyncMock()),
        patch("open_notebook.graphs.source.submit_command") as submit,
    ):
        await save_source(cast(SourceState, state))
    assert _status_writes(stage_writes, "caption") == ["skipped"]
    assert _status_writes(stage_writes, "embed") == ["skipped"]
    assert _status_writes(stage_writes, "analyze") == ["queued"]
    submit.assert_called_once_with(
        "open_notebook", "analyze_source", {"source_id": SOURCE_ID}
    )


# --- worker startup -----------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_startup_requeues_and_reprocesses(monkeypatch):
    query = AsyncMock(return_value=[{"id": "command:1"}, {"id": "command:2"}])
    monkeypatch.setattr("open_notebook.database.repository.repo_query", query)
    reprocess = AsyncMock()
    monkeypatch.setattr(
        "open_notebook.domain.ingestion.plan_reprocessing",
        AsyncMock(return_value={SOURCE_ID: "caption"}),
    )
    monkeypatch.setattr("open_notebook.domain.ingestion.reprocess", reprocess)
    await worker.prepare()
    sqls = [c.args[0] for c in query.await_args_list]
    assert any("SET status = 'new' WHERE status = 'running'" in s for s in sqls)
    reprocess.assert_awaited_once_with(SOURCE_ID, "caption")


@pytest.mark.asyncio
async def test_worker_startup_steps_can_be_disabled_and_never_raise(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_REQUEUE_INTERRUPTED", "false")
    monkeypatch.setenv("OPEN_NOTEBOOK_AUTO_REPROCESS", "false")
    query = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr("open_notebook.database.repository.repo_query", query)
    await worker.prepare()  # orphan cleanup fails, logged only
    assert all("command" not in c.args[0] for c in query.await_args_list)


# --- API ------------------------------------------------------------------------


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_notebook_ingestion_summarizes_sources(client):
    states = {
        "source:a": _states(),
        "source:b": [
            StageState("extract", "done", 2),
            StageState("caption", "running", started_at="2026-10-07T22:00:00"),
            StageState("embed", "pending"),
        ],
    }
    with (
        patch(
            "api.routers.ingestion.repo_query",
            new=AsyncMock(
                side_effect=[
                    ["notebook:n"],
                    [
                        {"id": "source:a", "title": "L1"},
                        {"id": "source:b", "title": "L2"},
                    ],
                ]
            ),
        ),
        patch(
            "api.routers.ingestion.notebook_members",
            new=AsyncMock(return_value=(["source:a", "source:b"], [])),
        ),
        patch(
            "api.routers.ingestion.ingestion_states", new=AsyncMock(return_value=states)
        ),
    ):
        body = client.get("/api/notebooks/notebook:n/ingestion").json()
    assert body["sources"] == 2 and body["sources_complete"] == 1
    assert not body["complete"]
    assert body["active"] == {"caption": 1}
    second = body["items"][1]
    assert second["title"] == "L2" and second["current_stage"] == "caption"


def test_retry_refuses_when_nothing_failed_or_outdated(client):
    with (
        patch(
            "api.routers.ingestion.repo_query",
            new=AsyncMock(return_value=[{"id": "source:a", "title": "L1"}]),
        ),
        patch(
            "api.routers.ingestion.ingestion_states",
            new=AsyncMock(return_value={"source:a": _states()}),
        ),
    ):
        response = client.post("/api/sources/source:a/ingestion/retry")
    assert response.status_code == 400

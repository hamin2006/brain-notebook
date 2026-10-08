"""Ingestion tracking against a real SurrealDB (schema from the migrations).

Skipped unless SURREAL_TEST_URL points at a disposable database; see
test_agent_tools_db.py for how to start one.
"""

import os

import pytest
import pytest_asyncio

TEST_URL = os.environ.get("SURREAL_TEST_URL")
pytestmark = [
    pytest.mark.skipif(not TEST_URL, reason="SURREAL_TEST_URL not set"),
    pytest.mark.real_stage_writes,
]


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setenv("SURREAL_URL", TEST_URL)
    for key, value in {"SURREAL_USER": "root", "SURREAL_PASSWORD": "root"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SURREAL_NAMESPACE", "ingestion_test")
    monkeypatch.setenv("SURREAL_DATABASE", f"db_{os.getpid()}_{id(tmp_path)}")

    from open_notebook.database.async_migrate import AsyncMigrationManager
    from open_notebook.database.repository import repo_query

    await AsyncMigrationManager().run_migration_up()

    async def make_source(title):
        row = (
            await repo_query(
                "CREATE source CONTENT {title: $t, full_text: 'x'}", {"t": title}
            )
        )[0]
        return str(row["id"])

    return repo_query, make_source


@pytest.mark.asyncio
async def test_stage_rows_track_a_source_through_the_pipeline(db):
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    deck = await make_source("deck.pdf")
    web = await make_source("article")
    await repo_query(
        "CREATE source_page CONTENT {source: $s, page: 1, text: 'Adam'}",
        {"s": ingestion.ensure_record_id(deck)},
    )

    await ingestion.stage_queued(deck, "extract")
    async with ingestion.tracked(deck, "extract") as run:
        run.detail = {"pages": 1}
    await ingestion.stage_queued(deck, "caption")  # same row updated, not a new one

    states = await ingestion.ingestion_states([deck, web])
    stages = {s.stage: s for s in states[deck]}
    assert stages["extract"].status == "done"
    assert stages["extract"].version == ingestion.STAGE_VERSIONS["extract"]
    assert stages["extract"].detail == {"pages": 1}
    assert stages["extract"].started_at and stages["extract"].finished_at
    assert stages["caption"].status == "queued"
    assert stages["concepts"].status == "pending"
    assert [s.stage for s in states[web]] == ["extract", "embed"]  # legacy, unpaged

    rows = await repo_query(
        "SELECT * FROM source_stage WHERE source = $s",
        {"s": ingestion.ensure_record_id(deck)},
    )
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_deleting_a_source_removes_its_stage_rows(db):
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    deck = await make_source("deck.pdf")
    await ingestion.stage_queued(deck, "extract")
    await repo_query("DELETE $s", {"s": ingestion.ensure_record_id(deck)})
    assert await repo_query("SELECT * FROM source_stage") == []


@pytest.mark.asyncio
async def test_worker_startup_requeues_running_jobs_and_drops_orphan_rows(db):
    from commands import worker
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    for status in ("running", "running", "completed"):
        await repo_query(
            "CREATE command CONTENT {app: 'open_notebook', name: 'embed_source', "
            "args: {}, status: $status}",
            {"status": status},
        )
    gone = await make_source("deleted.pdf")
    await ingestion.stage_queued(gone, "extract")
    await repo_query(
        "DELETE source WHERE id = $s", {"s": ingestion.ensure_record_id(gone)}
    )
    # A row written after its source was deleted (a late job) is an orphan.
    await ingestion.stage_failed(gone, "embed", "Source not found")

    assert await worker.requeue_interrupted() == 2
    statuses = await repo_query("SELECT VALUE status FROM command")
    assert sorted(statuses) == ["completed", "new", "new"]
    assert await worker.remove_orphan_stages() == 1
    assert await repo_query("SELECT * FROM source_stage") == []


@pytest.mark.asyncio
async def test_plan_reprocessing_finds_legacy_and_outdated_sources(db):
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    legacy = await make_source("old.pdf")  # ingested before tracking
    await repo_query(
        "CREATE source_page CONTENT {source: $s, page: 1, text: 'x'}",
        {"s": ingestion.ensure_record_id(legacy)},
    )
    current = await make_source("new.pdf")
    for stage in ("extract", "embed"):
        await ingestion.stage_done(current, stage)

    plan = await ingestion.plan_reprocessing()
    assert plan == {legacy: "extract"}  # extract is at version 2, legacy at 1

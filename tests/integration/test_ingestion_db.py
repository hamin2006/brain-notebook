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

    # The API queues a new source's extract row before extraction writes pages
    # (a source with pages but no rows would be adopted as pre-tracking).
    await ingestion.stage_queued(deck, "extract")
    await repo_query(
        "CREATE source_page CONTENT {source: $s, page: 1, text: 'Adam'}",
        {"s": ingestion.ensure_record_id(deck)},
    )
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
async def test_rows_from_before_the_new_page_fields_can_still_be_updated(db):
    """Migration 32: DEFINE FIELD ... DEFAULT doesn't fill existing records."""
    from open_notebook.database.async_migrate import AsyncMigrationManager
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    deck = ingestion.ensure_record_id(await make_source("old.pdf"))
    # An old row: written before shapes / garbled / caption_version existed.
    await repo_query("REMOVE FIELD shapes ON source_page")
    await repo_query("REMOVE FIELD garbled ON source_page")
    await repo_query("REMOVE FIELD caption_version ON source_page")
    await repo_query(
        "CREATE source_page CONTENT {source: $s, page: 1, text: 'x'}", {"s": deck}
    )
    await repo_query("DELETE _sbl_migrations WHERE version >= 30")
    await AsyncMigrationManager().run_migration_up()

    await repo_query(
        "UPDATE source_page SET text = 'y' WHERE source = $s AND page = 1", {"s": deck}
    )
    row = (
        await repo_query("SELECT * FROM source_page WHERE source = $s", {"s": deck})
    )[0]
    assert (row["text"], row["shapes"], row["garbled"], row["caption_version"]) == (
        "y",
        0,
        False,
        0,
    )


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
async def test_sources_with_live_jobs_reads_the_queue(db):
    from open_notebook.domain import ingestion

    repo_query, _ = db
    for sid, status in (
        ("source:a", "new"),
        ("source:b", "running"),
        ("source:c", "failed"),
    ):
        await repo_query(
            "CREATE command CONTENT {app: 'open_notebook', name: 'caption_pages', "
            "args: {source_id: $sid}, status: $status}",
            {"sid": sid, "status": status},
        )
    await repo_query(
        "CREATE command CONTENT {app: 'open_notebook', name: 'generate_podcast', "
        "args: {}, status: 'new'}"
    )
    assert await ingestion.sources_with_live_jobs() == {"source:a", "source:b"}


@pytest.mark.asyncio
async def test_reprocessing_a_source_from_before_tracking_keeps_it_complete(db):
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    old = await make_source("old.pdf")
    await repo_query(
        "CREATE source_page CONTENT {source: $s, page: 1, text: 'x'}",
        {"s": ingestion.ensure_record_id(old)},
    )
    # A reprocess queues the caption job, which refreshes extraction and
    # captions without changes, so the chain stops there.
    await ingestion.stage_queued(old, "caption")
    async with ingestion.tracked(old, "extract"):
        pass
    async with ingestion.tracked(old, "caption"):
        pass

    stages = (await ingestion.ingestion_states([old]))[old]
    assert ingestion.is_complete(stages)
    versions = {s.stage: s.version for s in stages}
    assert versions["extract"] == ingestion.STAGE_VERSIONS["extract"]
    assert versions["embed"] == ingestion.LEGACY_VERSION
    assert await ingestion.plan_reprocessing() == {}


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
    # extract is at version 2, legacy sources at 1
    assert plan == {legacy: ingestion.Restart("extract", "outdated", True)}


@pytest.mark.asyncio
async def test_a_partly_failed_stage_is_stored_and_planned_for_a_retry(db):
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    deck = await make_source("deck.pdf")
    await ingestion.stage_queued(deck, "extract")
    await repo_query(
        "CREATE source_page CONTENT {source: $s, page: 1, text: 'x'}",
        {"s": ingestion.ensure_record_id(deck)},
    )
    await ingestion.stage_done(deck, "extract")
    async with ingestion.tracked(deck, "caption") as run:
        run.detail = {"captioned": 2, "failed_pages": [1]}
        run.partly_failed("1 of 3 pages could not be captioned (pages 1)")
    for stage in ("embed", "analyze", "page_images", "concepts"):
        await ingestion.stage_done(deck, stage)

    stages = {s.stage: s for s in (await ingestion.ingestion_states([deck]))[deck]}
    assert stages["caption"].status == "failed"
    assert (stages["caption"].error or "").startswith("1 of 3 pages")
    assert stages["caption"].detail == {"captioned": 2, "failed_pages": [1]}
    plan = await ingestion.plan_reprocessing()
    # Later stages finished: continue past the retry only if a caption is added.
    assert plan == {deck: ingestion.Restart("caption", "failed", True)}


@pytest.mark.asyncio
async def test_replacing_a_concept_graph_twice_leaves_one_copy(db):
    from commands.concept_commands import replace_concept_graph
    from open_notebook.domain import ingestion

    repo_query, make_source = db
    deck = ingestion.ensure_record_id(await make_source("deck.pdf"))
    concept = (await repo_query("CREATE concept CONTENT {name: 'ReLU', key: 'relu'}"))[
        0
    ]
    mention = {
        "concept": ingestion.ensure_record_id(str(concept["id"])),
        "source": deck,
        "section": 0,
        "page_start": 3,
        "page_end": 3,
        "context": None,
    }
    for _ in range(2):  # a rerun replaces, never appends
        await replace_concept_graph(deck, [mention], [])
    rows = await repo_query(
        "SELECT * FROM concept_mention WHERE source = $s", {"s": deck}
    )
    assert len(rows) == 1
    await replace_concept_graph(deck, [], [])
    assert not await repo_query(
        "SELECT * FROM concept_mention WHERE source = $s", {"s": deck}
    )


@pytest.mark.asyncio
async def test_dense_summary_is_not_applied_to_uploads_by_default(db):
    """Migration 33: nothing reads Dense Summary, and it prompts with whole documents."""
    repo_query, _ = db
    rows = await repo_query(
        "SELECT name, apply_default FROM transformation WHERE name = 'Dense Summary'"
    )
    assert rows and rows[0]["apply_default"] is False


@pytest.mark.asyncio
async def test_trace_titles_come_from_sources_and_notes(db):
    from open_notebook.agent.display import display_trace

    repo_query, make_source = db
    deck = await make_source("Lecture 6.pdf")
    note = str(
        (await repo_query("CREATE note CONTENT {title: 'Exam notes', content: 'x'}"))[
            0
        ]["id"]
    )
    trace = await display_trace(
        [
            {
                "tool": "view",
                "args": {"address": f"{deck}#p76"},
                "result": f"Showing {deck}#p76.",
            },
            {
                "tool": "read",
                "args": {"address": note},
                "result": f"{note}: Exam notes",
            },
        ]
    )
    assert trace[0]["subject"] == "Lecture 6.pdf p. 76"
    assert trace[0]["result"] == "Showing Lecture 6.pdf p. 76."
    assert trace[1]["subject"] == "Exam notes"

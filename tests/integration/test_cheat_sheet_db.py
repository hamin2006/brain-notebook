"""Cheat sheet storage against a real SurrealDB (schema from the migrations).

Skipped unless SURREAL_TEST_URL points at a disposable database; see
test_agent_tools_db.py for how to start one.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

TEST_URL = os.environ.get("SURREAL_TEST_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="SURREAL_TEST_URL not set")


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setenv("SURREAL_URL", TEST_URL)
    for key, value in {"SURREAL_USER": "root", "SURREAL_PASSWORD": "root"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SURREAL_NAMESPACE", "cheat_sheet_test")
    monkeypatch.setenv("SURREAL_DATABASE", f"db_{os.getpid()}_{id(tmp_path)}")

    from open_notebook.database.async_migrate import AsyncMigrationManager
    from open_notebook.database.repository import ensure_record_id, repo_query

    await AsyncMigrationManager().run_migration_up()

    async def make_deck(title, sections):
        source = str(
            (await repo_query("CREATE source CONTENT {title: $t, full_text: 'x'}", {"t": title}))[0]["id"]
        )  # fmt: skip
        record = ensure_record_id(source)
        page = 1
        for index, (name, n_pages) in enumerate(sections):
            await repo_query(
                "CREATE source_section CONTENT {source: $s, index: $i, title: $t, "
                "page_start: $a, page_end: $b, summary: ''}",
                {
                    "s": record,
                    "i": index,
                    "t": name,
                    "a": page,
                    "b": page + n_pages - 1,
                },
            )
            for p in range(page, page + n_pages):
                await repo_query(
                    "CREATE source_page CONTENT {source: $s, page: $p, text: $text}",
                    {"s": record, "p": p, "text": f"{name} page {p}: a formula"},
                )
            page += n_pages
        return source

    return repo_query, make_deck


def _model(reply: str):
    return SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(content=reply, response_metadata={})
        )
    )


ITEM = '{"items": [{"kind": "formula", "title": "Ratio test", "body": "$L<1$", "priority": 1, "page_start": 1}]}'


@pytest.mark.asyncio
async def test_items_are_cached_per_section_and_reread_after_a_new_outline(db):
    import asyncio

    from commands import cheat_sheet_commands as job
    from open_notebook.domain import cheat_sheet as sheets

    repo_query, make_deck = db
    deck = await make_deck("Lecture 5.pdf", [("Ratio", 2), ("Root", 2)])
    other = await make_deck("Lecture 6.pdf", [("Taylor", 1)])
    model = _model(ITEM)
    sem = asyncio.Semaphore(4)

    assert await job.stale_section_count([deck, other]) == 3
    read, failed = await job.ensure_recall_items(deck, model, sem, job.Usage())
    assert (read, failed) == (2, [])
    items = await sheets.sheet_items([deck, other])
    assert [(i["section"], i["title"]) for i in items] == [
        (0, "Ratio test"),
        (1, "Ratio test"),
    ]
    assert items[1]["page_start"] == 3  # clamped into the Root section (pp. 3-4)

    # Cached: nothing is read again.
    model.ainvoke.reset_mock()
    assert await job.ensure_recall_items(deck, model, sem, job.Usage()) == (0, [])
    assert model.ainvoke.await_count == 0
    assert await job.stale_section_count([deck, other]) == 1

    # Analysis rewrites the outline (one section now): items are read again
    # and the second section's items go.
    await repo_query(
        "DELETE source_section WHERE source = $s", {"s": sheets.ensure_record_id(deck)}
    )
    await repo_query(
        "CREATE source_section CONTENT {source: $s, index: 0, title: 'All', page_start: 1, page_end: 4, summary: ''}",
        {"s": sheets.ensure_record_id(deck)},
    )  # fmt: skip
    assert await job.ensure_recall_items(deck, model, sem, job.Usage()) == (1, [])
    assert [i["section"] for i in await sheets.sheet_items([deck])] == [0]

    # A failed section is reported and stays unread.
    bad = _model("nothing")
    assert await job.ensure_recall_items(other, bad, sem, job.Usage()) == (1, [0])
    assert await job.stale_section_count([other]) == 1

    # Deleting the source deletes its items.
    await repo_query("DELETE $s", {"s": sheets.ensure_record_id(deck)})
    assert await sheets.sheet_items([deck]) == []


@pytest.mark.asyncio
async def test_sheets_versions_and_comments_round_trip_and_cascade(db):
    from open_notebook.domain import cheat_sheet as sheets

    repo_query, make_deck = db
    deck = await make_deck("Lecture 5.pdf", [("Ratio", 1)])
    nb = str((await repo_query("CREATE notebook CONTENT {name: 'Calc', description: ''}"))[0]["id"])  # fmt: skip
    sheet = await sheets.create_sheet(nb, "Midterm", [deck], {"pages": 1})
    assert sheet["status"] == "queued" and sheet["sources"] == [deck]

    layout = {"title": "Midterm", "topics": [{"id": "t1", "title": "T", "lines": []}]}
    await sheets.save_version(sheet["id"], 1, layout)
    await sheets.update_sheet(sheet["id"], {"status": "done", "current_version": 1})
    comment = await sheets.add_comment(sheet["id"], 1, "l1", "too long")
    assert (await sheets.load_comment(sheet["id"], comment["id"]))["text"] == "too long"
    assert (await sheets.load_version(sheet["id"], 1))["layout"] == layout
    assert [s["id"] for s in await sheets.list_sheets(nb)] == [sheet["id"]]
    assert (await sheets.source_labels([deck])) == {deck: "Lecture 5"}

    # Deleting the notebook deletes its sheets, their versions and comments.
    await repo_query("DELETE $nb", {"nb": sheets.ensure_record_id(nb)})
    assert await sheets.list_sheets(nb) == []
    assert await repo_query("SELECT * FROM cheat_sheet_version") == []
    assert await repo_query("SELECT * FROM cheat_sheet_comment") == []


@pytest.mark.asyncio
async def test_rereading_a_section_replaces_rows_whatever_their_ids(db):
    from commands import cheat_sheet_commands as job
    from open_notebook.domain import cheat_sheet as sheets

    repo_query, make_deck = db
    deck = await make_deck("Lecture 5.pdf", [("Ratio", 2)])
    record = sheets.ensure_record_id(deck)
    two = [
        {"kind": "formula", "title": t, "body": "$x$", "priority": 1, "page_start": 1, "page_end": 1}
        for t in ("A", "B")
    ]  # fmt: skip
    # A row with a random id (as older builds wrote) at position 0, then two items.
    await repo_query(
        "CREATE recall_item CONTENT {source: $s, section: 0, index: 0, kind: 'formula', "
        "title: 'old', body: 'x', priority: 1, page_start: 1, page_end: 1, version: 0}",
        {"s": record},
    )
    await job._store_section_items(record, 0, two)
    assert [i["title"] for i in await sheets.sheet_items([deck])] == ["A", "B"]
    await job._store_section_items(record, 0, two[1:])
    assert [i["title"] for i in await sheets.sheet_items([deck])] == ["B"]
    await job._store_section_items(record, 0, [])
    assert await sheets.sheet_items([deck]) == []

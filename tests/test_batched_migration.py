"""Batched backfill migrations: short statements, retried on write conflicts."""

from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.database.async_migrate import AsyncBatchedUpdate


@pytest.mark.asyncio
async def test_backfill_updates_in_batches_and_retries_conflicts():
    ids = [f"source_page:p{i}" for i in range(5)]
    updates: list = []
    conflicts = iter([True])  # the second batch conflicts once

    async def fake_query(sql, params=None):
        if sql.startswith("SELECT"):
            return ids
        if len(updates) == 1 and next(conflicts, False):
            raise RuntimeError("Transaction conflict")
        updates.append([str(i) for i in params["ids"]])
        return []

    migration = AsyncBatchedUpdate("source_page", "shapes = 0", "shapes = NONE", 2)
    with (
        patch("open_notebook.database.async_migrate.repo_query", new=fake_query),
        patch("open_notebook.database.async_migrate.bump_version", new=AsyncMock()) as bump,
        patch("open_notebook.database.async_migrate.asyncio.sleep", new=AsyncMock()),
    ):  # fmt: skip
        await migration.run()

    assert updates == [ids[0:2], ids[2:4], ids[4:5]]
    bump.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failing_backfill_leaves_the_version_alone():
    migration = AsyncBatchedUpdate("source_page", "shapes = 0", "shapes = NONE")
    with (
        patch("open_notebook.database.async_migrate.repo_query", new=AsyncMock(side_effect=[["source_page:p1"], ValueError("bad field")])),
        patch("open_notebook.database.async_migrate.bump_version", new=AsyncMock()) as bump,
    ):  # fmt: skip
        with pytest.raises(ValueError):
            await migration.run()
    bump.assert_not_awaited()

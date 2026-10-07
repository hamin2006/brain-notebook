"""Agent settings, memories and backfill endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def settings():
    from open_notebook.domain.agent_settings import AgentSettings

    AgentSettings._instances.pop(AgentSettings.record_id, None)
    instance = AgentSettings()
    object.__setattr__(instance, "_db_loaded", True)
    with (
        patch.object(AgentSettings, "load", new=AsyncMock(return_value=instance)),
        patch.object(AgentSettings, "update", new=AsyncMock()) as update,
    ):
        yield instance, update
    AgentSettings._instances.pop(AgentSettings.record_id, None)


def test_settings_defaults_and_partial_update(client, settings):
    instance, update = settings
    got = client.get("/api/agent/settings").json()
    assert got == {
        "rerank_model": "voyageai/rerank-3-lite",
        "page_embedding_model": "google/gemini-embedding-2",
        "knowledge_graph": True,
        "memory": True,
    }
    out = client.put(
        "/api/agent/settings", json={"rerank_model": "  ", "memory": False}
    ).json()
    assert out["rerank_model"] == "" and out["memory"] is False
    assert out["page_embedding_model"] == "google/gemini-embedding-2"
    update.assert_awaited_once()


def test_memories_list_and_delete(client):
    rows = [
        {"id": "memory:a", "content": "Exam Dec 10", "notebook": "notebook:x", "created": "2026-10-07"},
        {"id": "memory:b", "content": "Short answers", "notebook": None, "created": "2026-10-07"},
    ]  # fmt: skip
    with patch("api.routers.agent.repo_query", new=AsyncMock(return_value=rows)):
        listed = client.get("/api/agent/memories").json()
    assert [(m["id"], m["notebook_id"]) for m in listed] == [
        ("memory:a", "notebook:x"),
        ("memory:b", None),
    ]
    with patch(
        "api.routers.agent.delete_memory", new=AsyncMock(return_value=True)
    ) as d:
        assert client.delete("/api/agent/memories/a").status_code == 200
    d.assert_awaited_once_with("memory:a")
    with patch("api.routers.agent.delete_memory", new=AsyncMock(return_value=False)):
        assert client.delete("/api/agent/memories/zzz").status_code == 404


def test_rebuild_submits_one_job_per_source_with_rows(client):
    async def fake_query(sql, params=None):
        if sql == "SELECT VALUE id FROM source":
            return ["source:a", "source:b"]
        return ["page:1"] if str(params["s"]) == "source:a" else []

    with (
        patch("api.routers.agent.repo_query", new=fake_query),
        patch(
            "api.routers.agent.CommandService.submit_command_job",
            new=AsyncMock(return_value="command:1"),
        ) as submit,
    ):
        out = client.post(
            "/api/agent/rebuild", json={"what": "page_embeddings", "force": True}
        ).json()
    assert out == {"submitted": 1, "command_ids": ["command:1"]}
    submit.assert_awaited_once_with(
        "open_notebook", "embed_pages", {"source_id": "source:a", "force": True}
    )

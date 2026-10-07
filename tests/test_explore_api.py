"""Notebook overview, concept detail and source structure endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.agent.scope import AgentScope, ScopedSource


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def _scope():
    return AgentScope(
        sources={
            "source:a": ScopedSource(id="source:a", title="Lecture 1", page_count=40, metadata={"doc_type": "lecture"}),
            "source:b": ScopedSource(id="source:b", title="Lecture 2", page_count=60),
        },
        notes={},
        notebook_id="notebook:x",
    )  # fmt: skip


CONCEPTS = {
    "concept:relu": {"name": "ReLU", "key": "relu", "documents": {"source:a", "source:b"}, "mentions": 5},
    "concept:adam": {"name": "Adam", "key": "adam", "documents": {"source:b"}, "mentions": 9},
    "concept:sgd": {"name": "SGD", "key": "sgd", "documents": {"source:b"}, "mentions": 2},
}  # fmt: skip


def test_overview_counts_and_ranks_concepts(client):
    with (
        patch("api.routers.explore._notebook_scope", new=AsyncMock(return_value=_scope())),
        patch("api.routers.explore.per_source", new=AsyncMock(return_value=[{"n": 4}, {"n": 6}])),
        patch("api.routers.explore.scoped_concepts", new=AsyncMock(return_value=CONCEPTS)),
    ):  # fmt: skip
        body = client.get("/api/notebooks/notebook:x/overview?limit=2").json()
    assert body["documents"] == 2 and body["pages"] == 100 and body["sections"] == 10
    assert body["concepts"] == 3
    # shared across more documents first, then by mentions
    assert [c["name"] for c in body["top_concepts"]] == ["ReLU", "Adam"]
    assert body["top_concepts"][0] == {
        "id": "concept:relu",
        "name": "ReLU",
        "documents": 2,
        "mentions": 5,
    }


def test_concept_detail_resolves_titles_and_direction(client):
    mentions = [
        {"source": "source:a", "page_start": 3, "page_end": 4, "context": "ReLU is"}
    ]
    relations = [
        {"from_concept": "concept:relu", "to_concept": "concept:sig", "from_name": "ReLU", "to_name": "Sigmoid",
         "relation": "replaces", "source": "source:a", "page_start": 5, "page_end": 5},
        {"from_concept": "concept:cnn", "to_concept": "concept:relu", "from_name": "CNN", "to_name": "ReLU",
         "relation": "uses", "source": "source:b", "page_start": 9, "page_end": 9},
    ]  # fmt: skip
    with (
        patch("api.routers.explore._notebook_scope", new=AsyncMock(return_value=_scope())),
        patch("api.routers.explore.repo_query", new=AsyncMock(return_value=["ReLU"])),
        patch("api.routers.explore.concept_mentions", new=AsyncMock(return_value=mentions)),
        patch("api.routers.explore.concept_relations", new=AsyncMock(return_value=relations)),
    ):  # fmt: skip
        body = client.get("/api/notebooks/notebook:x/concepts/concept:relu").json()
    assert body["name"] == "ReLU"
    assert body["mentions"][0]["source_title"] == "Lecture 1"
    assert [(r["name"], r["outgoing"]) for r in body["relations"]] == [
        ("Sigmoid", True),
        ("CNN", False),
    ]


def test_source_structure(client):
    sections = [
        {"index": 1, "title": "Intro", "page_start": 1, "page_end": 4, "summary": "Why"}
    ]
    with (
        patch("api.routers.explore.load_scope", new=AsyncMock(return_value=_scope())),
        patch("api.routers.explore.scoped_concepts", new=AsyncMock(return_value=CONCEPTS)),
        patch("api.routers.explore.document_summary", new=AsyncMock(return_value="A deck")),
        patch("api.routers.explore.sections_of", new=AsyncMock(return_value=sections)),
    ):  # fmt: skip
        body = client.get("/api/sources/a/structure").json()
    assert body["id"] == "source:a" and body["page_count"] == 40
    assert body["metadata"] == {"doc_type": "lecture"} and body["summary"] == "A deck"
    assert body["sections"][0]["title"] == "Intro"
    assert len(body["concepts"]) == 3


def test_source_structure_missing(client):
    with patch(
        "api.routers.explore.load_scope",
        new=AsyncMock(return_value=AgentScope(sources={}, notes={})),
    ):
        assert client.get("/api/sources/zzz/structure").status_code == 404


def test_graph_keeps_top_concepts_relations_and_co_mentions(client):
    scope = AgentScope(
        sources={
            "source:a": ScopedSource(id="source:a", title="Lecture 1", metadata={"sequence": 1}),
            "source:b": ScopedSource(id="source:b", title="Lecture 2", metadata={"sequence": 2}),
        },
        notes={},
    )  # fmt: skip
    mentions = [
        {"concept": "concept:relu", "source": "source:a", "section": 0},
        {"concept": "concept:sig", "source": "source:a", "section": 0},
        {"concept": "concept:relu", "source": "source:b", "section": 3},
        {"concept": "concept:adam", "source": "source:b", "section": 3},
        {"concept": "concept:rare", "source": "source:b", "section": 4},
    ]
    relations = [
        {
            "from_concept": "concept:relu",
            "to_concept": "concept:sig",
            "relation": "replaces",
        }
    ]

    async def per_source(sql, ids, **params):
        return mentions if "concept_mention" in sql else relations

    names = [
        {"id": c, "name": c.split(":")[1]}
        for c in ("concept:relu", "concept:sig", "concept:adam")
    ]
    with (
        patch("api.routers.explore._notebook_scope", new=AsyncMock(return_value=scope)),
        patch("api.routers.explore.per_source", new=per_source),
        patch("api.routers.explore.repo_query", new=AsyncMock(return_value=names)),
    ):  # fmt: skip
        body = client.get("/api/notebooks/notebook:x/graph?limit=3").json()
    assert body["total_concepts"] == 4
    assert [d["id"] for d in body["documents"]] == ["source:a", "source:b"]
    relu = next(n for n in body["nodes"] if n["id"] == "concept:relu")
    assert relu["home"] == "source:a" and relu["documents"] == ["source:a", "source:b"]
    assert relu["mentions"] == 2
    assert "concept:rare" not in {n["id"] for n in body["nodes"]}
    kinds = {(e["source"], e["target"], e["kind"]) for e in body["edges"]}
    # the stated relation, and adam/relu share a section; relu/sig co-occur but already relate
    assert ("concept:relu", "concept:sig", "relation") in kinds
    assert ("concept:adam", "concept:relu", "co") in kinds
    assert not any(
        k == "co" and {s, t} == {"concept:relu", "concept:sig"} for s, t, k in kinds
    )

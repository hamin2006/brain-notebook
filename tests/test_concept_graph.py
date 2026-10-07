"""The concept graph: extraction job, matching and the graph tool."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from open_notebook.agent import retrieval
from open_notebook.agent.scope import AgentScope, ScopedSource
from open_notebook.agent.tools import tool_graph
from open_notebook.utils.concepts import concept_id, concept_key

SCOPE = AgentScope(
    sources={
        "source:l3": ScopedSource("source:l3", "Lecture 3"),
        "source:l4": ScopedSource("source:l4", "Lecture 4"),
    },
    notes={},
)


def test_concept_key_and_id_are_normalized_and_stable():
    assert concept_key("  Batch-Normalization ") == "batch normalization"
    assert concept_id("batch normalization") == concept_id(
        concept_key("Batch Normalization")
    )
    assert concept_id("relu") != concept_id("dropout")


CONCEPTS = {
    "concept:bn": {"name": "Batch normalization", "key": "batch normalization", "documents": {"source:l3", "source:l4"}, "mentions": 3, "embedding": [1.0, 0.0]},
    "concept:ln": {"name": "Layer normalization", "key": "layer normalization", "documents": {"source:l3"}, "mentions": 1, "embedding": [0.9, 0.1]},
    "concept:do": {"name": "Dropout", "key": "dropout", "documents": {"source:l3"}, "mentions": 2, "embedding": [0.0, 1.0]},
}  # fmt: skip


def test_match_concepts_prefers_exact_then_partial_then_similar():
    assert retrieval.match_concepts(CONCEPTS, "batch-normalization", None, 3) == [
        "concept:bn"
    ]
    assert retrieval.match_concepts(CONCEPTS, "normalization", None, 3) == [
        "concept:bn",  # in more documents
        "concept:ln",
    ]
    assert retrieval.match_concepts(CONCEPTS, "BN", [0.95, 0.05], 2) == [
        "concept:bn",
        "concept:ln",
    ]


@pytest.mark.asyncio
async def test_graph_overview_lists_concepts_shared_by_most_documents():
    with patch.object(
        retrieval, "scoped_concepts", new=AsyncMock(return_value=CONCEPTS)
    ):
        out = await tool_graph(SCOPE)
    lines = out.splitlines()
    assert lines[1] == "- Batch normalization: 2 document(s), 3 section(s)"
    assert lines[2].startswith("- Dropout")


@pytest.mark.asyncio
async def test_graph_concept_shows_mentions_and_relations_with_addresses():
    mentions = [
        {"source": "source:l3", "section": 9, "page_start": 96, "page_end": 108, "context": "Normalizes activations per batch"},
        {"source": "source:l4", "section": 2, "page_start": 12, "page_end": 12, "context": None},
    ]  # fmt: skip
    relations = [
        {"from_name": "Batch normalization", "to_name": "Internal covariate shift", "relation": "reduces", "source": "source:l3", "page_start": 97, "page_end": 97}
    ]  # fmt: skip
    with (
        patch.object(retrieval, "scoped_concepts", new=AsyncMock(return_value=CONCEPTS)),
        patch.object(retrieval, "concept_mentions", new=AsyncMock(return_value=mentions)),
        patch.object(retrieval, "concept_relations", new=AsyncMock(return_value=relations)),
        patch("open_notebook.utils.embedding.generate_embedding", new=AsyncMock(side_effect=RuntimeError("offline"))),
        patch.object(retrieval, "concept_for_name", new=AsyncMock(return_value=None)),
    ):  # fmt: skip
        out = await tool_graph(SCOPE, concept="batch normalization")
    assert out.startswith('Concept "Batch normalization"')
    assert "Appears in 2 document(s):" in out
    assert (
        '- source:l3#p96-108 "Lecture 3" (section source:l3#s9): Normalizes activations per batch'
        in out
    )
    assert (
        "- Batch normalization --reduces--> Internal covariate shift [source:l3#p97]"
        in out
    )


@pytest.mark.asyncio
async def test_graph_without_a_graph_says_so():
    with patch.object(retrieval, "scoped_concepts", new=AsyncMock(return_value={})):
        out = await tool_graph(SCOPE, concept="dropout")
    assert "No concept graph" in out


@pytest.mark.asyncio
async def test_extract_concepts_writes_mentions_and_relations():
    from commands import concept_commands as cmd

    extraction = {
        "concepts": [
            {"name": "Batch Normalization", "page": 97, "context": "Normalizes per batch"},
            {"name": "batch normalization", "page": 98, "context": "duplicate"},
            {"name": "Internal covariate shift", "page": 200, "context": ""},
        ],
        "relations": [
            {"source": "Batch normalization", "relation": "reduces", "target": "Internal Covariate Shift", "page": 97},
            {"source": "Batch normalization", "relation": "uses", "target": "Unknown thing"},
        ],
    }  # fmt: skip
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(extraction)))
    upserts: list = []
    aliases: dict = {}
    inserted: dict = {}

    async def fake_query(sql, params=None):
        if "FROM source_section" in sql:
            return [
                {
                    "index": 0,
                    "title": "Normalization",
                    "page_start": 96,
                    "page_end": 108,
                }
            ]
        if "FROM source_page" in sql:
            return [
                {"page": p, "text": f"page {p} text", "caption": None}
                for p in range(96, 109)
            ]
        if sql.startswith("SELECT"):  # aliases, existing concepts: none yet
            return []
        if sql.startswith("UPSERT") and "name" in params:
            upserts.append(params["key"])
        elif sql.startswith("UPSERT"):
            aliases[params["key"]] = str(params["concept"])
        return []

    with (
        patch.object(cmd.AgentSettings, "load", new=AsyncMock(return_value=SimpleNamespace(knowledge_graph=True))),
        patch.object(cmd, "repo_query", new=fake_query),
        patch.object(cmd, "repo_insert", new=AsyncMock(side_effect=lambda t, rows: inserted.setdefault(t, rows))),
        patch.object(cmd.Source, "get", new=AsyncMock(return_value=MagicMock(metadata={"title": "Lecture 3"}, title="L3"))),
        patch.object(cmd, "provision_langchain_model", new=AsyncMock(return_value=model)),
        patch.object(cmd, "limit_reasoning", side_effect=lambda m: m),
        patch.object(cmd, "generate_embeddings", new=AsyncMock(return_value=[[0.1], [0.2]])),
    ):  # fmt: skip
        out = await cmd.extract_concepts_command(
            cmd.ExtractConceptsInput(source_id="source:l3")
        )

    assert sorted(upserts) == ["batch normalization", "internal covariate shift"]
    assert aliases["internal covariate shift"] == concept_id("internal covariate shift")
    mentions = inserted["concept_mention"]
    assert [(str(m["concept"]), m["page_start"], m["page_end"]) for m in mentions] == [
        (concept_id("batch normalization"), 97, 97),
        (concept_id("internal covariate shift"), 96, 108),  # page outside section
    ]
    [relation] = inserted["concept_relation"]
    assert relation["relation"] == "reduces" and relation["page_start"] == 97
    assert (out.concepts, out.relations) == (2, 1)


@pytest.mark.asyncio
async def test_extract_concepts_off():
    from commands import concept_commands as cmd

    with patch.object(
        cmd.AgentSettings,
        "load",
        new=AsyncMock(return_value=SimpleNamespace(knowledge_graph=False)),
    ):
        out = await cmd.extract_concepts_command(
            cmd.ExtractConceptsInput(source_id="source:l3")
        )
    assert out.concepts == 0


def test_parse_extraction_tolerates_fences_prose_and_latex():
    from open_notebook.utils.concepts import parse_extraction

    raw = (
        "Here you go:\n```json\n"
        '{"concepts": [{"name": "Cross-entropy", "page": 3, '
        '"context": "Loss $-\\sum y \\log(\\hat{y})$ with \\frac{1}{2}, \\"quoted\\""}], '
        '"relations": []}\n```'
    )
    out = parse_extraction(raw)
    assert (
        out.concepts[0].context
        == 'Loss $-\\sum y \\log(\\hat{y})$ with \\frac{1}{2}, "quoted"'
    )
    with pytest.raises(ValueError):
        parse_extraction("no json here")


def test_concept_names_split_abbreviations():
    from open_notebook.utils.concepts import concept_names

    assert concept_names("Rectified linear unit (ReLU)") == [
        "Rectified linear unit",
        "ReLU",
    ]
    assert concept_names("  Dropout ") == ["Dropout"]
    assert concept_names("(odd)") == ["(odd)"]


@pytest.mark.asyncio
async def test_names_resolve_through_existing_aliases():
    from commands import concept_commands as cmd
    from open_notebook.utils.concepts import alias_id

    relu = concept_id("relu")  # created earlier from another lecture's "ReLU"
    created, aliases = [], {}

    async def fake_query(sql, params=None):
        if sql.startswith("SELECT key, concept"):
            wanted = {str(r) for r in params["records"]}
            return (
                [{"key": "relu", "concept": relu}] if alias_id("relu") in wanted else []
            )
        if sql.startswith("SELECT VALUE id"):
            return []
        if sql.startswith("UPSERT") and "name" in params:
            created.append(params["key"])
        elif sql.startswith("UPSERT"):
            aliases[params["key"]] = str(params["concept"])
        return []

    with (
        patch.object(cmd, "repo_query", new=fake_query),
        patch.object(cmd, "generate_embeddings", new=AsyncMock(return_value=[[0.1]])),
    ):
        resolved = await cmd._resolve_concepts(
            ["Rectified linear unit (ReLU)", "Rectified Linear Unit", "Sigmoid"]
        )
    assert resolved["rectified linear unit"] == relu  # via its abbreviation
    assert resolved["sigmoid"] == concept_id("sigmoid")
    assert created == ["sigmoid"]
    assert aliases == {
        "rectified linear unit": relu,
        "sigmoid": concept_id("sigmoid"),
    }


@pytest.mark.asyncio
async def test_graph_lookup_by_abbreviation_uses_the_alias():
    with (
        patch.object(retrieval, "scoped_concepts", new=AsyncMock(return_value=CONCEPTS)),
        patch.object(retrieval, "concept_for_name", new=AsyncMock(return_value="concept:ln")),
        patch.object(retrieval, "concept_mentions", new=AsyncMock(return_value=[])),
        patch.object(retrieval, "concept_relations", new=AsyncMock(return_value=[])),
        patch("open_notebook.utils.embedding.generate_embedding", new=AsyncMock(return_value=[1.0, 0.0])),
    ):  # fmt: skip
        out = await tool_graph(SCOPE, concept="LN")
    assert out.startswith('Concept "Layer normalization"')

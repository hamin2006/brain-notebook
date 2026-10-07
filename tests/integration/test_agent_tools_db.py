"""Agent tools against a real SurrealDB (schema from the migrations).

Skipped unless SURREAL_TEST_URL points at a disposable database, e.g.:

    docker run -d -p 127.0.0.1:18000:8000 surrealdb/surrealdb:v2 start --user root --pass root memory
    SURREAL_TEST_URL=ws://127.0.0.1:18000/rpc uv run pytest tests/integration -q
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from PIL import Image

TEST_URL = os.environ.get("SURREAL_TEST_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="SURREAL_TEST_URL not set")

VEC_OPT = [1.0, 0.0, 0.0]  # "optimizers" direction
VEC_CNN = [0.0, 1.0, 0.0]  # "convolution" direction
VEC_MIX = [0.7, 0.7, 0.0]


@pytest_asyncio.fixture
async def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("SURREAL_URL", TEST_URL)
    for key, value in {"SURREAL_USER": "root", "SURREAL_PASSWORD": "root"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SURREAL_NAMESPACE", "agent_tools_test")
    monkeypatch.setenv("SURREAL_DATABASE", f"db_{os.getpid()}_{id(tmp_path)}")

    from open_notebook.database.async_migrate import AsyncMigrationManager
    from open_notebook.database.repository import (
        ensure_record_id,
        repo_insert,
        repo_query,
    )

    await AsyncMigrationManager().run_migration_up()

    pdf = tmp_path / "lecture4.pdf"
    Image.new("RGB", (800, 450), "white").save(
        pdf, "PDF", save_all=True, append_images=[Image.new("RGB", (800, 450))] * 2
    )

    async def make_source(title, metadata, file_path=None):
        row = (
            await repo_query(
                "CREATE source CONTENT {title: $t, full_text: 'x', metadata: $m, asset: {file_path: $f}}",
                {"t": title, "m": metadata, "f": file_path},
            )
        )[0]
        return str(row["id"])

    l4 = await make_source(
        "AI 360 Lecture 4.pdf",
        {"doc_type": "lecture", "title": "Lecture 4 - Optimizers", "course": "AI 360", "sequence": 4,
         "topics": ["Adam", "dropout"], "page_count": 3},
        str(pdf),
    )  # fmt: skip
    l6 = await make_source(
        "AI 360 Lecture 6.pdf",
        {"doc_type": "lecture", "title": "Lecture 6 - Convolutional Networks", "course": "AI 360",
         "sequence": 6, "page_count": 2},
    )  # fmt: skip
    r4, r6 = ensure_record_id(l4), ensure_record_id(l6)
    await repo_insert(
        "source_page",
        [
            {"source": r4, "page": 1, "text": "Training by gradient descent", "equations": [], "image_ratio": 0.0},
            {"source": r4, "page": 2, "text": "Implicit regularization: Dropout", "equations": [], "image_ratio": 0.0},
            {"source": r4, "page": 3, "text": "", "caption": "Algorithm: Adam combines momentum and RMSProp. alpha = 0.001", "equations": [], "image_ratio": 0.9},
            {"source": r6, "page": 1, "text": "Residual Net: skip connections", "equations": [], "image_ratio": 0.0},
            {"source": r6, "page": 2, "text": "Dropout of 0.5 in AlexNet", "equations": [], "image_ratio": 0.0},
        ],
    )  # fmt: skip
    await repo_insert(
        "source_embedding",
        [
            {"source": r4, "order": 0, "content": "Lecture 4 — pp. 1–2\nTraining by gradient descent. Dropout", "embedding": VEC_MIX, "page_start": 1, "page_end": 2},
            {"source": r4, "order": 1, "content": "Lecture 4 — p. 3\nAdam combines momentum and RMSProp", "embedding": VEC_OPT, "page_start": 3, "page_end": 3},
            {"source": r6, "order": 0, "content": "Lecture 6 — pp. 1–2\nResidual Net skip connections. Dropout of 0.5", "embedding": VEC_CNN, "page_start": 1, "page_end": 2},
        ],
    )  # fmt: skip
    await repo_insert(
        "source_section",
        [
            {"source": r4, "index": 0, "title": "Regularization", "page_start": 1, "page_end": 2, "summary": "Dropout as implicit regularization.", "embedding": VEC_MIX},
            {"source": r4, "index": 1, "title": "Optimizers", "page_start": 3, "page_end": 3, "summary": "Adam combines momentum and RMSProp.", "embedding": VEC_OPT},
            {"source": r6, "index": 0, "title": "Residual networks", "page_start": 1, "page_end": 2, "summary": "Skip connections.", "embedding": VEC_CNN},
        ],
    )  # fmt: skip
    await repo_insert(
        "source_insight",
        [
            {"source": r4, "insight_type": "Document Summary", "content": "Lecture 4 covers regularization and optimizers such as Adam.", "embedding": VEC_OPT},
            {"source": r6, "insight_type": "Document Summary", "content": "Lecture 6 covers convolutional architectures and ResNet.", "embedding": VEC_MIX},
        ],
    )  # fmt: skip
    note = str(
        (await repo_query("CREATE note CONTENT {title: 'My dropout notes', content: 'Dropout scales activations at test time', embedding: $e}", {"e": VEC_MIX}))[0]["id"]
    )  # fmt: skip
    outside = await make_source("Other notebook doc.pdf", {"doc_type": "paper"})

    notebook = str(
        (await repo_query("CREATE notebook CONTENT {name: 'AI 360', description: ''}"))[
            0
        ]["id"]
    )

    from open_notebook.agent.scope import load_scope

    scope = await load_scope([l4, l6], [note], notebook)
    yield {
        "scope": scope,
        "l4": l4,
        "l6": l6,
        "note": note,
        "outside": outside,
        "notebook": notebook,
    }


def _tools(scope):
    from open_notebook.agent.tools import build_tools

    return {t.name: t for t in build_tools(scope)}


@pytest.mark.asyncio
async def test_list_resolves_lecture_numbers_and_sorts(corpus):
    tools = _tools(corpus["scope"])
    out = await tools["list"].ainvoke({"sequence": 4})
    assert corpus["l4"] in out and corpus["l6"] not in out
    everything = await tools["list"].ainvoke({})
    assert everything.index(corpus["l4"]) < everything.index(corpus["l6"])
    assert (
        "AI 360 #4" in everything
        and "3 pages" in everything
        and corpus["note"] in everything
    )


@pytest.mark.asyncio
async def test_grep_is_exhaustive_with_pages(corpus):
    out = await _tools(corpus["scope"])["grep"].ainvoke({"pattern": "dropout"})
    assert out.startswith("3 match(es)")  # Lecture 4 p2, Lecture 6 p2, the note
    assert f"{corpus['l4']}#p2" in out and f"{corpus['l6']}#p2" in out
    adam = await _tools(corpus["scope"])["grep"].ainvoke({"pattern": "rmsprop"})
    assert f"{corpus['l4']}#p3" in adam  # found in the vision caption


@pytest.mark.asyncio
async def test_search_levels_and_like(corpus):
    tools = _tools(corpus["scope"])
    with patch(
        "open_notebook.utils.embedding.generate_embedding",
        new=AsyncMock(return_value=VEC_OPT),
    ):
        passages = await tools["search"].ainvoke({"query": "Adam optimizer"})
        sections = await tools["search"].ainvoke(
            {"query": "optimizers", "level": "section"}
        )
    assert passages.splitlines()[1].startswith(f"- {corpus['l4']}#p3")
    assert f"{corpus['l4']}#s1 = {corpus['l4']}#p3" in sections
    related = await tools["search"].ainvoke({"like": corpus["l4"], "level": "document"})
    assert corpus["l6"] in related and f"- {corpus['l4']} " not in related


@pytest.mark.asyncio
async def test_outline_and_read_forms(corpus):
    tools, l4 = _tools(corpus["scope"]), corpus["l4"]
    outline = await tools["outline"].ainvoke({"source": l4})
    assert f"{l4}#s1 = {l4}#p3 Optimizers" in outline and "sequence: 4" in outline
    pages = await tools["read"].ainvoke({"address": f"{l4}#p2-3"})
    assert "--- p2 ---" in pages and "[Image] Algorithm: Adam" in pages
    section = await tools["read"].ainvoke({"address": f"{l4}#s1"})
    assert "Section summary: Adam combines" in section
    summary = await tools["read"].ainvoke({"address": f"{l4}/summary"})
    assert "optimizers such as Adam" in summary
    whole = await tools["read"].ainvoke({"address": l4})
    assert "Sections:" in whole and "--- p1 ---" not in whole  # the map, not the file
    note = await tools["read"].ainvoke({"address": corpus["note"]})
    assert "scales activations" in note


@pytest.mark.asyncio
async def test_view_queues_a_page_image(corpus):
    scope = corpus["scope"]
    out = await _tools(scope)["view"].ainvoke({"address": f"{corpus['l4']}#p3"})
    assert out.startswith("Showing") and len(scope.pending_images) == 1
    assert scope.pending_images[0]["data_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_scope_is_enforced(corpus):
    tools = _tools(corpus["scope"])
    out = await tools["read"].ainvoke({"address": f"{corpus['outside']}#p1"})
    assert out.startswith("Error:") and "not a source in this notebook" in out
    bad = await tools["read"].ainvoke({"address": "lecture 4"})
    assert bad.startswith("Error:") and "source:abc#p12" in bad


@pytest.mark.asyncio
async def test_note_saves_into_the_notebook(corpus):
    from open_notebook.database.repository import ensure_record_id, repo_query

    out = await _tools(corpus["scope"])["note"].ainvoke(
        {
            "title": "Dropout summary",
            "content": "Dropout zeroes units at train time [source:x#p2].",
        }
    )
    assert out.startswith("Saved as note:")
    note_id = out.split()[2]
    linked = await repo_query(
        "SELECT VALUE out FROM artifact WHERE in = $n", {"n": ensure_record_id(note_id)}
    )
    assert [str(x) for x in linked] == [corpus["notebook"]]
    rows = await repo_query(
        "SELECT note_type, title FROM $n", {"n": ensure_record_id(note_id)}
    )
    assert rows[0]["note_type"] == "ai" and rows[0]["title"] == "Dropout summary"


@pytest.mark.asyncio
async def test_visual_page_search_merges_builds(corpus):
    from open_notebook.agent import retrieval
    from open_notebook.database.repository import ensure_record_id, repo_query

    l4, l6 = corpus["l4"], corpus["l6"]
    for source, first, last, vector in (
        (l4, 1, 2, VEC_MIX),  # one animation build: shared vector
        (l4, 3, 3, VEC_OPT),
        (l6, 1, 1, VEC_CNN),
    ):
        await repo_query(
            "UPDATE source_page SET image_embedding = $v WHERE source = $s AND page >= $a AND page <= $b",
            {"v": vector, "s": ensure_record_id(source), "a": first, "b": last},
        )
    with (
        patch.object(
            retrieval, "page_embedding_model", new=AsyncMock(return_value="g")
        ),
        patch(
            "open_notebook.ai.openrouter.embed_multimodal",
            new=AsyncMock(return_value=[VEC_OPT]),
        ),
    ):
        out = await _tools(corpus["scope"])["search"].ainvoke(
            {"query": "algorithm box", "level": "page"}
        )
        like = await _tools(corpus["scope"])["search"].ainvoke(
            {"like": f"{l4}#p3", "level": "page"}
        )
    lines = out.splitlines()
    assert lines[1].startswith(f"- {l4}#p3 ")
    assert f"- {l4}#p1-2 " in out  # the build comes back once, as a range
    assert f"- {l4}#p3 " not in like and f"- {l4}#p1-2 " in like


@pytest.mark.asyncio
async def test_concept_graph_extraction_and_tool(corpus):
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage

    from commands import concept_commands as cmd
    from open_notebook.database.repository import repo_query

    replies = {
        "Regularization": {"concepts": [{"name": "Dropout", "page": 2, "context": "Implicit regularization"}], "relations": []},
        "Optimizers": {
            "concepts": [{"name": "Adam", "page": 3, "context": "Combines momentum and RMSProp"},
                         {"name": "RMSProp", "page": 3, "context": ""}],
            "relations": [{"source": "Adam", "relation": "builds on", "target": "RMSProp", "page": 3}],
        },
        "Residual networks": {"concepts": [{"name": "dropout", "page": 2, "context": "0.5 in AlexNet"}], "relations": []},
    }  # fmt: skip
    model = MagicMock()

    async def answer(prompt):
        section = next(title for title in replies if f'section "{title}"' in prompt)
        return AIMessage(content=json.dumps(replies[section]))

    model.ainvoke = answer
    with (
        patch.object(cmd.AgentSettings, "load", new=AsyncMock(return_value=SimpleNamespace(knowledge_graph=True))),
        patch.object(cmd, "provision_langchain_model", new=AsyncMock(return_value=model)),
        patch.object(cmd, "limit_reasoning", side_effect=lambda m: m),
        patch.object(cmd, "generate_embeddings", side_effect=lambda texts: [[0.1, 0.2, 0.3]] * len(texts)),
    ):  # fmt: skip
        for source in (
            corpus["l4"],
            corpus["l6"],
            corpus["l4"],
        ):  # l4 twice: re-run replaces
            await cmd.extract_concepts_command(
                cmd.ExtractConceptsInput(source_id=source)
            )

    assert len(await repo_query("SELECT * FROM concept")) == 3  # dropout is shared
    assert len(await repo_query("SELECT * FROM concept_mention")) == 4

    tools = _tools(corpus["scope"])
    overview = await tools["graph"].ainvoke({})
    assert overview.splitlines()[1] == "- Dropout: 2 document(s), 2 section(s)"
    with patch(
        "open_notebook.utils.embedding.generate_embedding",
        new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
    ):
        adam = await tools["graph"].ainvoke({"concept": "adam"})
    assert f"- {corpus['l4']}#p3 " in adam
    assert f"- Adam --builds on--> RMSProp [{corpus['l4']}#p3]" in adam

    # Deleting a source removes its part of the graph.
    await repo_query(f"DELETE {corpus['l6']}")
    assert len(await repo_query("SELECT * FROM concept_mention")) == 3


@pytest.mark.asyncio
async def test_notebook_grounding_is_read_by_the_agent(corpus):
    from open_notebook.agent.graph import _notebook_info
    from open_notebook.database.repository import ensure_record_id, repo_query

    assert (await _notebook_info(corpus["notebook"])).get("grounding") is None
    await repo_query(
        "UPDATE $nb SET grounding = 'general'",
        {"nb": ensure_record_id(corpus["notebook"])},
    )
    assert (await _notebook_info(corpus["notebook"]))["grounding"] == "general"

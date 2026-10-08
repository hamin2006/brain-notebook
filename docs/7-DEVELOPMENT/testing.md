# Testing

How the test suites are laid out, how to run them, and the patterns to copy when you add a test.

## Running the tests

```bash
# Backend (repo root)
uv run pytest tests/                                   # what CI runs (plus coverage flags)
uv run pytest tests/test_sources_api.py                # one file
uv run pytest tests/test_sources_api.py -k retry       # tests matching a name
uv run pytest tests/ --cov=open_notebook --cov=api     # with coverage

# Frontend (inside frontend/)
npm run test              # vitest run, once
npm run test:watch        # watch mode
npm run test:coverage     # what CI runs
```

The backend suite needs **no running SurrealDB, worker or AI provider**. CI runs it with nothing but `uv sync`. SurrealDB access, models and HTTP requests are mocked; a few tests use in-memory substitutes instead (for example `InMemorySaver` in `tests/test_empty_model_reply.py`). With an old local `uv`, use `uv run --frozen pytest` so it doesn't re-lock.

Two more layers exist for the research agent: **integration tests** against a real SurrealDB and the **agent eval**
against real models (below).

## Backend layout (`tests/`)

`tests/` is flat: one `test_<topic>.py` per feature or regression, for example `test_sources_api.py`, `test_agent_graph.py`, `test_page_search.py`, `test_concept_graph.py`. The one subfolder is `tests/integration/` (below). Name a new file after what it covers, or add to the existing file for that area.

`tests/conftest.py`:

- sets `OPEN_NOTEBOOK_PASSWORD=""` before anything is imported, so the auth middleware is disabled in tests;
- loads the repo's `.env` if it exists;
- puts the repo root on `sys.path`;
- has one autouse fixture, `stage_writes`: ingestion stage writes (`open_notebook/domain/ingestion.py`) are recorded
  in a list instead of reaching a database. Request the fixture to assert on them (each entry is
  `(source_id, stage, fields)`); tests that need the real writes (and the integration tests) are marked
  `@pytest.mark.real_stage_writes`.

pytest-asyncio runs in its default (strict) mode, so async tests need `@pytest.mark.asyncio`.

## Backend patterns

**API tests** use FastAPI's `TestClient` with a per-file fixture, and patch the domain call the router makes:

```python
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.exceptions import NotFoundError


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@patch("api.routers.notebooks.Notebook.get", new_callable=AsyncMock)
def test_delete_notebook_missing_returns_404(mock_get, client):
    mock_get.side_effect = NotFoundError("not found")
    assert client.delete("/api/notebooks/notebook:gone").status_code == 404
```

(Adapted from `tests/test_crud_404.py`.) Paths include the `/api` prefix. To assert on a 500 instead of having the exception raised into the test, create the client with `TestClient(app, raise_server_exceptions=False)` (see `tests/test_typed_exceptions_reach_handlers.py`).

**Patch where the name is used**, not where it's defined: `api.routers.notebooks.Notebook.get`, `open_notebook.graphs.ask.provision_langchain_model`, and so on. Async functions need `new_callable=AsyncMock` (or an `AsyncMock` as the replacement).

**Graph tests** patch `provision_langchain_model` in the graph module and return a fake model, then call the node function or `await graph.ainvoke(...)` (see `tests/test_ask_graph.py`, `tests/test_graphs.py`).

**Command tests** call the command function directly with its `CommandInput` and patched dependencies (see `tests/test_source_deleted_before_processing.py`, `tests/test_embed_source_partial_cleanup.py`).

**Things that leak between tests:**

- `RecordModel` subclasses (`DefaultModels`, `ContentSettings`, …) are singletons. Call `clear_instance()` in setup/teardown when a test touches one (see `tests/test_domain.py`).
- `provision_provider_keys()` writes to `os.environ`. Use pytest's `monkeypatch.setenv` / `delenv` so environment changes are undone.

**Migrations** can be tested as text, without a database, by reading the `.surrealql` file (see `tests/test_insight_timestamps.py`).

## Agent tests

- **The loop** (`tests/test_agent_graph.py`): a `ScriptedModel` streams scripted replies (text and/or tool calls)
  and records every message list it was sent. `_run(model, tools, writer=…, notebook=…, history=…, attachments=…,
  settings=…)` runs the real graph with `provision_langchain_model` patched to return the scripted research model
  for `"tools"` and the scripted writer for `"chat"`. Assert on `model.calls`, `writer.calls`, emitted events and the
  checkpointed state.
- **Tools** (`test_page_search.py`, `test_concept_graph.py`, `test_agent_rerank.py`, `test_agent_web.py`,
  `test_agent_list.py`): call the tool function with an `AgentScope` and patch the `retrieval` functions.
- **Web** (`test_agent_web.py`): `httpx.MockTransport` for SearXNG and fetched pages; the SSRF guard is tested with
  literal private, Tailscale and metadata addresses and a mocked resolver.
- **MCP** (`test_mcp_server.py`): `mcp.call_tool(name, args)` with `_scope` patched.

## Integration tests (real SurrealDB)

`tests/integration/test_agent_tools_db.py` runs the agent's tools, the concept graph, memory, settings and the
rebuild endpoint against a real SurrealDB with the full migrated schema; `test_ingestion_db.py` covers stage
tracking, the delete cascade, worker recovery and reprocessing plans. It catches SurrealQL behavior mocks can't
(for example `IN` returning no rows on composite-indexed tables). It's skipped unless `SURREAL_TEST_URL` is set:

```bash
docker run -d --rm --name surreal-test -p 127.0.0.1:18000:8000 surrealdb/surrealdb:v2 start --user root --pass root memory
SURREAL_TEST_URL=ws://127.0.0.1:18000/rpc uv run pytest tests/integration -q
docker rm -f surreal-test
```

Each test gets its own database name. Run them whenever you change a query.

## The agent eval

`evals/agent/` measures the whole system against real models over a real notebook: 35 questions about seven
deep-learning lecture decks, covering every task type in the [plan](plans/agentic-rag.md) (locate a fact, read a
diagram, summarize, compare, trace across lectures, enumerate, related documents, metadata questions, homework-style
questions, calculations, saving a note, not-covered questions, follow-ups). Each question lists the lectures,
pages and fact patterns a correct answer must contain (`questions.json`).

```bash
uv run python evals/agent/run_eval.py --mode agent --notebook "AI 360 Deep Learning (agent)" \
  --concurrency 3 --key-file path/to/.env      # key file only to report OpenRouter spend
# --only T4,adam-defaults    subset by task type or id;  --effort deep;  --mode chat|ask for baselines
```

It talks to a running API (`127.0.0.1:5055`), writes one JSON per question plus a summary to
`evals/agent/results/<mode>-<timestamp>/`, and reports: passed, page accuracy (a cited or named page in the expected
range), image-only facts, cites-the-right-document, median latency and spend. The lecture PDFs aren't in the
repository. Latest results are in the [plan](plans/agentic-rag.md#7b-phase-5-as-built-2026-10-07).

When a question fails, read its answer before changing code: several "failures" so far were grader patterns too
strict for a correct answer (LaTeX, wording), fixed in `questions.json`.

## Frontend layout

Tests are colocated with the code as `*.test.ts` / `*.test.tsx` (for example `src/lib/locales/index.test.ts`, `src/components/common/ConfirmDialog.test.tsx`). `frontend/src/test/` holds only the shared setup (`setup.ts`: jest-dom matchers and mocks for `next/navigation`, `matchMedia` and `@/lib/hooks/use-translation`, whose `t()` returns the key itself, so assert on keys rather than English text).

Vitest runs in `jsdom` with globals enabled and the `@/` alias (`frontend/vitest.config.ts`). Use Testing Library to render components; mock API modules rather than the network.

## What to test

- A bug fix comes with a test that fails without the fix. Name it after the behavior (`test_delete_notebook_missing_returns_404`) and reference the issue in the docstring.
- API changes: status codes, validation errors and the error mapping, not only the happy path.
- Don't test third-party libraries (Esperanto, content-core, LangGraph) or make real provider calls.

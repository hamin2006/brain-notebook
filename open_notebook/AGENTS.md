# Backend Rules (api/ + open_notebook/ + commands/ + prompts/)

Normative rules for working on the Python backend. Architecture and design rationale live in [docs/7-DEVELOPMENT/](../docs/7-DEVELOPMENT/index.md) — this file is only what you must know before changing code. Project-wide rules are in the root [AGENTS.md](../AGENTS.md).

## Commands

- Run API: `make api` (runs `run_api.py`: uvicorn with reload on 127.0.0.1:5055; Swagger at http://localhost:5055/docs)
- Background jobs need the worker: `make worker-start` (`python -m commands.worker`: on start it re-queues jobs a stopped worker left `running` and reprocesses outdated sources, then runs the surreal-commands worker)
- Tests: `uv run pytest tests/`
- Lint/format/typecheck: `uv run ruff check . --fix`, `uv run ruff format .` and `uv run python -m mypy .` (CI runs `ruff format --check`)

## API layer (`api/`)

- Routers (`api/routers/`) call domain models and `repo_*` functions directly. Logic goes in an `api/*_service.py` module only when it's shared or orchestrates jobs (`command_service`, `credentials_service`, `podcast_service`). New routers are registered in `api/main.py` with `prefix="/api"`.
- Provider metadata (env vars, modalities, test models, discovery URLs, docs links) lives in the registry: `open_notebook/ai/provider_registry.py` `PROVIDERS`. `TEST_MODELS`, `PROVIDER_ENV_CONFIG`, `PROVIDER_MODALITIES` and `OPENAI_COMPAT_PROVIDERS` are derived from it, and `GET /api/providers` exposes it. Adding a provider takes the registry entry **plus four hand-maintained copies**: the `SupportedProvider` Literal (`api/models.py`), `PROVIDER_CONFIG` (`open_notebook/ai/key_provider.py`), `env_var_map` in `get_provider_availability()` (`api/routers/models.py`) and `PROVIDER_DISCOVERY_FUNCTIONS` (`open_notebook/ai/model_discovery.py`). Tests catch a missing Literal or discovery entry, not the other two. Follow the [Add an AI provider](../docs/7-DEVELOPMENT/change-playbooks.md#playbook-add-an-ai-provider) playbook. The frontend consumes `GET /api/providers` at runtime (`useProviders()`), so a simple API-key provider needs no frontend edit; the registry declaration order is the display order.
- NEVER return API key values from any endpoint — metadata only.
- `api/routers/explore.py` is the UI's read-only view of what ingestion built: `/notebooks/{id}/overview` (counts, most shared concepts), `/notebooks/{id}/concepts/{concept_id}` (mentions, relations), `/notebooks/{id}/graph` (top concepts with home document, relations, strongest co-occurrences) and `/sources/{id}/structure` (metadata, outline, summary, concepts). It reuses `agent/retrieval.py` queries; keep it read-only and cheap (no LLM calls).
- `/sources/{id}/pages/{n}/image` takes `max_side` and `format=jpeg` (thumbnails, about 16 KB) besides PNG.
- `ExecuteChatRequest.context` is legacy and optional: the UI sends only `source_ids` / `note_ids`. Don't make new required request fields the frontend doesn't send; a required `context` once made every chat turn fail with 422.
- Every user-supplied URL field must go through `validate_url()` (`open_notebook/utils/url_validation.py`, async) for SSRF protection. Private IPs/localhost are intentionally allowed (self-hosted Ollama, LM Studio).
- Errors: raise typed exceptions from `open_notebook.exceptions` — global handlers map them to HTTP status codes (`NotFoundError`→404, `InvalidInputError`→400, `AuthenticationError`→401, `UnsupportedTypeException`→415, `RateLimitError`→429, `ConfigurationError`→422, `NetworkError`/`ExternalServiceError`→502, other `OpenNotebookError`→500). Don't raise bare `HTTPException` for domain errors. A router's catch-all `except Exception` (sanitized 500) must come after `except OpenNotebookError: raise` so typed errors reach the handlers (`tests/test_typed_exceptions_reach_handlers.py`).
- Requests over `OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB` (default 100) are rejected by `MaxBodySizeMiddleware` before auth/routing.
- CORS is open by default (`CORS_ORIGINS`); `allow_credentials` flips to `True` only when origins are explicit. No rate limiting built in.

## AI / model provisioning (`open_notebook/ai/`)

- All LLM calls in graph nodes go through `provision_langchain_model()` — never instantiate provider clients directly. It auto-upgrades to `large_context_model` above 105,000 tokens (hard-coded threshold).
- Missing/unconfigured model → raise `ConfigurationError` (not `ValueError`) so the API returns 422.
- Credential-linked models are preferred; `provision_provider_keys()` is the env-var fallback and **mutates `os.environ`** — be aware in tests.
- `DefaultModels.get_instance()` intentionally bypasses the singleton cache (fresh DB fetch each call). `AgentSettings.load()` does the same (API and worker are separate processes).
- Model slots: `tools` = the research agent (cheap, tool calling), `chat` = the answer writer, `transformation` = captions/analysis, `embedding`, `large_context`. Wrap utility calls in `limit_reasoning(model, max_tokens)` (OpenRouter `reasoning.max_tokens`; effort levels are ignored by some models) or reasoning models can return empty replies.
- Rerank and multimodal (image) embeddings go through `open_notebook/ai/openrouter.py`, not Esperanto.

## The research agent (`open_notebook/agent/`)

- Chat, source chat, Ask and MCP all use `agent/graph.py` (async, `AsyncSqliteSaver` from `graphs/checkpoint.py`). Only the question and answer (+ `agent_trace`) are checkpointed; tool traffic, images and attachments (passed in `config["configurable"]`) are not.
- Tools return plain text with addresses and raise `ToolError` for fixable mistakes; never let a tool exception end the turn.
- **Users never see record ids in the research trace.** Steps carry a readable `subject` and results with addresses replaced by document names and pages (`agent/display.py`: live events in `run_loop`, stored traces through `readable_traces` in `api/routers/_chat_shared.py`). Raw `args` stay as they are (the UI counts documents from them); anything new that shows trace text goes through these.
- **SurrealDB quirk:** `WHERE source IN $ids` returns nothing on tables with a composite unique index on `(source, …)` (`source_page`, `source_section`) — use `scope.per_source` (equality per source). Cover new queries with `tests/integration/`.
- `repo_query` returns record ids as strings: wrap with `ensure_record_id()` before comparing against record fields.
- Web fetching must go through `agent/web.py` (public IPs only, per-hop checks, IP pinning), never `validate_url()` (which allows private hosts).
- PDFium (pypdfium2) is not thread-safe: hold `PDFIUM_LOCK` around every call.
- Page extraction (pdfplumber) is pure Python, so threads don't parallelize it (the GIL): `extract_pdf_pages` splits large PDFs into page ranges for a shared spawn-process pool (`OPEN_NOTEBOOK_PDF_PROCESSES`). Keep the per-page work in `_read_page`, picklable and free of module state.

## Graphs (`open_notebook/graphs/`)

- Nodes are `async def`. `source.py` is the ingestion graph (page extraction for PDFs, then the job chain caption → embed → analyze → page images + concepts; analyze queues the last two once the outline is written, so they run beside its summaries). Upstream's `chat.py`, `source_chat.py` and `ask.py` (sync, SqliteSaver) are no longer used by the routers — don't build on them.
- Every node wraps LLM calls with `classify_error()`:
  ```python
  except Exception as e:
      exc_class, message = classify_error(e)
      raise exc_class(message) from e
  ```
- Strip extended-thinking output with `clean_thinking_content()` before using model responses.
- Chat checkpoints live at `./data/sqlite-db/checkpoints.sqlite` — `LANGGRAPH_CHECKPOINT_FILE` in `open_notebook/config.py` is a constant, not an env var.

## Domain (`open_notebook/domain/`)

- `Source.save()` does **NOT** auto-embed — call `source.vectorize()` explicitly (fire-and-forget, returns a command id). `Note.save()` DOES auto-submit `embed_note`.
- `ObjectModel.get()` is polymorphic via ID prefix — the subclass must be imported first or resolution fails. It raises `NotFoundError` **only** for a missing record and `DatabaseOperationError` for any other DB failure ([ADR-013](../docs/7-DEVELOPMENT/decisions/ADR-013-objectmodel-get-error-contract.md)) — so jobs can treat not-found as permanent and DB errors as retryable.
- `RecordModel` subclasses are singletons — call `clear_instance()` in tests.
- Relationship strings passed to `relate()` must match the schema (`reference`, `artifact`, `refers_to`).

## Database (`open_notebook/database/`)

- New migration = new file `open_notebook/database/migrations/N.surrealql` (+ `N_down.surrealql`) **and** an edit to `AsyncMigrationManager` — migrations are hard-coded, not auto-discovered. They run automatically on API startup. The fork's are 26–33; a new source-scoped table also needs a line in the `source_delete` event. **`DEFINE FIELD … DEFAULT` doesn't backfill existing records**, and on a SCHEMAFULL table any later UPDATE of an older row then fails on the missing required field: a new required field ships with an `UPDATE <table> SET <field> = <field> ?? <default> WHERE <field> = NONE`, one statement for all new fields since validation checks the whole record (migration 32 fixed 30/31; covered by `tests/integration/test_ingestion_db.py`). **Backfill big tables in batches** with `AsyncBatchedUpdate` (`async_migrate.py`), not one `UPDATE` in a `.surrealql` file: a statement that runs longer than about 40 s (1,500 pages with image embeddings) drops or hangs the client's websocket, and the API never finishes starting.
- No connection pooling — each `repo_*` call opens/closes a connection.
- Transaction-conflict `RuntimeError`s are retriable and logged at DEBUG (don't "fix" the missing stack trace).
- Bind values as `$params`, never f-string user input into SurrealQL ([security.md](../docs/7-DEVELOPMENT/security.md#database-queries-surrealql-injection)); see the [SurrealQL docs](https://surrealdb.com/docs/surrealql) for syntax.

## Background commands (`commands/`)

- Commands are `@command("<name>", app="open_notebook", retry={...})` functions and must be imported from `commands/__init__.py` (the worker imports that package).
- Retry config uses a blocklist: exceptions in `stop_on` (`ValueError`, `ConfigurationError`, `NotFoundError`, … — check the command's list) fail the job permanently (no retry, job marked `failed`); any other exception auto-retries. Note the embed commands catch `ValueError` internally and return `success=False` (see the comment in `commands/embedding_commands.py`).
- Submission is fire-and-forget via `submit_command()`; commands must be idempotent: a job may run again after a worker restart (the worker re-queues interrupted jobs) or a reprocess.
- **Ingestion stages are tracked** ([ADR-019](../docs/7-DEVELOPMENT/decisions/ADR-019-tracked-versioned-ingestion.md)): a stage command runs inside `tracked(source_id, stage)` and records the next stage with `stage_queued()` beside its `submit_command()` (`open_notebook/domain/ingestion.py`). A change to a stage's code or prompt that existing sources should get **bumps that stage in `STAGE_VERSIONS`** (with the reason in the comment); the next worker start reprocesses outdated sources from that stage. Don't write one-off backfill scripts. A stage that keeps going past a failed page or section (a fallback, an item left out) must call `run.partly_failed(reason)`, never just log it: that records the stage as failed so it is retried, while the job succeeds and the chain continues.
- Prompt templates are cached per process: a prompt change reaches jobs only after the worker restarts (deploys restart it).
- Podcast generation uses `max_attempts: 1` on purpose (prevents duplicate episodes); retry is the explicit `POST /api/podcasts/episodes/{id}/retry` endpoint.

## Prompts (`prompts/`)

- Template path syntax: `Prompter(prompt_template="ask/entry")` → `prompts/ask/entry.jinja` (forward slashes, no extension).
- Data is passed as `data=dict`; dict keys must match template variable names exactly.
- With a `PydanticOutputParser`, Prompter auto-injects `format_instructions` — the template must contain `{{ format_instructions }}` or the parser is silently ignored.
- No template inheritance/composition; templates are flat by design.
- Templates are cached — restart the app after editing.

## Environment knobs to know

| Variable | Meaning |
|---|---|
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` (or `_FILE`) | Required for credential storage; any string, no default |
| `OPEN_NOTEBOOK_CHUNK_SIZE` / `_CHUNK_OVERLAP` | Token-based (default 400 / 15%); restart required |
| `OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB` | Upload cap (default 100) |
| `CORS_ORIGINS` | Restrict before production |
| `SEARXNG_URL` | SearXNG for `web_search` (default `http://127.0.0.1:8888`) |
| `OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS` | Extra `host:port` patterns allowed on `/mcp` |

## Deep dives

[architecture](../docs/7-DEVELOPMENT/architecture.md) · [code standards](../docs/7-DEVELOPMENT/code-standards.md) · [credentials](../docs/7-DEVELOPMENT/credentials.md) · [content processing](../docs/7-DEVELOPMENT/content-processing.md) · [podcasts](../docs/7-DEVELOPMENT/podcasts.md) · [prompts](../docs/7-DEVELOPMENT/prompts.md) · [change playbooks](../docs/7-DEVELOPMENT/change-playbooks.md) · [testing](../docs/7-DEVELOPMENT/testing.md)

# API Reference

Everything the UI does goes through the REST API, so anything you can do in the app you can also script.

**The live OpenAPI schema is the reference.** The running API serves it, generated from the code, so it is always current:

- Swagger UI: `http://localhost:5055/docs` (try requests in the browser)
- ReDoc: `http://localhost:5055/redoc`
- Raw schema: `http://localhost:5055/openapi.json` (for client generators)

This page covers what the schema doesn't tell you: the prefix, auth, async jobs, streaming and errors. It deliberately doesn't list every endpoint.

## Base URL and prefix

All application endpoints are under **`/api`** (every router is mounted with `prefix="/api"` in `api/main.py`). The API listens on port 5055.

- Direct: `http://localhost:5055/api/notebooks`
- Through the frontend: the Next.js server proxies `/api/*` to the API, so `http://localhost:3000/api/notebooks` (or port 8502 in the Docker image) works too.

Outside `/api`: `GET /health` returns `{"status": "healthy"}`, and `GET /` returns a short status message.

## Authentication

If `OPEN_NOTEBOOK_PASSWORD` (or `OPEN_NOTEBOOK_PASSWORD_FILE`) is set, every request needs:

```
Authorization: Bearer <password>
```

```bash
curl http://localhost:5055/api/notebooks -H "Authorization: Bearer $OPEN_NOTEBOOK_PASSWORD"
```

- If no password is set, auth is disabled and all requests pass.
- These paths never need auth: `/`, `/health`, `/docs`, `/redoc`, `/openapi.json`, `/api/auth/status`, `/api/config`. `OPTIONS` (CORS preflight) requests also pass.
- A missing, malformed or wrong header returns `401`.
- Non-ASCII passwords are supported; send them UTF-8 encoded.

This is a single shared password (`api/auth.py`), not user accounts. See [security.md](security.md).

## Resource map

Use `/docs` for request and response shapes. This map shows where things are:

| Area | Paths |
|---|---|
| Notebooks | `/api/notebooks` (incl. `grounding`), `/api/notebooks/{id}/sources/{source_id}` (link/unlink), `/api/recently-viewed` |
| Sources | `/api/sources` (multipart create with optional file upload), `/api/sources/json`, `/api/sources/{id}/status`, `/api/sources/{id}/retry`, `/api/sources/{id}/insights`, `/api/sources/{id}/download`, `/api/sources/{id}/pages/{page}/image` (a rendered PDF page, PNG; `format=jpeg` and `max_side` for thumbnails) |
| Notes, insights | `/api/notes`, `/api/insights/{id}`, `/api/insights/{id}/save-as-note` |
| Chat (research agent) | `/api/chat/sessions`, `/api/chat/execute/stream` (SSE), `/api/chat/execute`; source chat under `/api/sources/{id}/chat/sessions` |
| Research agent | `/api/agent/settings` (GET/PUT), `/api/agent/memories` (GET), `/api/agent/memories/{id}` (DELETE), `/api/agent/rebuild` (POST: `page_embeddings` / `concepts`) |
| Explore (what ingestion built) | `/api/notebooks/{id}/overview` (counts, most shared concepts; `limit`), `/api/notebooks/{id}/concepts/{concept_id}` (mentions, relations), `/api/notebooks/{id}/graph` (top concepts, relations, co-occurrences for drawing), `/api/sources/{id}/structure` (metadata, page count, summary, outline, concepts) |
| Ingestion progress | `/api/notebooks/{id}/ingestion` (per source: stages with status, timing, errors; counts and active stages), `/api/sources/{id}/ingestion`, `POST /api/sources/{id}/ingestion/retry` (re-run from the first failed or outdated stage) |
| MCP | `/mcp` (streamable HTTP, not under `/api`): see [MCP Integration](../5-CONFIGURATION/mcp-integration.md) |
| Search and Ask | `/api/search`, `/api/search/ask` (streaming), `/api/search/ask/simple` |
| Transformations | `/api/transformations`, `/api/transformations/execute`, `/api/transformations/default-prompt` |
| Models and providers | `/api/models`, `/api/models/defaults`, `/api/models/sync`, `/api/models/auto-assign`, `/api/providers` |
| Credentials | `/api/credentials`, `/api/credentials/{id}/test`, `/api/credentials/{id}/discover`, `/api/credentials/{id}/register-models`, `/api/credentials/migrate-*` |
| Podcasts | `/api/podcasts/generate`, `/api/podcasts/episodes`, `/api/episode-profiles`, `/api/speaker-profiles` |
| Background jobs | `/api/commands/jobs`, `/api/commands/jobs/{job_id}` |
| Embeddings | `/api/embed`, `/api/embeddings/rebuild` |
| Settings and config | `/api/settings`, `/api/config`, `/api/capabilities`, `/api/languages`, `/api/auth/status` |

## Async operations

Source processing, embedding and podcast generation run on the background worker (see [architecture.md](architecture.md#ingestion-worker)). The endpoint that starts them returns right away with a record and/or a job id:

- Creating a source with `async_processing=true` (the UI does this) saves it, submits a `process_source` job and returns at once; poll `GET /api/sources/{id}/status` until it is `completed` or `failed`. Without it (the default), the request waits until processing finishes. Either way the later stages (captions, outline, page images, concepts) keep running: `GET /api/sources/{id}/ingestion` reports `complete: true` once every stage is done or skipped.
- `POST /api/podcasts/generate` returns a job id; poll `GET /api/podcasts/jobs/{job_id}` or list `GET /api/podcasts/episodes`.
- Any job: `GET /api/commands/jobs/{job_id}`.

If the worker isn't running, jobs stay queued.

## Streaming

Chat, source chat and Ask stream Server-Sent Events (`text/event-stream`): `data: {json}` lines with a `type` field.

**Notebook chat**, `POST /api/chat/execute/stream`:

| Event | Fields | Meaning |
|---|---|---|
| `step` | `step`, `tool`, `args` | The agent started a tool call (`tool` = `answer` when the writer starts) |
| `step_result` | `step`, `tool`, `summary` | First line of that tool's result |
| `text_delta` | `step`, `text` | Answer text as it's generated |
| `ai_message` | `message` | The saved answer, with `trace` (the steps) |
| `complete` / `error` | `message` on error | End of the turn |

Request fields besides `session_id` and `message`: `effort` (`quick` / `standard` / `deep`), `source_ids` and
`note_ids` (the scope; omit for the whole notebook), `model_override` (the answer model), `images` (up to 4
`data:image/...` URLs, used for this turn only). `context` is accepted for compatibility; only its ids are used.

```bash
curl -N http://localhost:5055/api/chat/execute/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id": "chat_session:...", "message": "What are Adam's defaults?", "context": {}, "effort": "quick"}'
```

**Source chat** forwards the same `step` / `step_result` / `text_delta` events, then `ai_message` with `content`.

**Ask**, `POST /api/search/ask`: `strategy` (the research steps so far), `final_answer`, `complete`, `error`. The
request still takes `strategy_model`, `answer_model` and `final_answer_model`; only the last is used (as the writer).

Check `/docs` for the exact request fields.

## Errors

Errors return JSON with a `detail` message. Domain errors map to status codes in `api/main.py`:

| Status | Meaning (exception) |
|---|---|
| 400 | Invalid input (`InvalidInputError`) |
| 401 | Missing or wrong password, or a provider rejected the API key (`AuthenticationError`) |
| 404 | Record not found (`NotFoundError`) |
| 413 | Request body over `OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB` (default 100) |
| 415 | Unsupported file type (`UnsupportedTypeException`) |
| 422 | Request validation failed, or a model or provider isn't configured (`ConfigurationError`) |
| 429 | Provider rate limit (`RateLimitError`) |
| 502 | Provider unreachable or failed (`NetworkError`, `ExternalServiceError`) |
| 500 | Anything else, including database failures (`DatabaseOperationError`; see [ADR-013](decisions/ADR-013-objectmodel-get-error-contract.md)) |

## Credential encryption migration

After upgrading to 1.15 or later, existing stored API keys can be rewritten into the new encryption format with one call (there is no UI button):

```bash
curl -X POST http://localhost:5055/api/credentials/migrate-encryption \
  -H "Authorization: Bearer $OPEN_NOTEBOOK_PASSWORD"
```

It is idempotent and only rewrites a key it can decrypt. **Back up the database first:** versions before 1.15 can't read the new format. Details: [credentials.md](credentials.md#migration-paths) and [ADR-009](decisions/ADR-009-pbkdf2-credential-encryption.md).

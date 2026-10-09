# Architecture

A map of the codebase: the processes, where each concern lives, and how data flows. Subsystem pages have details:

- [plans/agentic-rag.md](plans/agentic-rag.md): the design of the research agent and ingestion (goals, tool design, findings, eval results, decisions)
- [content-processing.md](content-processing.md): extraction, page-aware ingestion, chunking, embedding
- [credentials.md](credentials.md): provider credentials, encryption, provider registry, provisioning
- [prompts.md](prompts.md): prompt templates and `Prompter`
- [frontend.md](frontend.md): Next.js layers and data flows
- [podcasts.md](podcasts.md): episode and speaker profiles, podcast jobs
- [decisions/](decisions/README.md): why things are the way they are

## Processes

```
Browser / MCP client
   │
   ▼
Next.js frontend ── :3000 (dev or systemd), :8502 in the Docker image
   │  proxies /api/* and /mcp to INTERNAL_API_URL (default http://localhost:5055), 10 min timeout
   ▼
FastAPI API ─────── :5055 (`api/main.py`)                    Background worker
   │  REST, SSE chat streams, /mcp (FastMCP)                  (`python -m commands.worker`)
   │  runs the research agent in-process                       ingestion, embeddings, analysis, page images,
   │  submits jobs ───────────► job queue in SurrealDB ◄──────  concept graph, transformations, podcasts
   ▼                                              │
SurrealDB v2 ────── :8000 ◄───────────────────────┘
   (documents, graph edges, BM25, vectors)

External: AI providers via Esperanto / OpenRouter (rerank, multimodal embeddings);
          SearXNG (optional, :8888 or the compose network) for web search
```

- **Frontend** (`frontend/`): Next.js 16 App Router, React 19, TypeScript, TanStack Query, Zustand, Tailwind 4,
  i18next. Talks only to the API.
- **API** (`api/`): FastAPI. On startup it waits for SurrealDB and runs pending migrations (currently up to 29).
  Serves CRUD, the agent (chat, source chat, Ask) with SSE streaming, the MCP endpoint, and hands long work to the
  worker.
- **Worker** (`commands/`): [surreal-commands](https://github.com/lfnovo/surreal-commands) runs `@command`
  functions from the job queue ([ADR-004](decisions/ADR-004-background-workers.md)).
- **SurrealDB** (v2): documents, graph edges, full-text and vector search in one database
  ([ADR-001](decisions/ADR-001-surrealdb.md)).
- **Chat history**: LangGraph checkpoints in `./data/sqlite-db/checkpoints.sqlite` via an `AsyncSqliteSaver`
  (`open_notebook/graphs/checkpoint.py`). Uploads in `./data/uploads/`, podcast audio in `./data/podcasts/`.

The Docker image runs API, worker and frontend under supervisord; the `single` target also runs SurrealDB. From
source, `scripts/brain/install_services.sh` runs them as systemd user services.

## Backend layout

| Path | What lives there |
|---|---|
| `api/main.py` | App setup: middleware (CORS, body-size limit, password auth), exception handlers, routers (`prefix="/api"`), the `/mcp` route, startup migrations, lifespan (MCP session manager, checkpointer shutdown) |
| `api/routers/` | One module per resource. Agent-related: `chat.py` (`/chat/execute`, `/chat/execute/stream`), `source_chat.py`, `search.py` (Ask), `agent.py` (`/agent/settings`, `/agent/memories`, `/agent/rebuild`), `sources.py` (incl. `/sources/{id}/pages/{page}/image`) |
| `api/mcp_server.py` | FastMCP server: `ask` + the agent's primitives, scoped by notebook |
| `open_notebook/agent/` | **The research agent** (below) |
| `open_notebook/domain/` | Domain models on `ObjectModel` / `RecordModel`: `Notebook` (incl. `grounding`), `Source` (incl. `metadata`), `Note`, `SourceInsight`, `ChatSession`, `Transformation`, `Credential`, settings singletons incl. `AgentSettings` |
| `open_notebook/ai/` | Provider registry, `Model` / `DefaultModels` / `ModelManager`, `provision.py` (`provision_langchain_model`, `limit_reasoning`), `openrouter.py` (rerank and multimodal embeddings over HTTP), key provider, discovery |
| `open_notebook/graphs/` | `source.py` (ingestion graph), `transformation.py`, `prompt.py`, `checkpoint.py`; `chat.py`, `source_chat.py`, `ask.py` are upstream's pre-agent graphs, no longer used by the routers |
| `open_notebook/utils/` | `pdf_pages.py` (page extraction, LaTeXiT decoding, build grouping, rendering), `sections.py` (outline models), `concepts.py` (concept extraction models, aliases), chunking, embedding, encryption, error classification, URL validation |
| `open_notebook/database/` | `repository.py` (`repo_query` etc.; one connection per call) and migrations (`N.surrealql` + `N_down.surrealql`, registered in `async_migrate.py`) |
| `commands/` | Background commands (below) |
| `prompts/` | Jinja templates: `agent/` (system, subagent, review, compact), `sources/` (page caption, outline, section/document summary, concepts), plus upstream's ask/chat/transformation/podcast templates |
| `scripts/brain/` | Deployment: `install_services.sh`, `build_frontend.sh`, `deploy_pc.sh`, `provision_models.py`, `ingest_folder.py`, SearXNG compose |
| `evals/agent/` | The 35-question agent eval (`questions.json`, `run_eval.py`) |

## The research agent (`open_notebook/agent/`)

| Module | Role |
|---|---|
| `graph.py` | The LangGraph graph: one async node, `agent_node`. Loads scope, settings, memories; compacts history; runs `run_loop` with the research model and the tool list; hands the transcript to the answer writer; returns the answer plus a compact trace. `get_agent_graph()` (checkpointed) and `get_ephemeral_agent_graph()` (Ask, MCP) |
| `tools.py` | The primitives: `list`, `grep`, `search` (passage/section/document/page, `like`, `image`), `outline`, `read`, `view`, `graph`, `note`, `calculate`; arg schemas (`AddressList` accepts stringified lists); `build_tools(scope)` |
| `retrieval.py` | Search backends: BM25 + vector legs, reciprocal rank fusion, rerank, section/document rows, page-image hits, concept graph queries |
| `scope.py` | `AgentScope` (sources, notes, notebook, attachments, pending images), `load_scope`, `per_source` (per-source equality queries; see below) |
| `addresses.py` | Address parsing/formatting (`source:abc#p12-18`, `#s3`, `/summary`, `note:xyz`) |
| `memory.py` | Memory recall/save/delete and the `remember` / `forget` tools |
| `web.py` | SearXNG search, SSRF-safe fetching (public IPs only, per-hop checks, IP pinning), page/PDF text extraction, the web tools |
| `sessions.py` | Chat-session helpers on the async checkpointer |

### A turn

```
agent_node(state, config)
  ├─ scope = load_scope(source_ids, note_ids, notebook)      # what may be read
  ├─ settings, memories, notebook grounding
  ├─ compact older messages into state.summary (research model)
  ├─ tools = build_tools(scope) + delegate [+ remember/forget] [+ web_search/web_read]
  ├─ run_loop(research model, tools, transcript, max_steps by effort, reviewer if deep)
  │     each step: model.bind_tools → tool calls (parallel) → results appended;
  │     viewed page images injected as a HumanMessage; repeated calls deduped;
  │     emits {"type": "step"|"step_result"} through the LangGraph stream writer
  └─ answer_writer(chat model): flattened transcript + answer rules → streamed text_delta
→ state.messages += AIMessage(answer, additional_kwargs.agent_trace); summary/summarized
```

Only the question and answer (plus trace) are checkpointed; tool traffic, images and attachments (passed in
`config["configurable"]["attachments"]`) are not. Delegated sub-agents run `run_loop` with a single-source scope and
no writer.

### Models

`provision_langchain_model(content, model_id, default_type)` picks a model: content over 105K tokens → the
`large_context` default; else an explicit `model_id`; else the default for `default_type`. The agent uses `tools`
for research and `chat` (or the session override) for the answer; ingestion uses `transformation` (captions,
analysis) and `tools` (concepts). `limit_reasoning(model, max_tokens)` sets OpenRouter's `reasoning.max_tokens`
(2,048 per research step, 3,072 for the writer, 1,024 for utility calls). Errors go through `classify_error()` into
typed exceptions the API maps to status codes.

## Ingestion (worker)

```
process_source ─► graphs/source.py: extract (PDF → per-page via pdfplumber in a process pool; others → content-core)
                    └─ save_source: store source_page rows
                         ├─ visual pages? ─► caption_pages ─► vectorize ─► analyze_source
                         └─ otherwise ─────► vectorize ─────────────────► analyze_source (paged sources)
analyze_source ─► outline + metadata ─┬─► section summaries ─► document summary insight
                                      ├─► embed_pages        (page-image embeddings)
                                      └─► extract_concepts   (concept graph)
embed_source / embed_note / embed_insight, run_transformation, create_insight, rebuild_embeddings, generate_podcast
```

Each stage of a source (extract, caption, embed, analyze, page_images, concepts) records its state, timing and
version in `source_stage` (`open_notebook/domain/ingestion.py`); the API serves it at `/sources/{id}/ingestion` and
`/notebooks/{id}/ingestion`. The worker entrypoint (`commands/worker.py`) re-queues jobs a stopped worker left
`running` and restarts sources whose stage versions are outdated ([ADR-019](decisions/ADR-019-tracked-versioned-ingestion.md)).
Throughput and memory (8 job slots, per-document concurrency, the parser pool, caps per service) are in
[ADR-020](decisions/ADR-020-ingestion-throughput-and-memory.md).

Details: [content-processing.md](content-processing.md), [concept/ingestion](../2-CORE-CONCEPTS/ingestion.md).

## Data model

From the migrations (read them for exact fields). Upstream tables plus Brain Notebook's (migrations 26–33):

| Table | Holds |
|---|---|
| `notebook` | Name, description, `archived`, `grounding` |
| `source` | `title`, `full_text`, `asset` (file path or URL), `metadata` (doc type, course, sequence, topics, page count…), `command` |
| `source_page` | Per page: `text`, `equations`, `image_ratio`, `shapes`, `garbled`, `caption`, `caption_version`, `image_embedding`; unique `(source, page)` |
| `source_stage` | Ingestion progress, one row per source and stage: `status`, `version`, `queued_at` / `started_at` / `finished_at`, `error`, `detail` |
| `source_embedding` | Chunks: `order`, `content`, `embedding`, `page_start`, `page_end` |
| `source_section` | Outline sections: `index`, `title`, `page_start`, `page_end`, `summary`, `embedding`; unique `(source, index)` |
| `source_insight` | Transformation output, incl. the "Document Summary" from analysis |
| `concept`, `concept_alias` | Concepts (id derived from the normalized name) and their alternative names |
| `concept_mention`, `concept_relation` | Where a concept appears (source, section, pages) and stated relations between concepts |
| `memory` | Agent memories (`notebook` or none = everywhere), embedded |
| `note`, `chat_session`, `transformation`, `model`, `credential`, podcast tables | As in upstream Open Notebook |
| `open_notebook:*` records | Singletons: `default_models`, `content_settings`, `agent_settings`, … |

Graph edges: `reference` (source → notebook), `artifact` (note → notebook), `refers_to` (chat session → notebook or
source). The `source_delete` event removes a source's pages, chunks, sections, insights and graph rows.

**SurrealDB v2 quirk:** `WHERE source IN $ids` returns no rows on tables with a composite unique index on
`(source, …)` (`source_page`, `source_section`). Query those per source with equality (`scope.per_source`).
Integration tests (`tests/integration/`) run the real queries against SurrealDB.

## Request paths

- **Chat**: `POST /api/chat/execute/stream` → `_prepare_turn` (session, scope, attachments) → agent graph
  `astream(stream_mode=["custom", "values"])` → SSE events `step`, `step_result`, `text_delta`, `ai_message`,
  `complete` / `error`. A failed turn removes the question from the checkpoint. `/chat/execute` is the non-streaming
  variant.
- **Ask**: `POST /api/search/ask` → ephemeral agent graph; steps are streamed as the strategy, the answer as the
  final answer.
- **MCP**: `/mcp` → FastMCP tools call the same tool functions with a notebook scope, or the ephemeral graph for `ask`.
- **Middleware**: `CORSMiddleware` → `MaxBodySizeMiddleware` (413 over `OPEN_NOTEBOOK_MAX_UPLOAD_SIZE_MB`) →
  `PasswordAuthMiddleware` (Bearer, if a password is set) → router. Typed exceptions map to status codes in
  `api/main.py`; see [api-reference.md](api-reference.md#errors).

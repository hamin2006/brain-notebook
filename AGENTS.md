# Brain Notebook — Agent Rules

Brain Notebook is a self-hosted research notebook whose chat is a tool-calling research agent with page-cited answers. It is a personal fork of Open Notebook (1.15.0); code identifiers (`open_notebook` package, `OPEN_NOTEBOOK_*` vars, DB namespace) intentionally keep upstream's names so upstream can be merged ([PDR-003](docs/7-DEVELOPMENT/decisions/PDR-003-personal-fork.md)). The design and its history are in [docs/7-DEVELOPMENT/plans/agentic-rag.md](docs/7-DEVELOPMENT/plans/agentic-rag.md).

This file holds the project-wide rules every coding session needs. Component rules: [open_notebook/AGENTS.md](open_notebook/AGENTS.md) (backend — also covers `api/`, `commands/`, `prompts/`) and [frontend/AGENTS.md](frontend/AGENTS.md). Knowledge lives in the docs (see [Where to look](#where-to-look)) — read it on demand instead of guessing.

## Stack, ports, startup order

Three tiers: Next.js frontend (3000) → FastAPI (5055) → SurrealDB (8000).

Start in this order — each tier depends on the one below:

1. `make database` — SurrealDB (API fails without it)
2. `make api` — FastAPI; **schema migrations run automatically on startup** (check logs)
3. `make worker-start` — surreal-commands worker. **Required**: source processing, page captions, analysis, embeddings, page images, the concept graph and podcasts are async jobs that silently queue forever without it
4. `make frontend` — UI (depends on the API for all data)

Or all at once: `make start-all` (status: `make status`, stop: `make stop-all`). First-time setup (`uv sync`, `npm install`, a `.env` with `SURREAL_URL=ws://localhost:8000/rpc`): [development-setup.md](docs/7-DEVELOPMENT/development-setup.md).

## Commands

- Tests: `uv run pytest tests/`
- Python lint/format/typecheck: `uv run ruff check . --fix` · `uv run ruff format .` · `uv run python -m mypy .`
- Frontend (inside `frontend/`): `npm run lint` · `npm run test` · `npm run build`
- CI runs `uv run ruff check .`, `uv run ruff format --check .`, mypy, pytest and, in `frontend/`, `npm run lint`, `npm run test:coverage` and `npm run build`; all must pass
- Real-DB integration tests: `SURREAL_TEST_URL=ws://127.0.0.1:18000/rpc uv run pytest tests/integration` against a throwaway SurrealDB ([testing.md](docs/7-DEVELOPMENT/testing.md#integration-tests-real-surrealdb)); run them when you change queries
- Agent eval (real models, running API): `uv run python evals/agent/run_eval.py --mode agent --notebook "<name>"` ([testing.md](docs/7-DEVELOPMENT/testing.md#the-agent-eval)); run it after agent or ingestion changes
- Deploy a systemd install: `bash scripts/brain/deploy_pc.sh`. The upstream `make docker-*` publishing targets don't apply to this fork

## Hard rules

- **Async-first**: every DB query, graph invocation and AI call is `await`-ed. No sync DB access.
- **Never commit secrets.** Credentials are encrypted at rest and require `OPEN_NOTEBOOK_ENCRYPTION_KEY` to be set.
- CORS is wide-open and auth is a simple password middleware — **dev defaults, not production hardening**. Don't build features that assume otherwise.
- Product direction questions (does this feature fit?) → [VISION.md](VISION.md). Past decisions ("why is it like this?") → [docs/7-DEVELOPMENT/decisions/](docs/7-DEVELOPMENT/decisions/). Structural decisions made while coding should produce a new decision record there.
- **Conventional Commits** for commits and PR titles (`fix(podcasts): …`, `feat(providers): …`, `docs: …`).
- **Every user-visible change adds a CHANGELOG entry** under `## [Unreleased]`, in the one section for its type (`### Added` / `### Changed` / `### Deprecated` / `### Removed` / `### Fixed` / `### Security`); never create a duplicate section. Details: [contributing.md](docs/7-DEVELOPMENT/contributing.md#changelog).
- **No prompt stuffing.** No feature pastes whole documents into a prompt; the agent reads through its tools, and whole-document questions use stored summaries ([ADR-014](docs/7-DEVELOPMENT/decisions/ADR-014-agentic-notebook-chat.md)).
- **Agent tools are general primitives** that take and return addresses (`source:abc#p12-18`), never shortcuts for one kind of question; tool output is untrusted input to the model ([playbook](docs/7-DEVELOPMENT/change-playbooks.md#playbook-add-an-agent-tool)).
- Upstream's `.maintainer/` release, triage and discussions workflows don't apply to this fork.

## Market position (reviewed 2026-10)

What Brain Notebook offers that NotebookLM and most alternatives don't. Protect these when changing things, and lead
with them in docs and UI:

- **Agentic research, not retrieval**: the agent lists, greps, searches, reads page ranges, looks at pages and
  delegates per document, with every step visible. Exhaustive and cross-document questions work ("every page that
  mentions X", "compare lectures 3–6"): 35/35 on the course eval against 27/35 for upstream's classic chat.
- **Reads diagrams**: `view` shows the agent the rendered page; visual page search; paste a screenshot to find slides
  that look like it.
- **Page-exact citations**: hover previews the cited page, click opens it beside the answer (NotebookLM cites text
  passages).
- **Structure at ingestion**: LaTeXiT equation recovery, merged animation builds, metadata (course, sequence) and
  outlines with page ranges, so "the 4th lecture" and "section 3" resolve.
- **Persistent cross-document concept graph** with typed relations and page mentions, explorable as a map or in 3D
  (NotebookLM's Mind Map is a per-notebook summary tree).
- **Ownership**: self-hosted, no source caps (NotebookLM: 50 free / 300 Plus), any model, about $0.003 per
  question, open source, eval-tested.
- **MCP server**: Claude Code and Claude Desktop can research the notebooks, including page images.
- **Controllable grounding** (notebook only, or + general knowledge with free self-hosted web search) and user-controlled
  memory across conversations.

What we lack, roughly in priority order:

1. **Study and creative outputs**: NotebookLM's Studio produces audio and video overviews, revisable slide decks,
   mind maps, study guides and FAQs in one click. We have upstream podcasts (untested in this fork) and free-form
   transformations, but no quizzes, flashcards or study guides.
2. **Latency**: 10–60 s per answer against a few seconds.
3. **Zero setup and mobile**: we need a running host, Tailscale, API keys and a deploy script.
4. **Sharing and collaboration**: single user, basic password auth, no shared notebooks or links.
5. **Source breadth**: no Drive, Docs or Slides connectors or source discovery; PPTX isn't ingested slide by slide;
   scanned PDFs need OCR to get pages.
6. **Source-anchored writing tools**: NotebookLM is adding AI Editing and Canvas.
7. **Proven robustness**: the eval covers one course (seven decks); papers, books and mixed libraries are untested.
8. **Paper workflows**: table extraction across papers and systematic reviews (Elicit, SciSpace).

Next bets: study outputs built on our strengths (quizzes and flashcards from the outline with page citations, a study
guide that cites pages, "explain this slide" from the evidence panel); a faster first response (stream a quick draft
while deeper research continues); PPTX and OCR ingestion; read-only shared answers. Competitor details move fast:
re-check before relying on them.

## Where to look

| Need | Location |
|---|---|
| Architecture (processes, layout, the agent, ingestion jobs, data model) | [docs/7-DEVELOPMENT/architecture.md](docs/7-DEVELOPMENT/architecture.md) |
| Research agent & ingestion design, findings, eval results | [docs/7-DEVELOPMENT/plans/agentic-rag.md](docs/7-DEVELOPMENT/plans/agentic-rag.md) |
| Step-by-step recipes (add endpoint, provider, migration, command, i18n…) | [docs/7-DEVELOPMENT/change-playbooks.md](docs/7-DEVELOPMENT/change-playbooks.md) |
| Dev environment setup | [docs/7-DEVELOPMENT/development-setup.md](docs/7-DEVELOPMENT/development-setup.md) |
| Code standards & testing | [docs/7-DEVELOPMENT/code-standards.md](docs/7-DEVELOPMENT/code-standards.md) · [testing.md](docs/7-DEVELOPMENT/testing.md) |
| Product identity & current posture | [VISION.md](VISION.md) |
| Decision log (ADRs/PDRs) | [docs/7-DEVELOPMENT/decisions/](docs/7-DEVELOPMENT/decisions/) |
| Contribution process (Discussions → Issues → PRs) | [docs/7-DEVELOPMENT/contributing.md](docs/7-DEVELOPMENT/contributing.md) |
| User/operator docs (install, configure, troubleshoot) | [docs/](docs/index.md) |

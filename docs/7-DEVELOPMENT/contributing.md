# Contributing to Brain Notebook

Brain Notebook is a personal fork of [Open Notebook](https://github.com/lfnovo/open-notebook). Issues and pull
requests are welcome at https://github.com/hamin2006/brain-notebook; for changes that aren't specific to the research
agent or the ingestion pipeline (providers, extraction, podcasts, general UI), consider contributing to upstream Open
Notebook instead, where more people benefit and the fork picks them up on the next merge.

- **Bugs**: open an issue with steps to reproduce, the exact error, relevant logs (no keys or passwords), the version
  (Settings → Advanced) and how you run it.
- **Ideas and larger changes**: open an issue describing the problem first. The design notes in
  [plans/agentic-rag.md](plans/agentic-rag.md) and the [decision records](decisions/README.md) explain why things are
  the way they are; new tools should be general primitives, not shortcuts for one kind of question.
- **Small fixes** (typos, docs, obvious bugs): just open a PR.

## Development Workflow

Set up your environment with [development-setup.md](development-setup.md). Then:

1. **Branch from an up-to-date `main`**, named after the change type: `feat/...`, `fix/...`, `docs/...`.
2. **Make the change** following [code-standards.md](code-standards.md) and, for common change types, the matching
   [playbook](change-playbooks.md) (including [adding an agent tool](change-playbooks.md#playbook-add-an-agent-tool)).
3. **Add tests** ([testing.md](testing.md)): unit tests always; integration tests for new queries; run the agent eval
   for changes to the agent or ingestion, and report its summary in the PR.
4. **Update the docs** your change affects and **add a CHANGELOG entry** (below).
5. **Run the checks** (below), push and open a PR against `main`.

AI-assisted contributions are fine; you're responsible for every line, the tests, and the PR description being
accurate.

### Commit messages and PR titles

[Conventional Commits](https://www.conventionalcommits.org/), with a scope when one fits:

```text
feat(agent): visual page search and image attachments in chat
fix(concepts): parse concept JSON that contains LaTeX, retry once
docs(config): research agent settings, MCP, env vars
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `perf`. Keep the first line under about 72
characters and describe the effect; explain the why in the body.

### CHANGELOG

Every user-visible change adds an entry to `CHANGELOG.md` under `## [Unreleased]`, in the one section for its type
(`### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security`). Write it for users and
operators: what changed and what they need to do. Purely internal changes usually need no entry.

### Before you open a PR

Run what CI runs:

```bash
# Backend (repo root)
uv run ruff check .
uv run ruff format --check .     # fix with: uv run ruff format .
uv run python -m mypy .
uv run pytest tests/

# Frontend (inside frontend/), if you touched it
npm run lint
npm run test
npm run build
```

If you changed queries: the [integration tests](testing.md#integration-tests-real-surrealdb). If you edited docs:
`python3 scripts/check_md_links.py` (relative links must resolve). New UI strings need keys in all 14 locales (the
parity test checks).

## Merging upstream

```bash
git fetch upstream
git merge upstream/main
```

Expect conflicts in files the fork rewrote (`api/routers/chat.py`, `source_chat.py`, `search.py`,
`open_notebook/graphs/source.py`, the chat UI). Migrations are numbered in one sequence: renumber upstream's new
migrations after the fork's (currently 29) and register them in `async_migrate.py`. Run the full test suite and the
agent eval after a merge.

## Code of Conduct

See [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md).

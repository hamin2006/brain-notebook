# PDR-003: Brain Notebook is a personal fork that keeps upstream's identifiers

- **Status**: Accepted
- **Date**: 2026-10

## Context

Brain Notebook started as a fork of Open Notebook 1.15.0 to build an agentic research notebook. It replaces core
behavior (chat, Ask, ingestion) rather than extending it, so it can't be an upstream contribution as is, but upstream
keeps fixing providers, extraction and the UI.

## Decision

- Brain Notebook is its own app (name, version 2.0.0, repository, docs, update check), credited to Open Notebook.
- **Code identifiers keep upstream's names** (the `open_notebook` package, `OPEN_NOTEBOOK_*` variables, the database
  namespace, service names in compose) so upstream changes can still be merged.
- **No classic-chat fallback**: no mode pastes whole documents into a prompt.
- Provider-specific features (OpenRouter rerank and multimodal embeddings, reasoning budgets) are allowed when they
  degrade gracefully ([PDR-002](PDR-002-provider-agnostic-core.md) still holds for the core: chat and embeddings work
  with any provider).
- Upstream's release machinery (image publishing, maintainer workflows) doesn't apply; deployments build from source.

## Consequences

- Merging upstream means conflicts in rewritten files (chat routers, source graph, chat UI); keep those changes
  isolated in `open_notebook/agent/`, `commands/` and new modules where possible.
- Users must not use upstream images; the compose file builds this repository.

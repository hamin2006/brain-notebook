# ADR-017: Agent extensions are optional, settings-driven and OpenRouter-backed

- **Status**: Accepted (Brain Notebook)
- **Date**: 2026-10
- **Related**: [plans/agentic-rag.md](../plans/agentic-rag.md) §7b

## Context

Phase 5 added reranking, page-image embeddings (visual search), a concept graph, memory, web search and an MCP
server. Each costs something (money, latency, an external dependency) and not every deployment can provide it
(local-only setups have no rerank or multimodal embedding models in Esperanto).

## Decision

- Each extension is **switchable at runtime** in `AgentSettings` (Settings → Research agent), read fresh per call
  because the API and worker are separate processes. Empty model id = off; the agent degrades to the fused search
  order, text-only search, no graph tool, no memory tools, no web tools.
- **Rerank and multimodal embeddings call OpenRouter's HTTP API directly** (`ai/openrouter.py`) with the stored
  OpenRouter credential, instead of extending Esperanto's model types.
- **Web search is self-hosted** (SearXNG): no key, no per-search cost. Fetching is restricted to public addresses
  with per-hop checks and IP pinning; tools are offered only in notebooks that allow general knowledge.
- **The concept graph keys concepts by normalized name** (deterministic record ids, aliases for abbreviations)
  so lookups are direct record fetches and parallel jobs converge.
- **MCP is served by the API itself** (FastMCP at `/mcp`, stateless JSON), exposing the same tool functions.

## Alternatives considered

- **New Esperanto model types for rerank / multimodal embeddings**: more work across providers for features only
  OpenRouter offered cheaply.
- **A hosted web search API**: simpler, but ~$0.02 per search.
- **A separate MCP process wrapping the REST API** (like the community `open-notebook-mcp`): another service to run,
  and the REST API doesn't expose the agent's primitives.

## Consequences

- Without an OpenRouter credential two features are off unless their models are cleared; the docs say so.
- Settings live in the database, not env vars; backfills are explicit (`/api/agent/rebuild`).
- The graph's quality depends on extraction prompts; rebuilds with `reset` apply improvements to old documents.

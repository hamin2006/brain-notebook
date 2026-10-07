# ADR-014: Notebook chat is a tool-calling research agent

- **Status**: Accepted (Brain fork)
- **Date**: 2026-10
- **Related**: [plans/agentic-rag.md](../plans/agentic-rag.md)

## Context

Notebook chat pasted the full text or insights of every source ticked in the UI into one prompt and made one model call. Nothing outside the selection could be found, long documents blew the context (one 113-slide lecture extracted to ~60k tokens of mostly LaTeXiT junk), and answers couldn't cite pages. Ask searched, but planned once and never read further.

## Decision

**Notebook chat runs an agent graph (`open_notebook/agent/graph.py`)**: the model calls general tools over the notebook until it can answer or its effort budget (quick 4 / standard 10 / deep 20 tool steps) runs out, then answers with citations.

- **Tools are primitives, not tasks** (`agent/tools.py`): `list`, `grep`, `search` (passage / section / document, `like=`), `outline`, `read`, `view`. Summaries, comparisons, "related lectures" etc. are compositions of these.
- **One address format** (`agent/addresses.py`) for tool inputs, outputs and citations: `source:abc#p12-18`, `#s3`, `/summary`, `note:xyz`.
- **No whole-file loading**: reading a bare document returns its outline and stored summary; whole-document questions use the summaries built at ingestion.
- **The selection is a scope, not a payload**: ticked sources/notes limit what the tools can reach; no selection means the whole notebook.
- **Only the question and the final answer are checkpointed** (with a compact step trace in `additional_kwargs.agent_trace`). Tool results and viewed images live inside the turn.
- **Async graph on `AsyncSqliteSaver`** (`graphs/checkpoint.py`), sharing the sync saver's file and schema so existing threads stay readable.
- **Streaming** via LangGraph custom events (`step`, `step_result`, `text_delta`) on `POST /api/chat/execute/stream`; `POST /api/chat/execute` keeps its contract.

## Alternatives considered

- **Keep context stuffing as a fallback mode**: rejected; it is the failure mode this replaces, and two chat modes double the surface.
- **LangGraph prebuilt agent (agent ⇄ tools nodes)**: rejected for now; checkpointing every tool message and image would bloat history, and the single-node loop keeps images ephemeral and the trace compact.
- **RAGFlow's fixed multi-phase pipeline**: its sufficiency review and query rewrite are planned for the Deep effort level (plan phase 4); a model-driven loop covers Quick/Standard with far less machinery.

## Consequences

- Answers depend on the model's tool-calling quality; the eval set (`evals/agent`) measures it per task type.
- More model calls per turn (one per step). Effort levels bound cost and latency.
- Source chat and Ask still use their original graphs until plan phase 4 moves them onto the agent.

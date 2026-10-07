# Plan: Agentic RAG for Open Notebook (fork `hamin2006/open-notebook`)

Status: **final (v1), approved 2026-10-06** · Branch: `agentic-rag`

Changes to scope or decisions are recorded in §8 rather than by rewriting earlier sections.

## 1. Goal

Turn Open Notebook's chat from "paste the selected sources into one prompt" into a
research agent that can find documents, read them, look at their pages, and answer
with page-level citations, across a whole notebook.

### Task coverage (what the agent must handle; the tools are designed from this, not from single queries)

Corpus: study material (lecture decks, papers, textbook chapters, personal notes, transcripts).

| # | Task type | Example |
|---|---|---|
| T1 | Fact lookup | "What momentum does lecture 4 recommend?" |
| T2 | Grounded explanation | "Explain backprop the way lecture 2 does" |
| T3 | Locate | "Which slide shows the bottleneck block?" |
| T4 | Visual reading | Diagrams, plots, tables, equations on slides |
| T5 | Summarize at any scale | A slide range, a section, a lecture, the whole course |
| T6 | Compare | "How do lectures 3 and 4 treat regularization?" |
| T7 | Trace a concept | "How does invariance develop across the course?" |
| T8 | Exhaustive enumeration | "Every optimizer mentioned in the course", "Which lectures use CIFAR-10?" |
| T9 | Relatedness / prerequisites | "What should I review before lecture 6?" |
| T10 | Questions about documents themselves | "Which lecture is longest?", "What came after the CNN lecture?" |
| T11 | Query from the user's material | Pasted homework problem or screenshot: "Which lecture covers this?" |
| T12 | Generate study material | Quiz / flashcards from lecture 3 |
| T13 | Compute / verify math | "Is this gradient right?", "Output size of this conv layer?" |
| T14 | Save results | "Save this to my notes on lecture 4" |
| T15 | Out of scope | Says it isn't in the notebook (or uses web search if enabled) |
| T16 | Follow-ups and ambiguity | "What about the next one?"; asks "which course?" when unclear |

The eval set (§6) samples every task type. Every answer cites addresses with page numbers (§4.2), and the UI shows the agent's steps live.

## 2. What the deep dive found

### Open Notebook today (verified in code and on the real lecture PDFs)

| Area | Finding | Consequence |
|---|---|---|
| Chat (`graphs/chat.py`) | One `model.invoke()`; context = full text or insights of the sources ticked in the UI | Not retrieval at all; scales badly; nothing outside the selection is found |
| Ask (`graphs/ask.py`) | Plan ≤5 search terms → vector search each → combine; one pass, no loop | Closest to agentic, but no follow-up, no reading, no tools (`bind_tools` commented out) |
| Streaming | Source chat "streams" one event after the whole turn finishes; notebook chat doesn't stream | Need real SSE with step and token events |
| Checkpointer | Sync `SqliteSaver`, sync nodes + new-event-loop workaround (flagged fragile in `AGENTS.md`) | Move chat to `AsyncSqliteSaver` (`aiosqlite` is already a dependency) |
| Extraction (`content-core`) | **No page boundaries** in `full_text` (tested on Lecture 4) | Chunks can't be tied to pages: no page citations, can't jump to the slide |
| Extraction | Lecture 4: content-core returned **238,608 chars**; PyMuPDF finds **31,523** chars of text on its 113 pages | Unexplained 7.5× inflation (OCR of embedded textbook images? duplication?). Must be explained before trusting retrieval |
| Extraction | Math garbled (sub/superscripts split onto separate lines) | Hurts retrieval on equations; vision fallback for math-heavy pages |
| Chunking | ~400-token recursive/markdown splitting; `source_embedding.order` stored | Neighbor reads are possible; slides should be per-page chunks instead |
| Search (`fn::text_search` / `fn::vector_search`) | Results **grouped per source**, chunk identity and position dropped; BM25 and vector never fused | Need chunk-level hybrid search for the agent (UI search can stay as is) |
| Vector index | None; cosine is computed against every row | Fine for thousands of chunks; add HNSW later if needed |
| Document metadata | Only `title` (= filename), `topics`, `asset` | "4th lecture", "course", dates aren't queryable fields |
| Summaries | Transformations exist (Dense Summary, Table of Contents, …) and their insights are embedded | A base for document-level summaries and relatedness, but generated over full_text in one call |
| Uploads | `auto_delete_files` defaults to `"yes"` | Originals vanish, so the agent can't view pages. Fork default → `"no"` |
| Citations | UI parses `[source:x]`, `[note:y]`, `[source_insight:z]` (`lib/utils/source-references.tsx`) | Extend with a page suffix, e.g. `[source:x#p48]` |
| Conventions | Provider-agnostic core, API-first, async-first, typed errors, ADRs for structural decisions, CHANGELOG, **i18n keys in all 14 locales** | Kept where they protect quality (tests, CI, typed errors, ADRs); relaxed for this personal fork per §8 decision 2 |

### RAGFlow capabilities, and what we take

| RAGFlow capability | Take? | How it maps here |
|---|---|---|
| Agentic research pipeline: formalize question → plan → prefetch → research session → draft with an explicit `MISSING:` list → sufficiency review (SUFFICIENT / INSUFFICIENT / UNKNOWN) → query rewrite → loop → compose from budgeted evidence | **Yes, simplified** | Our graph (§4.3); "deep" effort enables the review loop |
| Thinking modes None/Low/Medium/High/Ultra | **Yes** as Quick / Standard / Deep | Step and time budgets, whether the review loop runs |
| Evidence-first prompt rules (deep-read before citing, rephrase empty searches, stop when reads stop changing the answer) | **Yes** | System prompt |
| Tools: hybrid search, list/read chunks with neighbors, `fetch_full_document`, `summarize_document`, `metadata_search`, `navigate_tree`/PageIndex, `graph_explore`, `wiki_query`, calculator, web search | **Most, not whole-document loading** | §4.2 primitives; `fetch_full_document`/`summarize_document` replaced by stored summary layers (no full-file context); graph/wiki later; web search optional |
| Hybrid retrieval: weighted vector+BM25, similarity threshold, top-N, rerank candidates, rerank model | **Yes** (RRF first; rerank optional) | §4.1 |
| Query augmentation: keyword extraction, multi-turn rewrite, cross-language | **Multi-turn rewrite yes**; keywords via the agent; cross-language later | §4.3 |
| "Presentation" parser: one chunk per slide/page | **Yes** | §3.1, critical for lecture decks |
| VLM-assisted PDF/table/image parsing | **Yes, opt-in per page** | §3.2 |
| Transformer at ingestion: summary, keywords, generated questions, metadata | **Summary + metadata yes**; keywords/questions later (cost) | §3.3–3.4 |
| Knowledge compilation: Tree (RAPTOR), PageIndex, mind map, graph, timeline, wiki | **PageIndex/outline + doc summary tree yes**; graph later; others no | §3.4, Phase 5 |
| Document metadata, auto-metadata, metadata filters | **Yes** | §3.3 |
| Raw-chunk memory store, doc metadata stamped on evidence | **Yes** (evidence ledger) | §4.3 |
| Memory layer (raw/semantic/episodic/procedural) | **Later** (conversation compaction now) | Phase 5 |
| Retrieval testing UI, golden-set metrics | **Yes, as an eval harness** (CLI first) | §6 |
| Related searches, AI summary of search results | Later | |
| Connectors (45), teams/permissions, agent canvas, chat channels, ES/NATS/ClickHouse/MinIO infra | **No** | Out of scope for a personal tool |

## 3. Ingestion: document understanding

### 3.1 Page-aware extraction and chunking
- New table `source_page` (`source`, `page`, `text`, `char_start`, `char_end`, `kind` = text / figure / mixed). Filled for PDFs with pypdfium2 (already a dependency) alongside content-core; PPTX support later (per-slide extraction or PDF conversion).
- `source_embedding` gains `page_start` / `page_end` (migration + backfill).
- **Slide-deck mode** (auto-detected: uniform landscape pages, low text density): one chunk per page, merging near-empty pages with the next one. Documents keep the current splitter, but chunk boundaries never cross pages without recording the range.
- `full_text` stays for compatibility; it gets page separators so existing features keep working.

### 3.2 Extraction quality
- **Investigate the 238k vs 31k discrepancy first** (Phase 0). Pick the engine per document type based on the result (PyMuPDF/pypdfium2 text, Docling, content-core auto).
- Optional **vision captioning per page** for pages with figures, diagrams or math (detected by image area / low text yield): the vision model writes a short description and, for diagrams, a Mermaid graph. Stored on `source_page`, embedded like text. Cost-capped and cached; uses the configured vision model.
- Keep originals: fork default `auto_delete_files = "no"`; page thumbnails cached for the UI.

### 3.3 Document metadata
- `source.metadata` (flexible object), with a known core: `doc_type` (lecture, paper, notes, book…), `series` / `course`, `sequence` (lecture number), `date`, `authors`, `page_count`.
- Auto-filled at ingestion from the filename, PDF metadata and the first pages by a cheap model call (structured output); editable via API and UI.
- Queryable by the agent (`list` filters/sort) and usable as search filters.

### 3.4 Summaries and outline (TreeRAG / PageIndex, simplified)
- **Section summaries:** group pages into sections (outline headings or fixed windows of ~10 slides) → summary per section with its page range.
- **Document summary + outline**, built from the section summaries (map-reduce, so a 60k-token deck is never sent in one call).
- Stored as insights of new types (`doc_summary`, `section_summary`, `outline`), embedded, so they're searchable and support document-level similarity.
- Runs as a background command after embedding, with a backfill command for existing sources. Estimated cost with `glm-5.3-flash`: roughly $0.01–0.03 per 100-slide deck (estimate, to be measured in Phase 1).

## 4. The agent

### 4.1 Retrieval backends
- Passage-level hybrid search with reciprocal rank fusion (optional weight), similarity floor and top-k; filters by source ids, metadata, page range; notes and insights included.
- Section- and document-level search over the stored section/document summaries plus metadata, and "more like this" (similarity to a given address's embedding).
- Exact/regex matching over page text (exhaustive, not top-k).
- Rerank: optional (LLM-as-reranker on the top-N, or a local cross-encoder later).

### 4.2 Tools: general primitives, not task-shaped

Design rules: few orthogonal tools that compose; file-system-like semantics models already handle well;
one address format everywhere; bounded output with a continuation pointer; errors that say how to fix the call;
every result carries addresses the answer can cite.

**Addresses** (taken and returned by every tool, and used as citations the UI renders as links):
`source:abc` · `source:abc#p12` · `source:abc#p12-18` · `source:abc#s3` (section) · `source:abc/summary` ·
`source:abc/outline` · `note:xyz` · `source_insight:…`

| Tool | Analogy | What it does | Origin |
|---|---|---|---|
| `list(filters?, sort?, fields?)` | `ls` | The catalog: documents with type, course, sequence number, date, page count, summary line; filter and sort | Generalizes RAGFlow's `metadata_search` catalog |
| `grep(pattern, scope?)` | `grep` | Exhaustive exact/regex matches with per-document counts and page numbers | RAGFlow `grep_chunks` |
| `search(query, scope?, level=passage\|section\|document, like?)` | semantic search | Meaning-based search at any granularity; `like=<address>` gives "more like this" | RAGFlow hybrid/semantic search legs; `level` and `like` are new |
| `outline(source)` | table of contents | Sections with page ranges and one-line summaries | RAGFlow PageIndex / `navigate_tree` |
| `read(address, limit?)` | `cat` / `less` | Read pages, a section, chunks with neighbors, or a stored layer (`/summary`); capped, returns a "continue at" address | RAGFlow `list_chunks`; layers are new |
| `view(address)` | open an image | Look at a page or an image source (sent to the model as an image) | New |
| `delegate(task, addresses[])` | sub-agents | Run a sub-task per document in parallel, each in its own context; returns compact results with addresses | RAGFlow fan-out / Claude Code subagents |
| `note(title, content, links)` | write a file | Save to the notebook's notes, after user confirmation | New (Open Notebook has AI notes) |
| `python(code)` *(optional)* | sandbox | Math checks, arithmetic, counting over results | RAGFlow `run_javascript` sandbox |
| `ask_user(question)` *(optional)* | — | Clarify instead of guessing | New |
| `web(query)` *(off by default)* | — | Web search; results kept separate from notebook evidence | RAGFlow `web_search` |
| image search *(phase 5)* | — | Find pages similar to a pasted screenshot (multimodal embeddings) | New |

No task-shaped tools: summarize = `outline` + `read(…/summary)` or sections; related = `search(like=…, level=document)`;
compare/trace/enumerate = `list` + `grep`/`search` + `delegate`. Considered and folded:
`find_documents`, `summarize_document`, `related_documents`, `find_pages` (these were shaped around one example query).

**Coverage check:** T1–T3 `search`/`grep` → `read`; T4 `view`; T5 `outline` + `read` layers (+ `delegate` for a course-wide summary);
T6–T8 `list` + `grep`/`search` + `delegate`; T9 `search(like=…)` + `list` order; T10 `list`; T11 `search` with the pasted text
(image search later); T12 `read` + generation; T13 `python`; T14 `note`; T15 search results + grounding policy (+ `web`);
T16 rewrite step + `ask_user`.

Images exist only inside the turn (never checkpointed). An early local draft of `search`, `read` and page find/view
(`open_notebook/graphs/agent_tools.py`, not committed) predates this design and will be rewritten to it.

### 4.3 Control flow (LangGraph, async, checkpointed)
```
rewrite (resolve follow-ups using history; skip on first turn)
  → research loop: tool-calling agent, evidence ledger of everything read
      → [deep only] sufficiency review: answerable? list MISSING items
            insufficient & budget left → targeted queries → research loop
  → compose: answer only from the ledger, page citations, state gaps
```
- **Effort levels:** Quick (≤4 tool steps, no review), Standard (≤10, no review), Deep (≤20, review loop ≤2 rounds). Per-turn time budget.
- **Guardrails:** repeat-query detection, tool-error recovery, forced final answer when the budget runs out, empty-model-reply handling (exists), `classify_error` on all model calls, configurable fallback model.
- **Grounding policy:** a notebook setting choosing between "answer only from the notebook" (strict; says when not found) and "may add general knowledge, marked as such".
- **Conversation memory:** checkpointed history; older turns compacted into a summary when the history gets long.
- **Model choice:** tools via LangChain `bind_tools`, so any tool-calling model works; OpenRouter-specific routing (tool-capable providers only, fallback models) is allowed (§8). If the chat model lacks vision, `view` routes to the configured vision model and returns a text description.

### 4.4 Where it runs
- Notebook chat → agent over the notebook (selection = scope; ticking no longer means "paste the full text").
- Source chat → the same agent scoped to one source.
- Ask (search page) → the same agent across chosen notebooks (replaces the one-pass Ask graph).
- MCP / API (Phase 5): the agent and its tools exposed so Claude Code or other agents can use the notebook (matches upstream's "Agents operating Open Notebook" horizon).

## 5. API and frontend
- `POST /api/chat/execute/stream` (SSE): `step` (tool, args summary), `step_result` (short summary), `answer_delta` (tokens), `citations`, `complete`, `error`. `/chat/execute` keeps working (non-streaming).
- Chat UI: live collapsible "Researching…" trace, effort selector, page citations that open the PDF at the page / show the slide thumbnail, inline preview of pages the agent viewed.
- Source view: metadata editor, outline with page links, document summary.
- New strings added to all 14 locales (English text in the non-en-US ones; the locale parity check requires the keys to exist).

## 6. Quality and operations
- **Eval harness** (`evals/` in this repo; the diagram-reading test from model selection moves here): ~40 questions over the lecture decks sampling every task type T1–T16, checked automatically (right documents used, required pages cited, answer facts present, enumerations complete, "not found" when appropriate) plus cost and latency per run. Run it before and after every phase.
- **Traces:** per turn, store steps, tool calls, tokens and cost; viewable in the UI and via the API.
- **Tests:** unit (fusion, scope, page mapping, metadata parsing), graph tests with a scripted fake model, API tests for SSE; CI must stay green (ruff, mypy, pytest, frontend lint/test/build).
- **Docs:** ADRs for (1) agent architecture, (2) page-aware chunking, (3) async checkpointer; CHANGELOG entries.
- **Deployment (PC):** docker compose with memory caps; OpenRouter credentials; models: chat and vision `z-ai/glm-5.3-flash` (fallback `qwen/qwen3.8-flash`); embeddings `qwen/qwen3-embedding-8b` via OpenRouter (§8).

## 7. Phases

| Phase | Scope | Done when |
|---|---|---|
| 0. Foundations | Dev env on the PC; embedding model setup; explain the extraction inflation; async checkpointer; SSE skeleton; eval harness with baseline numbers for current Chat/Ask | Baseline scores recorded; existing tests pass |
| 1. Ingestion | Page-aware extraction + slide mode, `source_page`, chunk page ranges, metadata extraction, section/doc summaries + outline, backfill command, keep originals | Lecture decks re-ingested with pages, metadata and summaries |
| 2. Agent v1 | Retrieval backends; tools `list`, `grep`, `search`, `outline`, `read`, `view`; address format + page citations; Quick/Standard loop; streaming events | T1–T5, T10, T15 pass on the eval set |
| 3. Frontend | Streaming chat with step trace, effort selector, page citations and previews, metadata/outline views, i18n | Usable end to end in the browser |
| 4. Deep mode | Tools `delegate`, `note`, `ask_user`, `python`; query rewrite, sufficiency review loop, conversation compaction, grounding setting; Source chat and Ask moved onto the agent | T6–T9, T11–T14, T16 pass; no task type regresses |
| 5. Extensions | Rerank; optional vision captions; multimodal embeddings (Qwen3-VL-Embedding on the PC GPU); knowledge graph (entities/relations as SurrealDB edges); MCP tools; memory layer | Each behind a setting, measured by the eval harness |

## 8. Decisions

| # | Decision | Made |
|---|---|---|
| 1 | ~~Embeddings run locally on the GTX 1660 Super via Ollama.~~ **Superseded the same day:** embeddings use `qwen/qwen3-embedding-8b` on OpenRouter (~$0.01 per million tokens; under $0.01 for the whole course). Measured on the 1660 (no tensor cores): Qwen3-Embedding-4B took 81 s per 50-chunk batch (over esperanto's 60 s timeout), 0.6B took 15 s but is the weakest of the family. Chat already sends notebook text to OpenRouter, so local embeddings added no privacy. Ollama stays installed, idle. | 2026-10-06 |
| 2 | **Personal fork.** Upstream conventions are kept where they protect quality (tests, CI, typed errors, ADRs), but provider-specific features are allowed (e.g. OpenRouter routing/fallbacks), and new UI strings may ship English-only in non-en-US locales (still required by the locale parity check). | 2026-10-06 |
| 3 | **Classic chat is removed, with no fallback.** No mode pastes whole files into the prompt, including "pinned" sources. The sidebar selection only sets the agent's search scope; whole-document questions go through stored summaries (§3.4), never full-text loading. | 2026-10-06 |
| 4 | **OpenRouter credits** topped up. A capped, project-specific key is still recommended. | 2026-10-06 |

# Content Processing: Pages, Chunking, Embedding, Context & Encryption

Design notes for the code that turns raw content into searchable, LLM-consumable data. The user-level view of the
pipeline is [How Documents Are Ingested](../2-CORE-CONCEPTS/ingestion.md).

## Page-aware PDF ingestion (`utils/pdf_pages.py`, `graphs/source.py`, `commands/`)

- `extract_pdf_pages(path)` reads each page with pdfplumber into `PdfPage(number, text, equations, image_ratio,
  shapes, garbled)` (`shapes` = vector lines + curves + rects; `garbled` = 3+ `(cid:N)` placeholders).
  `clean_page_text` removes residual junk and `(cid:N)`; `latexit_source()` decodes LaTeXiT payloads (base64 → 4-byte qCompress
  length + zlib → binary plist, `source` key) so the 4×-repeated invisible text becomes `$…$`.
- `group_builds(pages)` merges animation builds: a page is a build step of the previous one when it covers ≥ 90% of
  its text (`SequenceMatcher`) and isn't shorter. The last page carries the text; page numbers are kept as ranges.
- `graphs/source.py` uses page extraction for PDFs with a text layer (others go through content-core), stores
  `source_page` rows, and chains the jobs: `caption_pages` (`pages_needing_captions`: `image_ratio ≥ 0.25`, or ≥ 12 shapes over the
  document's median, or garbled; Transformation Model,
  4 concurrent, `NO_VISUAL_CONTENT` sentinel) → `embed_source` → `analyze_source` → `embed_pages` +
  `extract_concepts`.
- `embed_source` builds **page-ranged chunks** (`_paged_chunks`: page text + caption, header `Title — pp. N–M`,
  `page_start` / `page_end` on each `source_embedding`) instead of the generic splitter when pages exist.
- `analyze_source` (`commands/analyze_commands.py`): `plan_outline` (page index → `OutlinePlan` JSON; on failure,
  fixed page windows), `summarize_sections` (per section; empty reply → retry → plain extract), document summary
  from section summaries (empty → joined section summaries). Writes `source.metadata`, `source_section` (embedded),
  and replaces the "Document Summary" insight.
- **PDFium is not thread-safe**: every pypdfium2 call holds `PDFIUM_LOCK` (it crashed the worker with heap corruption
  when captions rendered pages in parallel).
- Model calls in these jobs use `limit_reasoning()` so reasoning models can't return empty replies.
- **Tracking and versions** (`open_notebook/domain/ingestion.py`, [ADR-019](decisions/ADR-019-tracked-versioned-ingestion.md)):
  each command runs inside `tracked(source_id, stage)` (running → done / skipped / failed, with a `detail` dict) and
  queues the next stage with `stage_queued()` beside its `submit_command()`. `STAGE_VERSIONS` holds each stage's
  version; bump it (with a reason in the comment) when existing sources should get a change. The worker entrypoint
  then restarts sources per `restart_point()` (failed, stalled, then outdated; never while work is queued or
  running): `reprocess()` maps extract/caption to `caption_pages(refresh=…, reprocess=…)`, which updates pages in
  place; after an outdated stage it continues the chain only if captions or text changed, after a failure or stall
  always. Other stages re-submit their own command. `caption_pages` skips pages already checked at the current caption version
  (`source_page.caption_version`).
- Ingestion re-runs replace a transformation's insight (`add_insight(replace=True)`) instead of duplicating it.
- **Office documents** (`utils/office_convert.py`): `content_process` converts PPTX/PPT/PPSX/ODP/DOCX/DOC/ODT/RTF to
  PDF with headless `soffice` (private `-env:UserInstallation` profile per call, 300 s timeout) when available, deletes
  the original and continues with the PDF as the source's file (returned in `content_state`). No converter or a failed
  conversion falls back to content-core text.

## Chunking (`utils/chunking.py`)

Content is split with content-type-aware LangChain splitters (`HTMLHeaderTextSplitter`, `MarkdownHeaderTextSplitter`, `RecursiveCharacterTextSplitter`). Content type detection uses the file extension first; heuristics can override a PLAIN extension when confidence ≥ 0.8. Oversized chunks from the HTML/Markdown splitters get a secondary split.

**Why the 400-token default.** `OPEN_NOTEBOOK_CHUNK_SIZE` defaults to 400 tokens — ~20% below the 512-token ceiling of BERT-family embedders (e.g. `mxbai-embed-large`). The buffer absorbs three error sources: tokenizer mismatch (we measure with `o200k_base`, the embedder tokenizes with WordPiece), splitter overshoot, and special tokens. For embedders with large windows (OpenAI `text-embedding-3` family: 8191 tokens) raise it, e.g.:

```bash
export OPEN_NOTEBOOK_CHUNK_SIZE=1500
export OPEN_NOTEBOOK_CHUNK_OVERLAP=150
```

`OPEN_NOTEBOOK_CHUNK_OVERLAP` defaults to 15% of chunk size. Both are **token-based** (not characters), minimum chunk size 100, and require an app restart to take effect.

## Embedding (`utils/embedding.py`)

- `generate_embedding(text)` — unified entry point: short text (≤ chunk size) embeds directly; long text is chunked, each chunk embedded, and the results combined via **mean pooling** (normalize each → mean → normalize result, numpy).
- `generate_embeddings(texts)` — batch path used by `embed_source_command`: batches of 50 with per-batch retry, to stay under provider payload limits.
- Empty/whitespace-only input raises `ValueError` — which background commands treat as a permanent (non-retried) failure by design.
- The embedding model comes from `model_manager` (see [credentials.md](credentials.md) for how provider config is resolved).

**Who triggers embedding** (see also the domain rules in `open_notebook/AGENTS.md`):

| Content | Trigger |
|---|---|
| Note | `Note.save()` auto-submits `embed_note` |
| Insight | `create_insight_command` submits `embed_insight` |
| Source | explicit `source.vectorize()` → `embed_source` (NOT automatic on save) |
| Everything | `rebuild_embeddings_command` fans out individual jobs |

All embedding is fire-and-forget through the surreal-commands worker — nothing embeds if the worker isn't running.

## Context building (`utils/context_builder.py`)

Upstream's context builder. The research agent doesn't use it (it reads through its tools); it still backs
`POST /api/chat/context` (podcast content selection) and the legacy chat graphs:

- `build_notebook_context()` backs `POST /api/chat/context` (chat panel + podcast generation): it assembles source/note contexts from the inclusion config, whose status strings are matched textually ("not in" skips, "insights" → short context, "full content" → long context). Without a config, every source and note is included with its short context. Per-item failures are logged and skipped.
- `build_source_context()` backs the source-chat graph: it requests the source's long context and adds insights as separate budgeted items. Full source text is retained when it fits. For an oversized source, up to 20% of the token budget is reserved for fitting insights in fetch order, unused space returns to the source, and a near-maximal token-aligned source prefix carries an explicit truncation notice. Prefix selection uses a cached binary search plus bounded forward validation for local BPE non-monotonicity; the offline word-count fallback stays logarithmic. Budget enforcement and `total_tokens` use the shared Markdown renderer that supplies the prompt, while internal counts/status metadata are not rendered to the model. If the budget cannot fit the rendered source headers, the notice, and at least one non-whitespace source character, the source item is omitted and metadata reports `source_text_status="omitted_budget"` rather than presenting notice-only text as source content.
- Every call re-fetches — there is no cache layer.
- Token counting uses `o200k_base` via tiktoken and is an estimate (±5-10% vs. the actual model); `token_count()` falls back to a coarse estimate if tiktoken is unavailable.

## Encryption

`utils/encryption.py` provides field-level encryption for sensitive values (API keys) stored in the database, using Fernet (AES-128-CBC + HMAC-SHA256).

- Key source: `OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE` (Docker secrets) → `OPEN_NOTEBOOK_ENCRYPTION_KEY`. **No default** — credential storage is unavailable until the key is set.
- Any string works as key: it's derived to a Fernet key via PBKDF2-HMAC-SHA256 (600k iterations, fixed app salt), lazily on first use; the derived instance is cached per process.
- New values carry a `pbkdf2v1:` marker. Decryption branches on it: marked values decrypt under PBKDF2 only (any failure raises — never returned as a key); unmarked values try the legacy SHA-256 derivation, then fall back to plaintext for pre-encryption data.
- One-shot upgrade: `POST /api/credentials/migrate-encryption` rewrites stored keys into the marked format (idempotent, fail-closed per record). Lazy re-encrypt-on-save alone is not enough since keys are set once.
- Key rotation is **not implemented** — changing the key orphans previously encrypted values.

## Text utilities (`utils/text_utils.py`)

`clean_thinking_content()` strips `<think>…</think>` blocks from model output (extended-thinking models); used in every graph that consumes LLM responses. It handles malformed output (missing opening tag) and bypasses extraction for content > 100KB for performance.

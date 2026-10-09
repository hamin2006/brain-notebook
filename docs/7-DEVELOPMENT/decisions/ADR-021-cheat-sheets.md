# ADR-021: Cheat sheets are built from cached recall items, composed in parts and revised by edit operations

- **Status**: Accepted (Brain Notebook)
- **Date**: 2026-10
- **Related**: [plans/cheat-sheet.md](../plans/cheat-sheet.md), [ADR-015](ADR-015-page-aware-ingestion.md) (outline
  sections), [ADR-019](ADR-019-tracked-versioned-ingestion.md) (stage versions)

## Context

A cheat sheet is a printable, page-budgeted recall sheet over chosen documents, every line cited
([user guide](../../3-USER-GUIDE/cheat-sheets.md)). Building it on the MATH 138 course (72 decks, 793 pages,
GLM 5.3 Flash and Qwen 3.7 Flash on OpenRouter) showed:

- **One composer reply tops out around 16K characters of sheet** whatever the budget: asked for 22K and 25K it
  wrote 15.0K and 15.8K (more, shorter lines). A two-page sheet at 7 pt holds about 24K.
- **A revision that rewrites the whole sheet** hits the same ceiling, spends most of its output re-typing lines
  nobody asked to change, and copied the prompt's line markup (`l5 (items r1, r2) ·`) into the text.
- **Three parallel composer calls on a 16K-token cap** ran for over 10 minutes: a reply that keeps going outlasts the
  180 s call timeout, and the HTTP client retries silently.
- **SurrealDB 2 mis-plans filters on tables with a composite unique index**: besides `IN` (already known), an
  equality on two columns of a three-column key returned nothing and `>=` acted as `>`.

## Decision

- **Recall items are extracted per outline section, cached and versioned.** One tools-model call per section reads
  its page text and captions; items are stored per (source, section) and reused by every later sheet. A section is
  read again when `RECALL_ITEMS_VERSION` changes or analysis rewrites the outline (which clears
  `source_section.recall_version`). Extraction is on demand, not an ingestion stage: most documents never get a sheet.
- **`recall_item` rows are keyed by record id** (`recall_item:<source>_<section>_<index>`) with a plain index on
  `source`, not a composite unique index.
- **Lines cite items, never pages the model names.** The composer and the reviser refer to items by short id; a line
  that covers no known item is dropped, and citations are computed from the items' page ranges.
- **A large budget is composed in parts** (`PART_CHARS`, about 9K characters each): the items, in course order, are
  cut between documents into parts of about equal weight, composed in parallel with proportional budgets, and their
  topics joined in order.
- **Revise, Shorten and Add more are edit operations on the current version**: the model returns `remove`, `edit` and
  `add` (with item ids and a placement) plus a note per comment; the job applies them. Pinned and hand-edited lines
  ignore removals and edits. Shorten and Add more are revisions with a built-in request and a changed budget, so they
  keep pins too.
- **Composer calls are bounded**: 10K output tokens and a 200 s attempt timeout that counts as a failed attempt (one
  retry), so a runaway reply costs one retry instead of minutes of silent HTTP retries.
- **PDF comes from the browser's print, `.tex` from the layout.** The sheet renders at its printed size (KaTeX, CSS
  columns); the browser measures real overflow and leftover room. A LaTeX install on the host and model-written
  LaTeX were rejected (size, compile failures); the `.tex` export is generated deterministically.

## Consequences

- First sheet over the 72-deck course: about $0.05 and 4 minutes (150 sections read); later sheets about a cent
  and 1–2 minutes; a revision under a cent in about 25 s. Checklist recall 21/22 of what the course teaches
  (`evals/cheat_sheet/`), every citation pointing at an existing page.
- The page budget (`CHARS_PER_PAGE_AT_7PT`) is a calibration, not a guarantee; the measured banner (Shorten / Add
  more) is the backstop. Topic boundaries between parts can repeat a heading; adjacent same-title topics are merged.
- A document added to a notebook later doesn't change existing sheets.
- Changing the extraction prompt means bumping `RECALL_ITEMS_VERSION` (the next build re-reads), not a backfill.

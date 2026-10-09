# Plan: cheat sheets

- **Status**: Proposed (2026-10), not started
- **Vision**: extends unique feature #4 (formula sheet) in [VISION.md](../../../VISION.md#focus-stem-students-in-slide-heavy-courses-decided-2026-10)
- **Builds on**: outlines with page ranges and recovered equations ([content-processing.md](../content-processing.md)),
  the concept-extraction pattern (`commands/concept_commands.py`), KaTeX rendering in the UI

## The feature

A student picks sources (say Lectures 1–6 before a midterm), a length (1 or 2 pages) and what to include. Brain
Notebook builds a dense cheat sheet: formulas, definitions, theorems and methods grouped by topic, every line citing
the slide it came from. The student reviews it, comments on lines ("too long", "missing the ratio test", "drop
this"), and **Revise** applies the comments. It prints to PDF and exports `.tex`.

NotebookLM's study guide is a prose summary of a notebook. This is a page-budgeted recall sheet, in the course's
notation, with page citations, and it can be revised.

## Decisions (defaults, changeable)

- **PDF through the browser's print**, not a LaTeX compile: the sheet is rendered in the app (KaTeX, already used),
  with a print stylesheet (Letter or A4, columns, small type). A TeX install on the host is several hundred MB, and
  model-written LaTeX fails to compile often enough to need a repair loop. A deterministic `.tex` export (built from
  the items, not by a model) covers Overleaf users.
- **Length**: 2 pages (one sheet, both sides) by default; 1 or 2, columns 2–4.
- **Included by default**: formulas, definitions, theorems and rules, methods (procedures, tests and when to use
  them). Optional: worked-example skeletons, common pitfalls.

## How it works

```
POST /notebooks/{id}/cheat-sheets {sources, pages, columns, kinds, instructions}
  └─ build_cheat_sheet(sheet)                                     worker job
       1. recall items: for each selected source, each outline section without
          current items ─► one extraction call (tools model) ─► recall_item rows (cached)
       2. compose: items + page budget + instructions ─► one call (chat model)
          ─► layout: topics ─► lines (item ids, condensed text, citations)
       3. sheet version 1
UI renders, measures real overflow per page, offers Shorten / Revise
POST /cheat-sheets/{id}/revise ─► revise_cheat_sheet: layout + open comments + unused items
  ─► new version; edited and pinned lines kept verbatim; comments marked addressed
```

### 1. Recall items (per section, cached)

The same shape as concept extraction: one call per outline section on its page text plus captions (captions carry the
LaTeX the caption step recovered from garbled Beamer math), and the page's recovered equations. A free-roaming agent
per source was considered and rejected: with about 6 steps it samples a 100-page deck, and a sheet that silently
misses a formula is worse than none. Per-section extraction reads everything and is repeatable.

Each item: `kind` (formula | definition | theorem | method | example | pitfall), `title`, `body` (Markdown with
`$…$` LaTeX, in the course's notation), `priority` (1–3, how likely it must be recalled), `page_start`, `page_end`.

Items are stored (`recall_item`: source, section, …, `version`) and reused by every later sheet over the same
sources, so the second sheet only composes. They are extracted on demand, not at ingestion (most uploads never get a
sheet). A prompt change bumps `RECALL_ITEMS_VERSION` and outdated sections re-extract on the next build. Concurrency
follows `OPEN_NOTEBOOK_SECTION_CONCURRENCY`; failed sections use `partly_failed`-style reporting on the sheet
("2 sections couldn't be read").

### 2. Composing to a page budget

The composer gets the items as compact lines (`id · kind · priority · title · body · cite`), the budget as an
approximate character count per page and column at the chosen type size, and the user's instructions. It returns
topics with lines; each line references the item ids it covers (merging duplicates across lectures) and may condense
their text, but never invents content: lines without an item id are dropped, and citations come from the items, not
from the model.

The browser measures what was actually rendered: a page that overflows shows **Shorten** (recompose with a tighter
budget), and leftover room shows **Add more**.

### 3. Review and revision

- Comment on a line or on the sheet; edit a line by hand; pin a line so revisions keep it.
- **Revise** sends the layout, the open comments and the unused items of the same sources (so "missing the ratio
  test" can be filled from the pool), and returns a new version. Edited and pinned lines are kept verbatim; each
  comment gets a short note on what changed and is marked addressed.
- Versions are kept; the sheet view can switch between them.

### Data

Migration 34: `recall_item` (above; unique `(source, section, index)`, added to the `source_delete` event),
`cheat_sheet` (notebook, title, source ids, options, status, error, current version), `cheat_sheet_version` (sheet,
number, layout, created), `cheat_sheet_comment` (sheet, version, line id or none, text, status, note).

### API and UI

- `POST/GET /notebooks/{id}/cheat-sheets`, `GET/PATCH/DELETE /cheat-sheets/{id}`, `POST /cheat-sheets/{id}/revise`,
  comments CRUD, `GET /cheat-sheets/{id}/tex`.
- Entry: **Cheat sheet** in the notebook header's menu → a dialog: sources (checkboxes in course order, all by
  default), length, columns, kinds, instructions ("exam covers lectures 1–6").
- The sheet is its own page (`/notebooks/{id}/cheat-sheets/{sheetId}`), full width for print: the sheet as it will
  print, citations as small marks that open the page in the evidence panel (hidden in print unless chosen), a
  comment rail, Revise, Print, `.tex`, the version switcher, progress while building.
- Every string in all 14 locales; CHANGELOG; user guide page; screenshots.

## Validation

A Calculus II deck set (integration techniques, applications, sequences and series, parametric and polar):

1. A checklist of what a Calc 2 sheet must contain: integration by parts, trigonometric integrals and substitution
   table, partial fractions, improper integrals, arc length and surface area, the series tests (divergence, integral,
   comparison, limit comparison, alternating, ratio, root) with their conditions, geometric and p-series, Taylor and
   Maclaurin series of eˣ, sin x, cos x, ln(1+x), 1/(1−x) with radii, parametric derivatives, polar area.
2. Score each build: checklist recall, formulas correct (hand-checked against the slides), every line's citation
   opens a page that supports it, fits the page budget, cost and time.
3. Then a second course (the NLP or deep learning notebook) to check it isn't tuned to calculus.

`evals/cheat_sheet/` holds the checklists and a runner, like the agent eval.

## Milestones

| # | Deliverable | Size |
|---|---|---|
| 1 | `recall_item` extraction job with caching and versioning, migration 34, tests | 2 days |
| 2 | Composer with page budget and citation checks, `cheat_sheet` and versions, API | 1 day |
| 3 | Sheet page: render, print layout, overflow measuring, `.tex` export, creation dialog | 2 days |
| 4 | Comments, edits, pins, Revise, version switcher | 1–2 days |
| 5 | Calc 2 validation and tuning; docs, screenshots | 1 day |

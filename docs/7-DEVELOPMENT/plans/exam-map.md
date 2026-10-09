# Plan: the exam map

- **Status**: Proposed (2026-10), not started
- **Vision**: unique feature #1 in [VISION.md](../../../VISION.md#focus-stem-students-in-slide-heavy-courses-decided-2026-10)
- **Builds on**: ingestion stages ([ADR-019](../decisions/ADR-019-tracked-versioned-ingestion.md)), the agent's
  retrieval (`open_notebook/agent/retrieval.py`), the workspace ([ADR-018](../decisions/ADR-018-research-workspace-ui.md))

## The feature

A student uploads past exams or problem sets into a course notebook. Brain Notebook splits each into questions,
matches every question to the slides that teach it, and shows:

1. **Questions → slides**: each question with the pages that teach its method, as thumbnails that open in the
   evidence panel.
2. **Lecture weight**: how much of the exams each lecture accounts for (points, or question count when points are
   missing), across every exam in the notebook.
3. **Never tested**: outline sections no question touches.
4. **Study plan**: sections ordered by exam weight, each linking to its pages and to the questions that test it.

NotebookLM and general chatbots can answer "what's on this exam" for one question at a time; none of them keep a
persistent mapping from a course's exams to its slides.

## How it works

```
exam PDF ─► existing pipeline (extract, caption, embed, analyze)
              analyze: doc_type = exam | problem_set ─► queue split_questions
split_questions ─► exam_question rows (label, text, pages, points)
              └─► queue map_questions(notebook) for each notebook the exam is in
map_questions ─► per question: candidates (retrieval, no model) ─► one judge call ─► question_match rows
              └─► low confidence ─► escalate to a one-document agent run (delegate's sub-agent)
API: GET /notebooks/{id}/exam-map ─► weights, never-tested, study plan computed from the rows (no model)
```

### 1. Recognising exams

- Add `exam` and `problem_set` to `DocumentMetadata.doc_type` (`open_notebook/utils/sections.py`). The outline step
  already sees the file name and first page, which is usually enough ("Midterm 2023", "HW 3").
- Users can override it: a "This is an exam" toggle on the source (sets `metadata.doc_type` and re-queues the
  question split). The model will misclassify some solution sets and review sheets, so this is needed in v1.
- Exams stay searchable by the agent like any source, but matching only targets teaching material (every source
  that isn't an exam or problem set).

### 2. Splitting into questions: `split_questions` (new source stage)

- New stage `questions` in `STAGES`, only for exam-type sources, queued by `analyze_source` once metadata is known;
  tracked and versioned like the others, so prompt changes re-run through a stage version bump.
- One structured call on the page text (captions for scanned or image-heavy pages, which the caption stage already
  produces) returns `[{label: "2(b)", text, page_start, page_end, points?, has_figure}]`.
- Sub-parts are separate questions (2(a) and 2(b) often test different lectures); a shared stem is copied into each
  part's text so it can be matched alone.
- Answer keys and solutions: if the exam includes them, keep the solution text on the question (`solution`). It
  makes matching much more accurate ("uses the chain rule through a softmax"), and the UI can hide it.
- Table `exam_question`: `source`, `index`, `label`, `text`, `solution`, `page_start`, `page_end`, `points`,
  `embedding`; unique `(source, index)`. Migration 34.

### 3. Matching questions to slides: `map_questions` (new notebook job)

Matching depends on the notebook's lectures, not just the exam, so it is a notebook-level job rather than a source
stage. It runs when an exam finishes splitting, and again on demand when lectures were added since (the API reports
the map as stale when a teaching source is newer than the last mapping).

For each question:

1. **Candidates, no model**: section hits (BM25 + vector over `source_section` summaries) and page hits (text and
   page-image embeddings), the concepts the question names (`match_concepts` → `concept_mentions`), fused with the
   existing reciprocal-rank fusion and reranked: about 8 sections with their pages.
2. **One judge call** (the `tools` model, structured output) sees the question (and solution), the candidate
   sections' summaries and their pages' text and captions, and returns
   `[{address: "source:abc#p12-18", role: teaches | example | background, confidence, why}]`, or nothing if the
   course doesn't cover it.
3. **Escalate when unsure**: if the best match has low confidence, or the question depends on a figure, run the
   delegate sub-agent (`run_loop`, single-source scope) on the top two documents with the question as its task. It
   can grep, read and `view` pages. Expect about 1 in 5 questions to need this.

Table `question_match`: `notebook`, `question`, `source`, `section` (index), `page_start`, `page_end`, `role`,
`confidence`, `why`, `mapped_at`. A re-map replaces a question's matches in one transaction (like
`replace_concept_graph`).

Concurrency and cost: questions run 10 at a time, inside the worker's existing limits
([ADR-020](../decisions/ADR-020-ingestion-throughput-and-memory.md)). A 30-question exam is about 30 judge calls plus
about 6 sub-agent runs: roughly $0.05–0.15 and 1–2 minutes.

### 4. The API (no model calls)

`GET /api/notebooks/{id}/exam-map` computes everything from the rows:

- **Weight per lecture and per section**: sum over questions of `points` (or 1), split across a question's `teaches`
  matches by confidence; `example` and `background` matches count at a lower weight. Lectures in `metadata.sequence`
  order.
- **Never tested**: outline sections with no match from any exam.
- **Study plan**: sections by weight, each with its pages, the questions that test it and the exams they came from.
- **Stale**: teaching sources added or re-analyzed after `mapped_at`, plus `POST /api/notebooks/{id}/exam-map/refresh`.

Also `GET /api/sources/{id}/questions` (one exam's questions and matches).

### 5. The UI

- A third workspace view beside Chat and Graph: **Exams** (`WorkspaceView = 'chat' | 'graph' | 'exams'`), shown
  once the notebook has an exam.
- Top: lecture-weight bars in lecture order (one colour per exam, stacked), "never tested" sections greyed out
  below them.
- Tabs: **Study plan** (sections by weight) and **Questions** (per exam: each question with its matched page
  thumbnails via `PageThumb`; clicking opens `openEvidence({kind: 'pages', …})`; the `why` line under each match).
- Each question has "Ask about this" (queues it in chat with `ask()`) and "Wrong match?" (removes a match; the
  correction is stored and kept on re-map).
- Upload: the existing add-source dialog; the source shows the exam toggle and its question count.
- Every string in all 14 locales; screenshots refreshed.

### 6. The agent and MCP (after v1)

The agent should be able to use the map ("what's most likely on the midterm?"), but tools stay general primitives:
expose questions as addresses (`source:exam#q3`), readable by `read` and findable by `list`/`search`, rather than
adding an exam-specific tool. The MCP server gets the same through the shared tool functions.

## Validation

The feature is only worth building further if matching is right and classmates use it.

1. **Gold set before the UI**: take one course already ingested, one or two real past exams, and hand-label each
   question's teaching pages (about an hour). Add it to `evals/` as `evals/exam_map/` with a runner that reports:
   - lecture accuracy (the top match is in the right lecture), target ≥ 90%;
   - page hit (a returned range overlaps a gold range), target ≥ 75%;
   - "not covered" questions correctly left unmatched;
   - cost and time per exam.
2. Tune candidates and the judge prompt against it; only then build the UI.
3. Give it to classmates before a midterm. Repeat use before the final decides whether to continue
   (VISION.md).

## Milestones

| # | Deliverable | Size |
|---|---|---|
| 1 | `doc_type` exam/problem_set, exam toggle, `questions` stage, `exam_question` table (migration 34), tests | 1–2 days |
| 2 | `map_questions` job (candidates, judge, escalation), `question_match`, integration tests | 2 days |
| 3 | Gold set and eval runner; tune until targets are met | 1–2 days |
| 4 | Exam-map API (weights, never tested, study plan, stale, refresh) | 1 day |
| 5 | Exams view, corrections, i18n, docs, screenshots, CHANGELOG | 2–3 days |
| 6 | Question addresses for the agent and MCP | later |

An ADR records the structural decisions (questions as a source stage, matching as a notebook job, judge before agent)
when milestone 2 lands.

## Open questions

- **Syllabus**: a syllabus lists topics per week rather than questions. It could map topics to lectures in the same
  way ("listed in the syllabus but never taught"), but it is left out of v1.
- **Exams without points**: weight by question count, or let the user enter points per question?
- **Handwritten or scanned exams**: captions recover their text roughly; the gold set should include one to see
  whether splitting holds up.
- **Exams across notebooks**: an exam in two notebooks is mapped separately in each, since the lectures differ.

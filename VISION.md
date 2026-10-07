# Brain Notebook — Vision & Principles

What Brain Notebook is, what it refuses to be, and where it's heading. Design decisions are checked against this
document; the reasoning behind each rule lives in the [decision records](docs/7-DEVELOPMENT/decisions/README.md).

---

## Identity

Brain Notebook is a **self-hosted research notebook whose answers are researched, not retrieved**: an agent works
through your documents the way a careful reader would and shows exactly where every claim comes from. It is a fork
of [Open Notebook](https://github.com/lfnovo/open-notebook) and keeps its foundations: your data in your own
deployment, any AI provider, notebooks/sources/notes, transformations and podcasts.

It aims to be better than NotebookLM at the thing NotebookLM is for, studying and researching from a body of
documents:

1. **Grounded**: every claim cites the page it came from; "the notebook doesn't cover this" is a valid answer.
2. **Thorough**: questions that span documents, need every mention, or hide in a diagram get investigated, not
   approximated from a few retrieved chunks.
3. **Yours**: self-hosted, cheap to run, inspectable (the research steps are visible), usable from other agents (MCP).

### What Brain Notebook IS

- A research assistant over a personal library: lecture decks, papers, books, notes
- An agent with general tools (list, grep, search, read, view, graph, delegate), not a pipeline tuned to one kind of question
- A research memory other agents can use through MCP

### What Brain Notebook IS NOT

- A chat-with-a-pasted-document tool: no mode stuffs whole documents into a prompt
- A general-purpose chatbot or web search engine (the web supplements the notebook, it doesn't replace it)
- A multi-user collaboration platform (single user first)
- A document editor or file storage system

### Principles

| Principle | Rule |
|---|---|
| **Evidence first** | Answers come from what the agent read, with the most specific address; strict grounding is the default ([ADR-014](docs/7-DEVELOPMENT/decisions/ADR-014-agentic-notebook-chat.md)). |
| **Primitives, not shortcuts** | New capabilities are general tools that compose; a tool shaped around one example question is a smell. |
| **Structure at ingestion** | Pages, outlines, summaries, metadata and the concept graph are built once when a document arrives, so questions never need the whole document in a prompt ([ADR-015](docs/7-DEVELOPMENT/decisions/ADR-015-page-aware-ingestion.md)). |
| **Cheap by design** | Repeated calls run on the cheapest model that can do them; strong models are used once per answer ([ADR-016](docs/7-DEVELOPMENT/decisions/ADR-016-two-models-per-turn.md)). |
| **Measured** | Changes to the agent or ingestion are checked against the eval set before and after; regressions block. |
| **Privacy and control** | Self-hosted; optional features that call out (rerank, page embeddings, web search) are visible switches ([ADR-017](docs/7-DEVELOPMENT/decisions/ADR-017-agent-extensions.md)). |
| **Provider-agnostic core** | Chat and embeddings work with any provider; provider-specific extras degrade gracefully ([PDR-002](docs/7-DEVELOPMENT/decisions/PDR-002-provider-agnostic-core.md), [PDR-003](docs/7-DEVELOPMENT/decisions/PDR-003-personal-fork.md)). |
| **Async-first** | Long work runs on the worker; the UI streams progress ([ADR-004](docs/7-DEVELOPMENT/decisions/ADR-004-background-workers.md)). |

---

## Current Posture

> **Reviewed: 2026-10** (version 2.0.0).

The research agent, page-aware ingestion and the Phase 5 extensions (rerank, visual page search, concept graph,
memory, web search, MCP) are built and pass the 35-question course eval. The phase now is **use it on real coursework
and fix what that reveals**, before adding surfaces.

### Focus: STEM students in slide-heavy courses (decided 2026-10)

The first audience is university students in technical courses taught from slide decks with diagrams and equations
spread over many lectures. The proof that we're better is there (the course eval), we are the user, and classmates are
the first users. Researchers are the second audience, later.

**Build what nobody has; don't fill feature gaps with NotebookLM.** Its Studio outputs (audio and video overviews,
generic flashcards, mind maps, summaries, slide decks) are commodities it gives away free; matching them wins no
one. What exists from upstream (podcasts, transformations) stays, but isn't extended or led with. Two exceptions:

- **Table stakes must be good enough**, because users leave over them even though they never choose us for them:
  a fast first response (answers take 10–60 s today), reliability, getting material in easily (PPTX, scans, the
  course site or Drive), and a usable phone experience.
- **Where students expect a category, build our version of it**: quizzes on the diagrams that link to the slide,
  not generic flashcards.

**Unique features, in order:**

1. **Exam map**: upload past exams, practice problems or the syllabus; every question is matched to the slides
   that teach it, showing what's tested, what never is and how heavily each lecture counts, with a study plan
   ordered by exam weight that links every item to a slide.
2. **Solve it the course's way**: paste a homework problem (a screenshot works); the agent finds where the course
   teaches the method and walks through it in the professor's notation with slide citations, flagging anything the
   course hasn't covered. General AI solves with its own method and notation.
3. **"I'm lost" prerequisite path**: from a concept, the graph traces what it builds on (chain rule → computational
   graph → Jacobian) into 3–5 steps, each one slide and a check question.
4. **Formula sheet**: every equation in the course, recovered as LaTeX and grouped by concept with slide references,
   checked for completeness.
5. **Diagram quizzes**: questions built from figures, with the slide as the answer key.
6. **Your degree as one connected map**: the concept graph spans courses and semesters ("taught in MATH 221,
   Lecture 8").

For researchers, later: a citation checker for drafts (does each cited paper support the sentence, with page and
figure), results tables read from figures and plots, and the MCP server for writing in Claude Code.

**Validate before scaling**: build the exam map, test it on a real past exam, and give it to classmates before a
midterm. Repeat use before the final decides the direction.

### Horizon

Directions under consideration, not promises:

- **More document types with structure**: slides from PPTX directly, books with chapters, scanned PDFs through OCR with pages.
- **Cross-session recall**: summaries of past conversations the agent can search ("what did we conclude last week?").
- **A larger eval** across other courses and paper collections, so improvements aren't tuned to one notebook, and a
  head-to-head comparison with NotebookLM on the same decks.

---

## How this document changes

Identity changes rarely and through a decision record; the posture section is edited when the phase changes.
Engineering practices live in [docs/7-DEVELOPMENT/design-principles.md](docs/7-DEVELOPMENT/design-principles.md).

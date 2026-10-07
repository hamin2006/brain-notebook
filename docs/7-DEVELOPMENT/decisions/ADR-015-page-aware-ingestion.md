# ADR-015: PDFs are ingested page by page, with analysis layers

- **Status**: Accepted (Brain Notebook)
- **Date**: 2026-10
- **Related**: [plans/agentic-rag.md](../plans/agentic-rag.md) §3, [ADR-014](ADR-014-agentic-notebook-chat.md)

## Context

content-core turned a PDF into one string. Citations could only name the whole source, chunks straddled pages, and
lecture decks extracted to mostly noise: LaTeXiT stores each equation's source as invisible 4×-repeated text (70% of
one deck), animation builds repeat slides dozens of times, and diagram-only slides have no text at all. An agent
that should "read pages 86–94" or "summarize lecture 6 section by section" needs pages and structure.

## Decision

**PDFs with a text layer are extracted per page** (pdfplumber) into `source_page`, with LaTeXiT payloads decoded to
LaTeX, junk removed and animation builds grouped. Visual pages get **vision captions**. Chunks are **page-ranged**.
A background **analysis** job builds metadata (type, course, sequence, topics), a **topic outline with page ranges**,
section summaries and a document summary, all from bounded prompts (never the whole document). Original files are
kept by default so pages can be rendered.

## Alternatives considered

- **Docling / layout models for everything**: heavier, slower, and still no structure layer; kept as an opt-in engine.
- **Whole-document summaries in one prompt**: blows context on long decks and fails silently with reasoning models.
- **Fixed page windows as sections**: kept only as the fallback when the outline can't be parsed.

## Consequences

- Page citations, page previews, `read(#p…)`, `outline`, `list` by lecture number and visual search all depend on it.
- Scanned PDFs and non-PDF types still get one text block; PPTX should be exported to PDF.
- Ingestion is a chain of jobs (pages → captions → chunks → analysis → page images → concepts); each is retryable
  and idempotent per source. PDFium calls are serialized (`PDFIUM_LOCK`).

# ADR-018: The UI is a research workspace that shows its evidence ("Ink & Signal")

- **Status**: Accepted (Brain Notebook)
- **Date**: 2026-10
- **Related**: [ADR-011](ADR-011-design-token-system.md) (token contract, kept), [ADR-014](ADR-014-agentic-notebook-chat.md) (agentic chat), [ADR-015](ADR-015-page-aware-ingestion.md) (pages, outline, concepts), [frontend.md](../frontend.md)

## Context

After the research agent, page-aware ingestion and the concept graph landed, the UI still looked like upstream's:
three equal boxed columns (sources, notes, chat), a chat that read like any chatbot, page citations that opened a
modal, and none of what ingestion builds (page images, outlines, summaries, concepts) visible anywhere. The product's
differentiators were invisible, and the "Quiet Green" palette (squared, green actions, teal AI voice) gave the agent
no presence.

## Decision

**The notebook page is a three-pane research workspace (library · conversation · evidence) and the visual language is
"Ink & Signal": paper surfaces, ink actions, an iris voice for the agent, amber for evidence.**

- **Workspace**: a collapsible *library* (Sources · Notes · Concepts tabs), the *conversation* as the centred hero,
  and an *evidence* panel that opens beside it when a citation or concept is clicked (rendered page with range
  browsing and its outline section, or a concept with relations and mentions). On narrower desktops the library
  yields to the evidence panel; on phones they become tabs and an overlay. State lives in
  `lib/stores/workspace-store.ts` (only layout preferences persist).
- **Answers show their work**: a live research timeline while the agent runs (tool icons, arguments, result
  summaries, elapsed time, a rotating iris edge), folded into one line afterwards; citations are amber chips whose
  hover shows the cited page; every answer ends with a strip of cited-page thumbnails.
- **What ingestion built is visible**: page thumbnails on cards and source rows, a *Structure* tab on every paged
  source (metadata, summary, outline with page ranges, concepts, all pages), notebook stats in the header, and
  starter questions generated from the notebook's top concepts. Backed by read-only endpoints
  (`/notebooks/{id}/overview`, `/notebooks/{id}/concepts/{concept}`, `/sources/{id}/structure`) and JPEG
  thumbnails (`/pages/{n}/image?format=jpeg`).
- **Tokens**: the ADR-011 contract stays (layers, semantic utilities, no raw palette classes, dark mode on the root);
  the values and laws change. Legacy names are kept so components didn't need a sweep: `teal` = iris (agent),
  `gold` = amber (evidence), `fern` = emerald (included / ok). New aliases `iris`, `amber`, `surface-*`, `ink-*`,
  `on-agent`. **Laws**: ink acts (primary buttons are ink) · iris is the agent's voice (live state, focus) · amber
  is evidence (citations, pages) · emerald confirms · red only destroys · paper surfaces, hairlines and soft
  layered shadows · radii 6–18 px · Instrument Serif for titles, Geist for interface, Geist Mono for data and
  addresses.

## Alternatives considered

- **Keep the three equal columns and restyle them**: rejected; the conversation and its evidence are the product,
  and equal columns gave sources and notes the same weight as the answer.
- **Citations as a modal (as before)**: rejected for the notebook; reading an answer against its pages needs them
  side by side. The modal stays where there's no evidence panel (Ask, source chat).
- **A graph visualisation for concepts**: deferred; a ranked, filterable list with a detail panel answers "where is
  this covered?" better than a hairball at 500 concepts.
- **A new token namespace**: rejected; keeping the legacy names made the palette change a value edit, as ADR-011
  intended.

## Consequences

- New screens use `components/brain/` (page thumbnails, citations, research timeline, evidence and concept panels)
  rather than re-implementing them.
- Page images are fetched with auth and cached for the session (`usePageImage`); grids use lazy loading. Thumbnail
  rendering runs on the API under the PDFium lock, so very large grids load progressively.
- ADR-011's palette laws are superseded by the ones above; its contract and `/dev/design` remain the reference.

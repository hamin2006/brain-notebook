# How Documents Are Ingested

The research agent can only be as good as what it searches over. When you add a source, the background worker turns
it into several layers the agent's tools use: pages, captions, chunks, an outline with summaries, metadata, page-image
embeddings and a concept graph. PDFs get all of these; other sources get chunks and summaries.

## The pipeline for a PDF

```
upload
  │
  ▼
1. pages          text per page (pdfplumber), equations recovered, junk removed      → source_page
  │
  ▼
2. captions       visual pages (images, drawn diagrams, math) → vision model       → source_page.caption
  │
  ▼
3. chunks         page-ranged chunks, embedded                                       → source_embedding
  │
  ▼
4. analysis       metadata + topic outline + section summaries + document summary    → source.metadata,
  │                                                                                     source_section,
  │                                                                                     "Document Summary" insight
  ├──► 5. page images    each page rendered and embedded (multimodal model)         → source_page.image_embedding
  └──► 6. concept graph  concepts and relations per section                         → concept, concept_mention,
                                                                                        concept_relation
```

A 100-page deck takes a few minutes end to end, and costs a few cents with the recommended OpenRouter models. The
source is searchable as soon as step 3 finishes; steps 4–6 add the outline, summaries, visual search and graph.
Measured with a two-job worker: a 7-deck course of 89 LaTeX slides took 10 minutes, 8 decks (276 pages) 17 minutes,
and 7 decks with 738 pages of animation builds 17 minutes.

### Following progress

The notebook's **Sources** list shows an indexing strip while anything is running (how many documents are ready and
which steps are active), and each source shows its current step. A source's **Structure** tab lists every step with
how long it took. If a step fails after extraction (a model outage, say), the source shows *failed* with **Retry**,
which re-runs it from that step; the rest of the document stays usable. The same data is at
`GET /api/notebooks/{id}/ingestion` and `GET /api/sources/{id}/ingestion`.

### 1. Pages

PDFs with a text layer are extracted **page by page**, so everything downstream can cite pages. Two things common in
lecture decks are cleaned up:

- **LaTeX equations hidden by LaTeXiT.** Keynote decks made with LaTeXiT carry each equation's source as invisible,
  4×-repeated text; in one 96-page lecture that was 70% of the extracted text. Brain Notebook decodes the embedded
  payload back to LaTeX, so equations become `$\theta_{k+1} = \theta_k - \alpha \ldots$` instead of noise.
- **Animation builds.** Slides that reveal bullet points one at a time are separate PDF pages with growing text.
  Consecutive build steps are merged (the most complete page carries the text), which halves the pages to process in
  a typical deck without losing page numbers.

Scanned PDFs (no text layer) fall back to Open Notebook's regular extraction: one block of text, no pages.

### 2. Captions for visual pages

Visual pages are rendered and described by the **Transformation Model**, which must accept images. A page is
visual when:

- at least a quarter of its area is images (plots, screenshots, slides exported as pictures);
- it draws a diagram as vector shapes (PowerPoint, Keynote and TikZ diagrams): at least 12 more lines, curves and
  rectangles than the document's typical page, so what a template draws on every slide doesn't count;
- or its text came out as unmapped glyphs (`(cid:…)`), which is how LaTeX math often extracts. The junk is removed
  from the text and the caption transcribes the math.

Animation builds are captioned once, on their most complete page. The caption adds what the text layer misses:
text inside the image, equations in LaTeX, and for diagrams the structure (what feeds into what). Pages with nothing
visual to add are skipped. Captions are stored with the page and searched like text, so "where are RMSProp's update
equations?" can find a slide that is only a picture.

### 3. Chunks

Pages are grouped into chunks that never cross page boundaries without recording the range, each prefixed with
`Title — pp. N–M`, and embedded with the **Embedding Model**. Passage search (vector + keyword, fused and reranked)
works over these chunks and notes.

### 4. Analysis

The Transformation Model reads a compact index of the pages (first line of each page or build) and returns:

- **Metadata**: type (lecture, paper, book, notes…), title, course or series, number in the series ("4" for
  Lecture 4), date, authors, topics. `list` filters and sorts on these.
- **Topic sections** with page ranges (typically 5–20 for a 100-page deck), each summarized from its pages, and the
  summaries embedded for section-level search.
- A **document summary**, built from the section summaries (stored as the source's *Document Summary* insight and
  embedded for document-level search and "related documents").

Long decks are never sent in one prompt: the outline uses the page index, and each summary only its section.

### 5. Page images

Every page is rendered and embedded with a multimodal embedding model (`google/gemini-embedding-2` by default, about
$0.0001 per page). An animation build is rendered once, from its last page. This powers `search(level="page")`
("the slide with a ResNet block diagram"), `like=<page>` and searching with a pasted image. Configurable in
[Research agent settings](../5-CONFIGURATION/research-agent.md#visual-page-search).

### 6. Concept graph

The research model lists each section's key concepts (canonical names; abbreviations like "Rectified linear unit
(ReLU)" are recorded as aliases so "ReLU" and "rectified linear unit" are one concept) and the relations the section
states. Concepts are shared across documents, so the `graph` tool can say "dropout appears in lectures 3, 4, 5 and 6,
on these pages". Topics that only appear in an agenda or syllabus slide are skipped. Configurable in
[Research agent settings](../5-CONFIGURATION/research-agent.md#concept-graph).

## Other source types

PowerPoint and Word files (PPTX, PPT, PPSX, ODP, DOCX, DOC, ODT, RTF) are converted to PDF with LibreOffice when it's
installed on the worker's machine, and then take the PDF pipeline above (`OPEN_NOTEBOOK_OFFICE_TO_PDF`).

Web pages, spreadsheets, EPUB, plain text, YouTube, audio, video, and office files without LibreOffice go through
Open Notebook's extraction (content-core, optionally Docling or Crawl4AI) into one text, which is chunked and
embedded. The agent can search, grep and read them by chunk (`source:abc#c12`). They don't get pages, captions, an
outline or page images.

Transformations you select when adding a source still run and produce insights, as in Open Notebook.

## Re-processing

- **After an upgrade that improves a step**, existing documents are brought up to date automatically: when the
  worker starts, sources processed by an older version of a step are re-run from that step (only what changed is
  redone; captions, insights and page images are kept). Set `OPEN_NOTEBOOK_AUTO_REPROCESS=false` to turn this off.
- **A restart during ingestion** (a deploy, a crash) loses nothing: the worker re-queues the interrupted jobs when it
  starts.
- **A source added before Brain Notebook** (or by upstream Open Notebook) has no pages. Delete it and add the file
  again to get the full pipeline.
- **After turning on visual page search or the concept graph**, or changing the page-embedding model: **Settings →
  Research agent** has buttons to run steps 5 and 6 for all existing documents.
- Original files are kept (`auto_delete_files` defaults to *no*) because the agent's `view` tool renders pages from
  them.

## Where it's stored

All layers live in SurrealDB tables tied to the source (`source_page`, `source_embedding`, `source_section`,
`concept_mention`, `source_stage` for progress, …) and are deleted with it. Uploaded files are in the app's data folder. See
[Database](../5-CONFIGURATION/database.md).

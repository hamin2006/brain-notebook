# What the AI Sees: Scope, Search and Privacy

A model only knows what is sent to it. In Brain Notebook, documents are never pasted wholesale into a prompt: the
[research agent](research-agent.md) decides what to look up, and only what it reads reaches the models. This page
explains what you control (scope), how the search behind the agent and the Search tab works, and what each provider
receives.

---

## Scope: what the agent may look at

| Where you ask | What the agent can search and read |
|---|---|
| **Notebook chat** | The notebook's sources and notes, except those set to **Not included in chat** in the sources/notes panel |
| **Source chat** | That one source |
| **Ask page** | The notebooks you pick, or your whole knowledge base if you pick none |
| **MCP `ask` / tools** | The notebook named in the call, or everything |

In notebook chat, the per-source selector still offers *Insights only* and *Full content* (inherited from Open
Notebook); both mean "in scope". Nothing is sent up front either way: the agent reads the pages it needs. Selections
live in the page and reset when you reload it.

**Grounding** (per notebook) decides whether answers may go beyond the notebook: see
[Grounding](research-agent.md#grounding).

---

## Search behind the agent

The agent's `search` tool combines several legs, all limited to the scope above:

| Level | Searches | How |
|---|---|---|
| `passage` | Page-ranged chunks and notes | Keyword (BM25) and vector legs fused by reciprocal rank, then **reranked** |
| `section` | Section summaries from the document outline | Vector + keyword, reranked |
| `document` | Document summaries, titles, metadata, topics | Vector + keyword |
| `page` | Page **images** | Multimodal embedding of your description, a page, or a pasted image |

`grep` complements it: an exhaustive regex over page text (and chunks of non-PDF sources, and notes) for "every
mention of…" questions, where top-k search would miss some.

---

## The Search tab

**Ask and Search → Search** lets you search yourself, without an AI answer. It covers sources, insights and notes;
you can turn sources or notes off and limit it to specific notebooks.

- **Text search**: full-text BM25 over titles and content. Works on every source, needs no model. English stemming.
- **Vector search**: by meaning, over embedded chunks, insights and notes. Needs an embedding model.

Chunks are page-ranged for PDFs; for other sources they're about 400 tokens with 15% overlap
(`OPEN_NOTEBOOK_CHUNK_SIZE`, `OPEN_NOTEBOOK_CHUNK_OVERLAP`). If you change the embedding model, rebuild embeddings
under **Advanced → Rebuild Embeddings**; vectors from different models can't be compared.

---

## Citations

Answers cite **addresses**: `[source:abc#p94]` (a page), `#p12-18` (a range), `#s3` (a section), `/summary`,
`[note:xyz]`. They render as numbered references labeled with the page or section; clicking a page citation previews
the page. Legacy whole-item citations (`[source:abc]`) still render. See [Citations](../3-USER-GUIDE/citations.md).

---

## Privacy: what leaves your machine

Content goes to whichever provider runs the model for that job. With the recommended setup that's OpenRouter (which
routes to the model's provider). If every model is local, no document content goes to a cloud AI provider; reranking
and visual page search would then be off.

| Job | What the provider receives |
|---|---|
| **Research steps** (Tools Model) | Notebook name and description, your question and recent conversation (or its summary), tool results: search hits, pages read, outlines, summaries; images of pages the agent views; images you attach |
| **Answer** (Chat Model) | The same transcript, flattened to text, including viewed page images and attachments |
| **Captions** (Transformation Model) | An image of each mostly-visual page, and its text |
| **Document analysis** (Transformation Model) | The page index, then each section's page text |
| **Embeddings** | Every chunk, section summary, note, insight and concept name |
| **Page-image embeddings** (OpenRouter) | An image of every page (one per animation build) |
| **Rerank** (OpenRouter) | The search query and up to 24 candidate passages |
| **Concept graph** (Tools Model) | Each section's page text |
| **Web search** (optional) | Search queries go to public search engines through your SearXNG; `web_read` fetches pages from their sites |
| **Transformations, podcasts** | As in Open Notebook: the source text; see [Podcasts](podcasts-explained.md#privacy-what-each-model-sees) |

Other outbound requests: adding a URL source fetches that site (and, if configured, sends it to Firecrawl or Jina).
MCP clients you connect receive whatever their tools return.

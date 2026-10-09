# User Guide - How to Use Brain Notebook

Step-by-step instructions for each feature. To understand how things work first (the research agent, ingestion, notebooks and sources), read [Core Concepts](../2-CORE-CONCEPTS/index.md).

---

## Before You Start

Brain Notebook needs default models. The quickest way is `scripts/brain/provision_models.py` with an OpenRouter key; or follow [Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent). [API Configuration](api-configuration.md) covers the rest of the Models page.

What each feature needs:

| Feature | Models needed |
|---------|---------------|
| Notebook chat, source chat, Ask | Tools Model (research; tool calling), Chat Model (answer), Embedding Model |
| PDF captions and document analysis | Transformation Model (vision-capable), or the Chat Model if none is set |
| Transformations (insights) | Transformation Model, or the Chat Model if none is set |
| Reranking, visual page search | An OpenRouter credential (or turn them off in **Settings → Research agent**) |
| Vector search | Embedding Model |
| Text search | None |
| Uploaded audio and video files, YouTube videos without a transcript | Speech-to-Text Model (YouTube videos with a transcript don't need one) |
| Podcasts | The language and text-to-speech models chosen in the episode and speaker profiles |

---

## The Guides

| Guide | What it covers |
|-------|----------------|
| [Interface Overview](interface-overview.md) | The sidebar, the notebook page, the source view, keyboard shortcuts |
| [API Configuration](api-configuration.md) | Connecting AI providers, syncing models, default model assignments |
| [Adding Sources](adding-sources.md) | The Add Source wizard, file types, processing status, failures |
| [Content Processing Engines](content-processing-engines.md) | How files and URLs are extracted (Docling, Firecrawl, Jina, Crawl4AI, OCR) |
| [Transformations](transformations.md) | Generating insights from sources, built-in and custom transformations |
| [Chatting with the agent](chat-effectively.md) | Notebook chat: effort, grounding, attached images, scope, sessions, source chat |
| [Citations](citations.md) | Page citations and page previews |
| [Working with Notes](working-with-notes.md) | Writing notes and saving AI answers |
| [Search and Ask](search.md) | Text and vector search, and Ask across your knowledge base |
| [Cheat Sheets](cheat-sheets.md) | A printable, cited recall sheet from your slides: building, reviewing, revising, printing |
| [Creating Podcasts](creating-podcasts.md) | Generating episodes, episode and speaker profiles |

---

## Your First 15 Minutes

1. **Create a notebook.** Sidebar **New → Notebook** (or **Notebooks → New Notebook**). Give it a name and a short description ("AI 360 deep learning lectures 0-6"); the agent reads the description.
2. **Add a PDF.** In the notebook, **Add Source → Add Source → Upload File**. On the Process step keep embedding on and click **Done**. Processing runs in the background; the card shows **Queued**, **Processing**, then **Completed**, and the outline and summaries follow a few minutes later. See [Adding Sources](adding-sources.md).
3. **Ask.** In the conversation, ask something specific (or click a starter question) and press **Enter**. Watch the research steps, then hover or click a page citation to see the page.
4. **Keep the answer.** Click the **Save to note** icon under the answer. It appears in the Notes column.
5. **Ask across everything.** Open **Ask and Search**, stay on **Ask (beta)**, type a question and click **Ask**. Save the answer with **Save to Notebooks**.

---

## Which Feature for Which Task?

| Task | Use |
|------|-----|
| Research questions about a notebook, with follow-ups | [Notebook Chat](chat-effectively.md) |
| Find a slide by what it looks like | Ask in chat ("the slide with the ResNet diagram"), or paste a screenshot |
| Ask one question across everything | [Ask](search.md#ask) |
| Find a passage or term you remember | [Text search](search.md#search) |
| Find content about an idea, whatever the wording | [Vector search](search.md#search) |
| Get the same summary or extraction for each source | [Transformations](transformations.md) |
| Make a printable cheat sheet for an exam | [Cheat Sheets](cheat-sheets.md) |
| Listen to your research | [Podcasts](creating-podcasts.md) |

---

## Getting Help

- **Something fails or shows an error?** → [Troubleshooting](../6-TROUBLESHOOTING/index.md)
- **How does it work?** → [Core Concepts](../2-CORE-CONCEPTS/index.md)
- **Not installed yet?** → [Installation](../1-INSTALLATION/index.md)

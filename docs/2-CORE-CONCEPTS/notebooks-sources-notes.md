# Notebooks, Sources, Insights, and Notes

Brain Notebook has four kinds of content, plus the layers the research agent builds from your sources. Knowing how they relate explains most of the app.

```
NOTEBOOK  "AI Safety Research"  (name + description)
 │
 ├── SOURCES  (linked; a source can be linked to several notebooks)
 │    ├── safety_paper.pdf
 │    │     └── INSIGHTS  "Dense Summary", "Key Insights"   ← made by transformations
 │    └── alignment_talk.mp4
 │          └── INSIGHTS  "Simple Summary"
 │
 └── NOTES  (belong to this notebook)
      ├── My reading notes          (Human)
      └── Answer saved from chat    (AI Generated)
```

---

## Notebooks

A **notebook** is a workspace for one project or topic. It has a name, an optional description, its linked sources, its notes and its chat sessions.

- The **name and description are given to the research agent** in notebook chat as project information ("AI 360 deep learning course, lectures 0-6"), so a good description helps it interpret questions. Ask, Search and transformations don't use them.
- Each notebook has a **grounding** setting (*Notebook only* or *Notebook + general knowledge*), set from the chat panel. See [Grounding](research-agent.md#grounding).
- Notebooks can be **archived** (hidden from the active list, nothing is deleted) and unarchived.
- **Deleting** a notebook permanently deletes its notes. Sources that are linked only to this notebook can be deleted too or kept in your library; sources shared with other notebooks are just unlinked. The delete dialog shows the counts before you confirm.

---

## Sources

A **source** is one piece of input material: an uploaded file, a web link or pasted text. See [Adding Sources](../3-USER-GUIDE/adding-sources.md) for the supported types.

When you add a source, background jobs:

1. **Extract the text**. PDFs with a text layer are read **page by page** (equations recovered, visual pages captioned by a vision model); other types go through document parsing, web fetching or speech-to-text ([Content Processing Engines](../3-USER-GUIDE/content-processing-engines.md)).
2. **Embed it**: page-ranged chunks (PDFs) or ~400-token chunks, each with a vector for search.
3. **Run the transformations** you selected, producing insights.
4. For PDFs: **analyze** the document (metadata such as course and lecture number, a topic outline with page ranges, section and document summaries), **embed page images** for visual search, and add its concepts to the **concept graph**.

The full pipeline is described in [How Documents Are Ingested](ingestion.md).

Things to know:

- **Sources live in a shared library.** The **Sources** page lists every source. A source can be linked to any number of notebooks (use **Add Existing Source** in a notebook) or to none. Removing a source from a notebook only unlinks it; deleting a source removes it everywhere.
- **The extracted text is not edited in the app.** To pick up a changed web page, use **Refresh content** on the source; to fix a bad upload, add the file again.
- **Search coverage depends on embedding.** Text (keyword) search and the agent's `grep` work on every source. Vector search and the agent's `search` need embedded chunks; insights and section/document summaries are embedded on their own.
- **Original files are kept** by default, because the agent looks at PDF pages (`view`) and page previews render from them.

---

## Insights

An **insight** is the output of running a [transformation](../3-USER-GUIDE/transformations.md) on a source, for example a summary, a list of key points or a table of contents. Insights are the piece most people miss, and several features depend on them:

- **They are attached to the source**, not to a notebook. You see them on the source's **Insights** tab, labeled with the transformation's title.
- **PDFs get one automatically**: the *Document Summary* produced by document analysis. The agent reads it with `read(source:…/summary)` and searches it at document level.
- **They are the "Summary" option in podcasts.** When you pick content for an episode, *Summary* sends the source's insights.
- **They are searchable.** Text search, vector search and Ask all include insights.
- **They can be cited.** Answers can reference an insight, and clicking the reference opens it.
- **They can become notes**, but only through the API today (`POST /api/insights/{insight_id}/save-as-note`). The UI has no button for this.

You create insights when you add a source (step 3 of the Add Source wizard) or later from the source's Insights tab with **Generate New Insight**.

---

## Notes

A **note** is text that belongs to a notebook. A note has a title and Markdown content, and is marked either **Human** (you wrote it) or **AI Generated** (saved from the AI).

Ways to create one:

- **Write Note** in the notebook's Notes column.
- **Save to note** under a notebook chat answer (one click; the title is generated for you).
- **Ask the agent** to save something ("save a short note summarizing dropout"): it uses its `note` tool.
- **Save to Notebooks** after an Ask answer (the question becomes the title, and you can pick several notebooks).

Notes are in or out of the agent's scope in notebook chat, searchable (including by `grep`), and embedded for vector search. See [Working with Notes](../3-USER-GUIDE/working-with-notes.md).

---

## How They Connect

```
Add source ──► pages / text ──► captions (PDF) ──► chunks + embeddings ──► transformations ──► insights
                                                        │
                                                        ▼ (PDF)
                                analysis (metadata, outline, summaries) ──► page images ──► concept graph
                                                        │
                                                        ▼
                                     the research agent's tools; Search; "Summary" in podcasts

Chat / Ask answer ──► Save to note / Save to Notebooks ──► note (AI Generated)
Write Note ──────────────────────────────────────────────► note (Human)
```

## Summary

| Concept | What it is | Belongs to |
|---------|------------|------------|
| **Notebook** | A project workspace with name and description | — |
| **Source** | Input material (file, link, text) | The library; linked to zero or more notebooks |
| **Insight** | A transformation's output for one source | One source |
| **Note** | Text you wrote or saved from the AI | One notebook |
| **Pages, sections, metadata** | The agent's view of a PDF (built automatically) | One source |
| **Concepts** | Ideas extracted from sections, linked across documents | Shared; mentions belong to sources |

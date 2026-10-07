# Search and Ask - Finding What You Need

Search and Ask live on the **Ask and Search** page (sidebar, under **Process**). Both work across your whole knowledge base, or only the notebooks you pick. There is no separate search box inside a notebook.

You can also start either from **Quick actions** (**Ctrl+K** / **⌘K**): type a query and choose *Search results for "..."* or *Ask about "..."*.

| | Search | Ask (beta) |
|---|---|---|
| **Gives you** | A list of matching sources, insights and notes | One researched answer with citations |
| **Uses an AI model** | Vector search uses the embedding model; text search uses none | The [research agent](../2-CORE-CONCEPTS/research-agent.md): Tools Model to research, a language model to answer |
| **Best for** | Finding a passage, term or document | Questions across notebooks, when you don't know where the answer is |

Search is explained further in [What the AI Sees](../2-CORE-CONCEPTS/ai-context-rag.md#the-search-tab).

---

## Search

1. Open **Ask and Search** and choose the **Search** tab.
2. Type your query and press **Enter**.
3. Adjust if needed:
   - **Search Type**: **Text Search** or **Vector Search**.
   - **Search In**: **Search Sources** and/or **Search Notes**.
   - **Notebooks**: pick notebooks to limit the search, or leave all unchecked to search everything.

Results show how many were found; click a result to open the source, note or insight. Where available, a result also lists its **Matches** (the matching passages).

### Text Search vs. Vector Search

| | Text Search | Vector Search |
|---|---|---|
| **Matches** | Exact words (with English stemming) | Meaning, by similarity |
| **Covers** | Source titles and content, insights, note titles and content | Source content, insights, note content (not titles) |
| **Needs** | Nothing | An Embedding Model, and only finds embedded content |
| **Use when** | You know the term, name or phrase | You know the idea but not the wording |

If no Embedding Model is set, the page says *Vector search requires an embedding model. Only text search is available.*

**Tips:**
- Text search works best with distinctive words: names, acronyms, technical terms.
- Vector search works best with a descriptive phrase ("risks of relying on a single supplier") rather than one word.
- A source you can find with text search but not vector search probably isn't embedded. Open it and use **Embed Content**.

---

## Ask

Ask runs the research agent once over the notebooks you pick (or everything), without a conversation.

1. Open **Ask and Search** and stay on the **Ask (beta)** tab.
2. Type your question.
3. Optionally limit it to some **Notebooks** (leave all unchecked for your whole knowledge base).
4. Press **Cmd/Ctrl+Enter** or click **Ask**.

While it runs, the **Strategy** area shows the agent's research steps as they happen (searches, reads, pages it
looks at); then the **Final Answer** appears with citations. Click **Save to Notebooks** to keep the answer as a note
(titled with your question) in one or more notebooks.

### Requirements and models

- The default models must be set ([Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent)):
  the **Tools Model** does the research.
- **Advanced** lets you pick models; the **Final Answer Model** writes the answer. The Strategy and Answer model
  fields are kept for compatibility and are not used by the agent.
- Ask uses Standard effort and the *Notebook only* grounding rules: it answers from your documents and says when
  they don't cover the question.

### When to use Ask

- Use Ask when you don't know which notebook holds the answer.
- Ask is single-turn. To follow up, open the notebook and use [Chat](chat-effectively.md); the citations tell you
  where to look.

---

## Troubleshooting

| Problem | Try |
|---------|-----|
| No results in vector search | Check that an Embedding Model is set and the sources are embedded; rebuild from **Advanced → Rebuild Embeddings** if you changed the embedding model |
| Text search misses a word | Try another form of the word or a synonym; stemming is English-only |
| Too many results | Limit to specific notebooks, or turn off **Search Sources** or **Search Notes** |
| Ask answer is empty or fails | Pick another **Final Answer Model** under **Advanced**, and check the Tools Model supports tool calling |

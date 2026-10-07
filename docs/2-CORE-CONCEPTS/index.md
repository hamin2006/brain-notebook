# Core Concepts - Understand the Mental Model

These pages explain how Brain Notebook is organized and how its research agent decides what to read. Read them once
and the rest of the app will make sense. For step-by-step instructions, go to the [User Guide](../3-USER-GUIDE/index.md).

## The Pages

### 1. [The Research Agent](research-agent.md)
How a question gets answered.

**Key idea**: Chat, source chat, Ask and MCP `ask` all run a research agent. A cheap model calls tools (list, grep,
search, outline, read, view, graph, delegate…) until it has the evidence, then a stronger model writes one answer
citing the exact pages. Effort sets how much research it may do; grounding sets whether it may go beyond the notebook.

---

### 2. [How Documents Are Ingested](ingestion.md)
What the agent searches over.

**Key idea**: PDFs are read page by page (equations recovered, visual pages captioned), chunked by page, analyzed
into metadata + an outline + summaries, embedded as page images for visual search, and linked into a concept graph.

---

### 3. [Notebooks, Sources, Insights, and Notes](notebooks-sources-notes.md)
The things you work with.

**Key idea**: A notebook groups sources and notes for one project. Sources can belong to several notebooks.
Transformations turn a source into insights. Notes are what you write or save from the AI.

---

### 4. [What the AI Sees: Scope, Search and Privacy](ai-context-rag.md)
What you control and what each provider receives.

**Key idea**: Nothing is pasted into a prompt up front. You set the agent's scope (which sources and notes it may
look at); it reads only what it needs. The page lists what each model job sends to its provider.

---

### 5. [Chat vs. Ask vs. Transformations](chat-vs-transformations.md)
Which tool to use for which job.

### 6. [Podcasts Explained](podcasts-explained.md)
How a podcast episode is generated from your content (unchanged from Open Notebook).

---

## The Big Picture

- **Evidence first.** Answers come from what the agent read in your documents, with page citations; in *Notebook
  only* mode it says when the notebook doesn't cover something.
- **You choose the providers.** OpenRouter is the recommended default (one key for every model the agent uses); any
  provider Open Notebook supports works for chat and embeddings.
- **Your data stays in your deployment.** Sources, pages, summaries, the concept graph, notes and memories live in
  your SurrealDB database; uploaded files and chat history (a checkpoint file) live in the app's data directory.
  Back up both.

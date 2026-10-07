# The Research Agent

Every question you ask in Brain Notebook (notebook chat, source chat, the Ask page, or `ask` over MCP) is answered by
a **research agent**. It doesn't receive your documents in its prompt. It receives a description of the notebook and
a set of tools, and it investigates until it can answer, the way you would with a stack of lecture slides:
find the right deck, skim its outline, search for the term, read the pages, look at the diagram, then write the
answer and cite the pages.

## One question, step by step

```
You: "From the 4th lecture, what are Adam's default hyperparameters?"

 research model (cheap, many calls)                         tools
 ─────────────────────────────────                          ─────
 1  list(sequence=4)                    → source:l4 "Lecture 4 - Losses, Optimizers…" (113 pages)
 2  search("Adam default hyperparameters", addresses=[source:l4])
                                        → source:l4#p94 … source:l4#p86-93 …
 3  read(source:l4#p94)                 → page text + caption of the slide image
 4  view(source:l4#p94)                 → the page itself, as an image
 5  (done) findings with addresses

 answer model (one call)
 ─────────────────────────────────
 6  writes the answer from everything gathered, citing [source:l4#p94]
```

You see steps 1–5 live in the chat ("Searching for…", "Reading…"), then the answer streams in. Each answer keeps a
collapsible list of the steps behind it.

## The tools

The tools are general primitives, not shortcuts for particular questions. "Summarize lecture 6 and find related
lectures" is `list` → `outline` → `read(…/summary)` → `search(like=…, level=document)`, not a special tool.

| Tool | Like | What it does |
|---|---|---|
| `list` | `ls` | The catalog: documents with type, course, number in the series, page count, summary line; filter and sort. Resolves "the 4th lecture", "the longest paper". |
| `grep` | `grep` | Exhaustive regex over page text and notes, with counts and page numbers. For "every mention of…". |
| `search` | search engine | By meaning. `level=passage` (evidence), `section` or `document` (topics, related material), `page` (by **appearance**: "slide with a diagram of parallel convolution branches"); `like=<address>` for "more like this"; `image=attachment:1` for "pages that look like the screenshot I pasted". Passages and sections are reranked. |
| `outline` | table of contents | A document's metadata and topic sections with page ranges and one-line summaries. |
| `read` | `cat` | Read pages (`#p12-18`), a section (`#s3`), a stored summary (`/summary`), a chunk or a note; long reads return a "continue at" address. |
| `view` | open an image | Look at a page as a picture (the model sees the image). For diagrams, charts, table layouts, equations the text garbles. |
| `graph` | index of a textbook | The concept graph: every document and page range where a concept appears, and its stated relations (*is a*, *motivates*, *variant of*…). Without a concept: the ideas shared by the most documents. |
| `delegate` | sub-agents | Run the same task on several documents in parallel, each in a fresh context; returns a cited mini-answer per document. For comparing or tracing across many documents. |
| `calculate` | calculator | Exact arithmetic (output sizes, parameter counts). |
| `note` | save a file | Save a note into the notebook, only when you ask. |
| `remember` / `forget` | | Long-term [memory](#memory), only when you ask or state a lasting preference. |
| `web_search` / `web_read` | browser | Only in notebooks that allow general knowledge, with web search turned on. |

## Addresses and citations

Every tool takes and returns **addresses**:

| Address | Means |
|---|---|
| `source:abc` | a document |
| `source:abc#p12` / `#p12-18` | a page / page range |
| `source:abc#s3` | section 3 of the document's outline |
| `source:abc#c37` | chunk 37 (non-paged sources) |
| `source:abc/summary`, `/outline` | stored layers |
| `note:xyz` | a note |

Answers cite the most specific address the agent actually read, right after the claim: "Adam combines momentum and
RMSProp [source:abc#p94]". The chat renders these as numbered references labeled with the page range; clicking a page
citation previews the page. See [Citations](../3-USER-GUIDE/citations.md).

## Two models per question

| Role | Default model slot | Recommended | Calls per question |
|---|---|---|---|
| **Research** (tool calls, sub-agents, the deep-mode reviewer, conversation summaries) | **Tools Model** | `qwen/qwen3.7-flash`: cheap, tool calling, can see images | many |
| **Answer** (one call, from everything gathered) | **Chat Model**, or the model picked for the chat | `z-ai/glm-5.3-flash` | one |

The research loop re-sends a growing transcript at every step, so it runs on the cheapest model that can call tools.
The answer model sees the full transcript once (tool results and viewed pages, flattened to text) and writes the
cited answer. Each research step may think for at most 2,048 tokens and the answer model for 3,072, which keeps
latency predictable with reasoning models.

## Effort

| Effort | Tool steps | Review |
|---|---|---|
| Quick | up to 4 | no |
| Standard (default) | up to 10 | no |
| Deep | up to 20 | a reviewer checks the draft against the question; gaps it lists send the agent back to research (up to 2 rounds) |

When the budget runs out, the answer is written from what was gathered, and says what couldn't be verified.

## Grounding

Each notebook has a grounding setting (the **Notebook only / + General knowledge** switch in the notebook header):

- **Notebook only** (default): answers use only the notebook. If it doesn't cover the question, the answer says so,
  says what was searched, and gives the closest thing the notebook does contain.
- **Notebook + general knowledge**: the agent still checks the notebook first, then may add general knowledge, marked
  as not from the notebook. If [web search](../5-CONFIGURATION/research-agent.md#web-search) is on, it can search
  and read web pages for what the notebook lacks, and cites them as links.

Even in general mode the agent is told to find and cite where the notebook covers a topic, rather than answering from
memory or by calculating alone.

## What the agent sees, and remembers

- **Scope.** In notebook chat, the agent can search the notebook's sources and notes that aren't set to *Not
  included in chat*. Source chat is limited to that source; Ask to the notebooks you pick (or everything).
- **History.** The last 20 messages are sent as they are; older turns are folded into a running summary of the
  conversation. The full history stays visible in the chat.
- **Tool traffic is not stored.** Only your question and the answer (with a compact list of steps) are saved. A
  follow-up re-reads pages when it needs them, using the addresses cited in earlier answers.
- **Images you attach** are used for that turn only.

### Memory

Across conversations the agent knows only what's in its memory list: things you asked it to remember ("remember my
final exam is on Dec 10") or lasting preferences you stated ("keep answers short"). Each item applies to one notebook
or everywhere. At the start of every turn the relevant items (up to 20, the most similar to the question when there
are more) are given to the agent. You can say "forget that", or delete items in **Settings → Research agent**.

## Guardrails

- A repeated identical tool call isn't run again; the agent is told to use the earlier result.
- A failing tool returns an error message the agent can act on; it never ends the turn.
- Tool arguments the model gets slightly wrong (a list sent as text) are accepted.
- An empty answer (a reasoning model that spent its budget thinking) is retried once with less thinking.
- Web pages are untrusted input: fetched text is labeled as such and the agent is told never to follow instructions
  in it; fetching can only reach public internet addresses.

## Why not "classic" RAG?

The original Open Notebook chat pasted every selected document into one prompt (up to 234,000 tokens per question in
our test notebook), and Ask ran a fixed plan of five vector searches. Both answer from whatever text happens to be in
the prompt, can't look at a diagram, and can't follow a question across documents. On the
[35-question course eval](../7-DEVELOPMENT/testing.md#the-agent-eval), pasting the documents cited the right page
for 1 of 30 answers; the agent cites it for 30 of 30, at about a third of the cost.

## Related

- [How documents are ingested](ingestion.md): what the tools search over
- [Chatting with the agent](../3-USER-GUIDE/chat-effectively.md)
- [Research agent settings](../5-CONFIGURATION/research-agent.md)
- Design and decisions: [agentic RAG plan](../7-DEVELOPMENT/plans/agentic-rag.md), [ADR-014](../7-DEVELOPMENT/decisions/ADR-014-agentic-notebook-chat.md)

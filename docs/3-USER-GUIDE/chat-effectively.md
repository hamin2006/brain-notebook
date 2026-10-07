# Chatting with the Research Agent

Notebook chat is where you ask questions about a notebook. Each message is researched by an agent that searches,
reads and looks at your documents before answering with page citations. How it works is explained in
[The Research Agent](../2-CORE-CONCEPTS/research-agent.md); this page is about using it.

---

## Quick Start

1. Open a notebook. **Chat with Notebook** is the right-hand column (on a phone, the **Chat** tab).
2. Type a question in **Ask anything about your sources...** and press **Ctrl+Enter** (**⌘+Enter** on Mac).
   Plain **Enter** adds a new line.
3. Watch the research happen under **Researching…**: each step is listed as it runs ("Searching for “adam”",
   "Reading source:…#p94", "Looking at…"), with a one-line result. Then the answer streams in.
4. Click a numbered reference to check it: page citations open a preview of the page.

The first message creates a chat session automatically.

---

## The controls above the message box

| Control | What it does |
|---|---|
| **Model** | The model that **writes the answer** for this session (default: your Chat Model). Research steps always use the Tools Model. |
| **Effort** | **Quick** (up to 4 research steps), **Standard** (up to 10, default), **Deep** (up to 20, plus a reviewer that checks the draft and sends the agent back for gaps). Per message. |
| **Answers from** | **Notebook only** (default) or **Notebook + general knowledge**. Saved on the notebook. In general mode the agent may add general knowledge, marked as such, and use web search if it's turned on. |
| **Attach image** (paperclip) | Attach up to 4 images to the message, or paste them into the message box. |

Use **Quick** for lookups ("what's on the Adam slide?"), **Standard** for most questions, **Deep** for questions that
span many documents or need everything ("list every activation function the course mentions", "compare how lectures
3–6 treat regularization").

---

## What the agent can look at

The sources and notes panel decides the agent's **scope**: anything not set to **Not included in chat** can be
searched and read. (*Insights only* and *Full content* both mean "in scope"; nothing is sent up front either way.)
Click a card's context icon to change it, or use the **Context** menu in the column header for all at once. Choices
aren't saved and reset when you reload.

Narrowing the scope helps when a notebook mixes topics; for a single course or project, leave everything in.

---

## Asking good questions

The agent resolves references itself, so you can ask the way you'd ask a person who has the documents:

- **Point at documents naturally**: "in the 4th lecture", "the paper by Kingma", "the slide after the ResNet one".
- **Ask for pages**: "What does page 12 of lecture 6 show?"
- **Ask about diagrams**: "In the residual block diagram, what's on the main path?" The agent looks at the page.
- **Ask across documents**: "Which lectures discuss dropout, and how do they differ?" It may run one sub-agent per
  document in parallel.
- **Ask for structure**: "Summarize lecture 6 section by section, then find related lectures."
- **Ask about a picture**: paste a screenshot of a slide or a homework problem and ask "which lecture covers this?"
- **Follow up**: "and the next lecture?", "expand on the second point". The agent sees the conversation (older turns
  as a summary).
- **Calculations** use an exact calculator: "how many weights does that layer have?"
- **Save things**: "save a short note summarizing this" creates a note; "remember that my exam is on Dec 10" adds it
  to the agent's [memory](../2-CORE-CONCEPTS/research-agent.md#memory).

If the notebook doesn't cover something, *Notebook only* answers say so and list what was searched. Switch to
*Notebook + general knowledge* if you want outside information.

---

## Working with answers

Under each answer:

- **N research steps**: expands the list of tool calls behind the answer.
- **Copy to clipboard**, and **Save to note** (saves it as an *AI Generated* note in this notebook).

References are explained in [Citations](citations.md).

## Sessions

A session is one conversation; it's saved and reloaded when you come back. **Sessions** opens the list, where you
can create, switch, rename or delete sessions. Starting a new session for a new topic keeps the agent's view of the
conversation focused. Attached images aren't saved with the session.

---

## Source chat

Each source has its own chat (open the source, **Chat with Sources**). It's the same agent limited to that one
source, with its own sessions and model choice. **Save to note** isn't available there; use **Copy to clipboard**.

---

## When something goes wrong

| Symptom | What to do |
|---|---|
| Answer cites no pages | The source has no pages (not a PDF, a scanned PDF, or added before page-aware ingestion). Re-add the PDF; see [Ingestion](../2-CORE-CONCEPTS/ingestion.md#re-processing). |
| *The model returned an empty answer…* | Retry. Already retried once automatically with less reasoning; if it keeps happening, pick another answer model. |
| "The notebook doesn't cover…" but it does | Check the source is in scope and finished processing; try **Deep**, or name the document. |
| Slow | Deep effort and cross-document questions take longer (30 s–2 min). Use **Quick** for lookups. |
| *No model configured…* | Set the default models: [Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent). |

More in [AI & Chat Issues](../6-TROUBLESHOOTING/ai-chat-issues.md).

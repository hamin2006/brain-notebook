# Chat vs. Ask vs. Transformations - Which Tool for Which Job?

Notebook chat, source chat and Ask all run the same [research agent](research-agent.md); they differ in scope and in
whether you can follow up. Transformations are different: a fixed prompt run on one source, saved as an insight.

| | Notebook Chat | Source Chat | Ask | Transformations |
|---|---|---|---|---|
| **Where** | Notebook page, conversation | Source page | Ask and Search → Ask | Add Source wizard, or a source's Insights tab |
| **What it uses** | The research agent over the notebook (sources and notes in scope) | The research agent over one source | The research agent over the notebooks you pick, or everything | One source's full text |
| **Follow-ups** | Yes, in saved sessions | Yes, in saved sessions | No | No |
| **Output** | Answer with page citations, research steps | Answer with page citations | Answer with citations | An insight attached to the source |
| **Extras** | Effort, grounding, image attachments | | | |
| **Save it** | **Save to note** | Copy to clipboard | **Save to Notebooks** | Already saved as an insight |
| **Models** | Tools Model researches, Chat Model (or the session's model) answers | Same | Tools Model researches, the Ask final-answer model answers | Transformation Model, or the transformation's own model |

---

## Notebook Chat - Research With Follow-Ups

The main way to use Brain Notebook. Ask anything about the notebook, from "what's on page 94 of lecture 4" to
"compare how lectures 3 and 4 treat regularization". Choose the **effort** per message and the **grounding** for the
notebook; paste screenshots; follow up and the agent resolves "it", "the next lecture" and so on from the
conversation.

→ [Chatting with the agent](../3-USER-GUIDE/chat-effectively.md)

## Source Chat - One Document

Each source has its own chat on its page, with the agent limited to that source. Useful for working through one
paper or deck; for anything that might involve other documents, use notebook chat.

## Ask - One Question Across Notebooks

The Ask page runs the agent over several notebooks or your whole knowledge base, without a conversation. Its
research steps appear as the "strategy", and the answer as the final answer. Use it when you don't know which notebook
holds the answer.

→ [Search and Ask](../3-USER-GUIDE/search.md)

## Transformations - The Same Prompt, Saved as an Insight

A transformation is a saved prompt (for example "Dense Summary" or "Table of Contents") that runs on one source and
stores the result as an **insight** on that source. Pick transformations when you add sources, or run one later from
the source's Insights tab. Insights are embedded and searchable. PDFs also get a *Document Summary* insight
automatically from [document analysis](ingestion.md#4-analysis), so you don't need a summary transformation for them.

→ [Transformations](../3-USER-GUIDE/transformations.md)

---

## Decision Guide

```
Do you want an AI answer?
├─ No, just find passages → Search (text or vector)
└─ Yes → Is it about one notebook?
         ├─ Yes → Notebook Chat (Source Chat for a single document)
         └─ No / not sure which → Ask
Want the same extraction stored for every source? → Transformation
```

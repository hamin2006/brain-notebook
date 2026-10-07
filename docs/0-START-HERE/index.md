# Brain Notebook - Start Here

**Brain Notebook** is a self-hosted research notebook. Add PDFs (lecture slides, papers, books), web pages, audio,
video and notes; then ask questions. A research agent investigates your documents the way you would: it finds the
right document, searches and greps it, reads the relevant pages, looks at slides whose meaning is in a diagram, and
answers with citations to the exact pages. Click a citation to see the page.

## Choose your path

### Recommended: OpenRouter + Docker
One API key gives you every model the agent uses (chat, research, embeddings, rerank, page-image embeddings).

→ [Quick Start](quick-start-cloud.md) (about 10 minutes, mostly the first image build)

### Other cloud providers (OpenAI, Anthropic, Google, …)
Same quick start; pick your provider when connecting models. Reranking and visual page search need an OpenRouter key
(they can be turned off).

### Local models with Ollama
Possible, with caveats: the research model must support tool calling, and page captions need a vision model.
→ [Local Quick Start](quick-start-local.md) · [Ollama already installed](quick-start-external-ollama.md)

### A Linux machine you'll keep running (home server, desktop)
→ [From source with systemd services](../1-INSTALLATION/from-source.md), the setup the reference deployment uses.

---

## What you can do

- **Ask research questions** about a notebook: "From lecture 4, what are Adam's default hyperparameters?",
  "Summarize lecture 6 and find related lectures", "Which lectures discuss dropout, and how do they differ?"
- **Get page citations** for every claim, and preview the cited page in the app
- **Ask about images**: paste a screenshot of a slide or a homework problem into chat
- **Choose the effort** per question (quick, standard, deep) and the **grounding** per notebook (notebook only, or
  notebook plus general knowledge and web search)
- **Search** by meaning, by exact words, or by what a page *looks like*
- **Keep notes**, run **transformations**, generate **podcasts** (inherited from Open Notebook)
- **Use it from Claude Code** or other MCP clients

## Prerequisites

- **Docker** (Compose v2), or for a source install: Python 3.11–3.12 with [uv](https://docs.astral.sh/uv/), Node.js 22, and SurrealDB v2 (Docker is the easy way to run it)
- **An AI provider key**; OpenRouter is recommended
- About 2.5 GB of RAM for the app and database with a few hundred pages ingested

---

**Need help?** See the [full documentation](../index.md) or [troubleshooting](../6-TROUBLESHOOTING/index.md).

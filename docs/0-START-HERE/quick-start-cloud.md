# Quick Start - Docker + OpenRouter (10 minutes)

Run Brain Notebook with Docker and the recommended OpenRouter models, then get a cited answer from one of your own
PDFs. Other cloud providers work the same way; see the note in Step 3.

## Prerequisites

1. **Docker with Compose v2**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) on macOS and Windows,
   Docker Engine with the Compose plugin on Linux.
2. **git**.
3. **An [OpenRouter API key](https://openrouter.ai/keys)** with a few dollars of credit. A typical question costs
   about $0.003; ingesting a 100-slide deck a few cents (captions, analysis, embeddings, concept graph).

## Step 1: Get the code and set the encryption key (1 min)

```bash
git clone https://github.com/hamin2006/brain-notebook.git
cd brain-notebook
```

Open `docker-compose.yml` and replace `change-me-to-a-secret-string` in the `OPEN_NOTEBOOK_ENCRYPTION_KEY` line with
a long random secret, for example the output of `openssl rand -hex 32`. It encrypts the API keys you store in the app;
keep it, or saved keys can't be decrypted.

> **Shared network?** The UI (`8502`) and API (`5055`) are published on all interfaces with no password. If other
> devices can reach this machine, change the two `open_notebook` port lines to `"127.0.0.1:8502:8502"` and
> `"127.0.0.1:5055:5055"`, or add `- OPEN_NOTEBOOK_PASSWORD=your-password` to its `environment:` block.

## Step 2: Build and start (5 min the first time)

```bash
docker compose up -d --build
```

This builds the app image from the repository (the upstream `lfnovo/open_notebook` images don't contain the research
agent), starts SurrealDB, and runs the database migrations. When `docker compose logs open_notebook | grep "version 29"`
shows *Database is now at version 29*, open **http://localhost:8502**.

## Step 3: Connect the models (2 min)

From the `brain-notebook` folder:

```bash
OPENROUTER_API_KEY=sk-or-... python3 scripts/brain/provision_models.py
```

(Without the variable it asks for the key; the script only needs Python 3, no packages.) It stores your key in the app
(encrypted), adds three models and sets them as defaults:

| Default | Model | Role |
|---|---|---|
| Chat, Transformation, Large Context | `z-ai/glm-5.3-flash` | Writes answers; captions slides; analyzes documents |
| Tools | `qwen/qwen3.7-flash` | The research agent's tool calls (cheap, fast, can see images) |
| Embedding | `qwen/qwen3-embedding-8b` | Passage, section and document search |

Each model is tested; you should see three `ok` lines. Reranking (`voyageai/rerank-3-lite`) and page-image embeddings
(`google/gemini-embedding-2`) use the same key automatically.

**Another provider instead?** Connect it under **Manage → Models** and set the defaults yourself:
[Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent). Without an OpenRouter key,
turn off reranking and visual page search in **Settings → Research agent**.

## Step 4: Ask your first question (2 min)

1. **Notebooks → New Notebook**, give it a name.
2. **Add Source → Add Source → Upload File**, pick a PDF (slides or a paper), and finish the dialog.
3. Wait until the source shows as processed. A 100-page deck takes a few minutes: pages are extracted, visual pages
   captioned, then the document is analyzed (outline, summaries, metadata) and its pages are embedded.
4. In the chat panel ask something specific, e.g. *"What does the slide on page 12 say about X?"* or *"Summarize this
   document section by section"*, and press **Enter**.

You'll see the agent's research steps live ("Searching for…", "Reading…"), then the answer with citations like
`[1]` that show the page range. Click one to preview the page.

## Verification checklist

- [ ] `docker compose ps` shows `surrealdb` and `open_notebook` running
- [ ] http://localhost:8502 opens
- [ ] `provision_models.py` printed three `ok` lines
- [ ] The uploaded PDF finished processing (its status no longer shows as processing)
- [ ] A question gets an answer with page citations

## Optional

- **Web search** (free, self-hosted): add `SEARXNG_SECRET=$(openssl rand -hex 32)` to a `.env` file next to
  `docker-compose.yml`, run `docker compose --profile web up -d`, then turn on **Settings → Research agent → Web search**.
  The agent uses the web only in notebooks set to *Notebook + general knowledge*. See [Web search](../5-CONFIGURATION/research-agent.md#web-search).
- **Claude Code**: `claude mcp add --transport http brain http://localhost:8502/mcp`. See [MCP](../5-CONFIGURATION/mcp-integration.md).
- **Podcasts / audio sources**: add a text-to-speech or speech-to-text model under **Manage → Models**.

## Troubleshooting

- **`provision_models.py` can't connect**: the API isn't up yet (wait for the migrations) or isn't on `127.0.0.1:5055`;
  pass `--api http://host:5055/api`.
- **A model test fails**: check the key and your OpenRouter credit.
- **The source never finishes**: `docker compose logs -f open_notebook` shows the worker; see [Processing issues](../6-TROUBLESHOOTING/processing-issues.md).
- **Port 8502 is in use**: change `"8502:8502"` to e.g. `"8503:8502"` and run `docker compose up -d`.
- More: [Quick Fixes](../6-TROUBLESHOOTING/quick-fixes.md).

## Next steps

- [Chatting with the agent](../3-USER-GUIDE/chat-effectively.md): effort, grounding, images, follow-ups
- [How the research agent works](../2-CORE-CONCEPTS/research-agent.md)
- [Docker Compose guide](../1-INSTALLATION/docker-compose.md): settings, backups, updates, remote access

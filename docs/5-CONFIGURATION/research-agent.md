# Research Agent Settings

**Settings → Research agent** holds the switches for the research agent's optional parts. Model fields take an
OpenRouter model id; **leave a model empty to turn that feature off**. Changes apply to the next question (and, for
ingestion features, to the next source processed). The same settings are available through the API:
`GET` / `PUT /api/agent/settings`.

| Setting | Default | What it does |
|---|---|---|
| **Rerank model** | `voyageai/rerank-3-lite` | Reorders passage and section search candidates |
| **Page image embedding model** | `google/gemini-embedding-2` | Visual page search |
| **Concept graph** | on | Extract concepts and relations after document analysis |
| **Memory** | on | The agent's `remember` / `forget` tools and remembered items in its prompt |
| **Web search** | off | `web_search` / `web_read` in notebooks set to *Notebook + general knowledge* |

The card also lists **Remembered** items with a button to forget each one.

The models the agent itself uses (research, answers, analysis, embeddings) are set in **Manage → Models**: see
[Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent). Reranking and page-image
embeddings use your OpenRouter configuration (or `OPENROUTER_API_KEY` in the environment).

---

## Reranking

`search` gathers up to max(3 × limit, 24) candidates from its keyword and vector legs, fuses them, and asks the rerank
model to put the best first. Rerankers read the query and each passage together, so they're much better than vector
similarity at "which of these actually answers the question". `voyageai/rerank-3-lite` costs about $0.00006 per
search and adds ~0.3 s. Other OpenRouter rerank models work (`cohere/rerank-v3.5`, `qwen/qwen3-reranker-8b`, …).

If reranking is off or the call fails, the fused order is used. Searches without text (`like=`) aren't reranked.

---

## Visual page search

After a PDF is analyzed, every page is rendered (1024 px) and embedded with the page image embedding model, one
render per animation build. The agent can then:

- `search(level="page", query="diagram of a residual block")`: describe what a page looks like
- `search(level="page", like="source:abc#p48")`: pages that look like another page
- `search(image="attachment:1")`: pages that look like an image you attached to your message

`google/gemini-embedding-2` costs about $0.0001 per page. Alternatives on OpenRouter: `voyageai/voyage-multimodal-3.5`
(~10× the price) or `nvidia/llama-nemotron-embed-vl-1b-v2:free` (free, rate-limited). Vectors from different models
can't be compared: after changing the model, click **Embed pages of existing documents**, which re-embeds pages that
are missing an embedding. To force a full re-embed use the API:
`POST /api/agent/rebuild {"what": "page_embeddings", "force": true}`.

---

## Concept graph

After analysis, the research (Tools) model lists each section's key concepts and the relations the section states,
merged across documents by name and abbreviation. The agent's `graph` tool reads it. Extraction costs roughly
$0.01 per 100-page deck with the recommended models.

**Build concept graph for existing documents** rebuilds the whole graph from scratch (it clears it first), which also
applies any improvement in naming or merging to older documents. API:
`POST /api/agent/rebuild {"what": "concepts", "reset": true}`.

---

## Memory

When on, the agent gets `remember` and `forget` tools and sees remembered items at the start of every turn (all of
them up to 20, otherwise the 20 most relevant to the question). It's told to remember only what you ask it to, or
lasting preferences you state, never facts from the documents. Items are stored per notebook, or "everywhere" for
things about you. API: `GET /api/agent/memories`, `DELETE /api/agent/memories/{id}`.

---

## Web search

Web search runs through **SearXNG**, a self-hosted metasearch engine that queries public search engines for you: no
API key, no per-search cost. The agent gets two tools:

- `web_search(query)`: titles, URLs and snippets
- `web_read(url)`: fetches a page (or an online PDF) and keeps its main text

They're offered only when **Web search** is on **and** the notebook's grounding is *Notebook + general knowledge*.
The agent is told to use the notebook first and the web for what it lacks, to prefer authoritative sources, and to
cite web facts with links. A search takes about 1–2 s.

### Running SearXNG

**Docker Compose**: the root `docker-compose.yml` has a `searxng` service in the `web` profile:

```bash
echo "SEARXNG_SECRET=$(openssl rand -hex 32)" >> .env
docker compose --profile web up -d
```

**From source**: a separate compose project in `scripts/brain/searxng/` (localhost:8888, 512 MB memory cap):

```bash
cd scripts/brain/searxng
echo "SEARXNG_SECRET=$(openssl rand -hex 32)" > .env
docker compose up -d
```

The API finds it at `SEARXNG_URL` (default `http://127.0.0.1:8888`; the Docker Compose setup sets
`http://searxng:8080`). Its settings (`scripts/brain/searxng/settings.yml`) enable the JSON API and turn off the bot
limiter, since only the API talks to it. It uses about 120 MB of RAM.

Some upstream engines occasionally refuse automated queries (a DuckDuckGo CAPTCHA, Brave rate limits); SearXNG still
returns results from the others.

### Safety

Web pages are untrusted input chosen by a model, so `web_read` is strict:

- only `http` and `https`;
- only **public** addresses: hosts that resolve to localhost, private networks, link-local, Tailscale (100.64.0.0/10)
  or cloud metadata addresses are refused, so a page can't steer the agent into your LAN or this machine;
- every redirect hop is checked again, and the connection is pinned to the vetted IP (no DNS rebinding);
- responses are capped at 3 MB;
- page text is labeled untrusted and the agent is told never to follow instructions in it.

Search queries leave your machine (through SearXNG to the search engines), as do the fetched pages' requests.

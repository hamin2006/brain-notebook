<a id="readme-top"></a>

<div align="center">
  <img src="docs/assets/hero.svg" alt="Brain Notebook">

  <h3 align="center">Brain Notebook</h3>

  <p align="center">
    A self-hosted research notebook whose chat is a research agent: it reads your PDFs, slides and notes,
    looks at diagrams, and answers with page citations.
    <br />
    <a href="docs/0-START-HERE/index.md"><strong>Get started »</strong></a>
    ·
    <a href="docs/3-USER-GUIDE/index.md">User guide</a>
    ·
    <a href="docs/2-CORE-CONCEPTS/research-agent.md">How the agent works</a>
    ·
    <a href="docs/1-INSTALLATION/index.md">Install</a>
  </p>
</div>

Brain Notebook is a fork of [Open Notebook](https://github.com/lfnovo/open-notebook) (1.15.0), the open-source
NotebookLM alternative, rebuilt around **agentic retrieval**. Instead of pasting selected documents into one
prompt, every question is researched: the agent lists your documents, greps and searches them, reads the pages it
needs, looks at slides when the answer is in a diagram, and only then writes a cited answer.

![The notebook workspace: an answer with page citations, and the cited slide in the evidence panel](docs/assets/screenshots/workspace.webp)

## A tour

<table>
<tr>
<td width="50%" valign="top">

**Watch it research.** Every question runs a visible investigation: the agent searches, greps, reads page ranges
and *looks at* slides, and each step shows what it found.

<img src="docs/assets/screenshots/research-live.webp" alt="Live research timeline: search, grep, read and view steps with their results">

</td>
<td width="50%" valign="top">

**Check every claim.** Citations are numbered chips; hover one to see the exact page, click it to open the page
beside the answer. Every answer ends with thumbnails of the pages it cites.

<img src="docs/assets/screenshots/citations.webp" alt="Hovering a citation previews the cited slide">

</td>
</tr>
<tr>
<td width="50%" valign="top">

**See how ideas connect.** The concept graph maps every concept across your documents: one column per lecture,
relations the slides state as curved links, shared sections as faint ones.

<img src="docs/assets/screenshots/concept-graph.webp" alt="Concept graph of seven lectures, coloured by the lecture that introduces each concept">

</td>
<td width="50%" valign="top">

**Follow a concept.** Hover to light up its neighbourhood and relation names; click to see where every document
covers it, and ask the agent about it in one click.

<img src="docs/assets/screenshots/concept-graph-focus.webp" alt="Backpropagation focused in the graph, with its relations and mentions in the side panel">

</td>
</tr>
<tr>
<td width="50%" valign="top">

**Start from what's there.** An empty conversation knows the notebook: its size, starter questions built from its
own key concepts, and the concepts themselves.

<img src="docs/assets/screenshots/welcome.webp" alt="Empty conversation with notebook stats, starter questions and key concepts">

</td>
<td width="50%" valign="top">

**Documents with structure.** Each PDF gets metadata, a summary, an outline with page ranges and section
summaries, its concepts and every page as a thumbnail.

<img src="docs/assets/screenshots/source-structure.webp" alt="A lecture's Structure tab: outline section with its pages and summary">

</td>
</tr>
<tr>
<td width="50%" valign="top">

**Cheat sheets for the exam.** Pick the lectures; get a dense, page-budgeted recall sheet in the course's notation,
every line cited to its slide. Comment on lines, pin or edit them, and **Revise**; the page measures whether it fits.

<img src="docs/assets/screenshots/cheat-sheet.webp" alt="A two-page cheat sheet over 72 lectures, a selected line with its comment and the review panel">

</td>
<td width="50%" valign="top">

**It prints as a real sheet.** Letter or A4, 2–4 columns, rendered math; or export `.tex`. Every formula comes
from the slides: a request for something the course doesn't teach is declined, not invented.

<img src="docs/assets/screenshots/cheat-sheet-print.webp" alt="The first printed page of a Calculus 2 cheat sheet">

</td>
</tr>
</table>

<p align="center">
  <img src="docs/assets/screenshots/concept-graph-3d.webp" alt="The concept graph in 3D, orbiting, glowing nodes coloured by lecture" width="80%">
  <br><sub>…or explore it in 3D: an orbiting scene where focusing a concept sends particles along its relations.</sub>
</p>

<p align="center">
  <img src="docs/assets/screenshots/home.webp" alt="Home: ask across all notebooks, recent items and notebook cards" width="80%">
  <br><sub>Home: ask across every notebook, jump back in, notebooks with their decks as covers. Light and dark themes, 14 languages.</sub>
</p>

## What it does

**Research agent (notebook chat, source chat, Ask, MCP)**
- Tools instead of prompt stuffing: `list`, `grep`, `search` (passage / section / document / *page appearance*),
  `outline`, `read`, `view` (the page as an image), `graph`, `calculate`, `note`, and `delegate` (parallel
  sub-agents, one per document).
- Every claim cites the most specific address it read: `[source:abc#p94]`. Hover a citation to preview the page,
  click it to open the page beside the answer.
- Effort levels: *quick*, *standard*, *deep* (deep adds a reviewer that sends the agent back for gaps).
- Two models per question: a cheap research model makes the many tool calls, a stronger model writes the answer
  once. On the 35-question course eval this costs about **$0.003 per question**.
- Grounding per notebook: *Notebook only* (says when the notebook doesn't cover something) or *Notebook + general
  knowledge*, optionally with **web search** through a self-hosted SearXNG (no API key).
- Memory across conversations (only what you ask it to remember), and long chats are compacted, not truncated.
- Paste a screenshot into chat and ask about it; the agent can find notebook pages that look like it.

**Ingestion built for lecture slides and papers**
- PDFs are read page by page: equations hidden by LaTeXiT become LaTeX again, animation builds are merged, and
  pages that are mostly pictures get a vision-model caption.
- Each document gets metadata (type, course, number in the series, topics), an outline of topic sections with
  page ranges, section summaries and a document summary.
- Page images are embedded for **visual search** ("the slide with the inception module diagram"), passages are
  **reranked**, and a **concept graph** links ideas across documents.

**A workspace built for research**
- Library (sources, notes, concepts) · conversation · evidence panel, side by side; the live research timeline;
  starter questions from the notebook's own concepts; **New chat** and saved sessions.
- An interactive **concept graph** of the whole notebook, and a **Structure** view of every document.
- Ask across all notebooks from the home page; paste or drop images into chat.
- **Cheat sheets**: a printable one- or two-page recall sheet of the formulas, definitions and methods in the
  lectures you pick, every line cited to its slide, revised from your comments; about $0.05 for a 72-lecture
  course, then a cent per sheet or revision.

**Everything Open Notebook already had**: notebooks, sources of many types (PDF, web, audio, video, Office), notes,
transformations, podcasts, 20+ AI providers, REST API, 14 UI languages.

**Use it from Claude Code**: the app is an MCP server (`/mcp`) exposing `ask` and the agent's tools, including page
images.

### How well it works

On a 35-question eval over seven deep-learning lecture decks (locate facts, read diagrams, summarize, compare across
lectures, enumerate, follow-ups, "not covered" questions):

| | Open Notebook chat (documents in the prompt) | Brain Notebook |
|---|---|---|
| Correct | 27 / 35 | **35 / 35** |
| Cites the right page | 1 / 30 | **30 / 30** |
| Facts only visible in images | 2 / 6 | **6 / 6** |
| Cost for the run | $0.34 | **$0.10** |

Details: [docs/7-DEVELOPMENT/plans/agentic-rag.md](docs/7-DEVELOPMENT/plans/agentic-rag.md).

## Quick start (Docker)

You need Docker with Compose and an [OpenRouter](https://openrouter.ai/keys) API key (other providers work too; see
[AI providers](docs/4-AI-PROVIDERS/index.md)).

```bash
git clone https://github.com/hamin2006/brain-notebook.git
cd brain-notebook
# Set the key that encrypts stored API keys (pick your own secret):
sed -i.bak "s/change-me-to-a-secret-string/$(openssl rand -hex 32)/" docker-compose.yml
docker compose up -d --build        # first build takes a few minutes
```

Open **http://localhost:8502**, then set up the models (one command, uses the recommended OpenRouter models):

```bash
OPENROUTER_API_KEY=sk-or-... python3 scripts/brain/provision_models.py
```

…or do it by hand under **Manage → Models** (see [Models for the agent](docs/4-AI-PROVIDERS/index.md#models-for-the-research-agent)).
Create a notebook, upload a PDF, wait for it to finish processing, and ask a question.

Optional web search: `docker compose --profile web up -d`, then **Settings → Research agent → Web search**.

> The UI and API listen on all interfaces with no password. On a shared network, bind the ports to `127.0.0.1`
> or set `OPEN_NOTEBOOK_PASSWORD` first ([security](docs/5-CONFIGURATION/security.md)).

Other ways to install: [from source with systemd services](docs/1-INSTALLATION/from-source.md) (what the reference
deployment runs), [Docker Compose in depth](docs/1-INSTALLATION/docker-compose.md), [all options](docs/1-INSTALLATION/index.md).

## Documentation

| Start | Use | Configure | Develop |
|---|---|---|---|
| [Overview](docs/0-START-HERE/index.md) | [Interface](docs/3-USER-GUIDE/interface-overview.md) | [AI providers & models](docs/4-AI-PROVIDERS/index.md) | [Architecture](docs/7-DEVELOPMENT/architecture.md) |
| [Quick start](docs/0-START-HERE/quick-start-cloud.md) | [Adding sources](docs/3-USER-GUIDE/adding-sources.md) | [Research agent settings](docs/5-CONFIGURATION/research-agent.md) | [Development setup](docs/7-DEVELOPMENT/development-setup.md) |
| [Install](docs/1-INSTALLATION/index.md) | [Chatting with the agent](docs/3-USER-GUIDE/chat-effectively.md) | [Environment variables](docs/5-CONFIGURATION/environment-reference.md) | [Testing & evals](docs/7-DEVELOPMENT/testing.md) |
| [How the agent works](docs/2-CORE-CONCEPTS/research-agent.md) | [Citations](docs/3-USER-GUIDE/citations.md) · [Search & Ask](docs/3-USER-GUIDE/search.md) | [MCP](docs/5-CONFIGURATION/mcp-integration.md) · [Security](docs/5-CONFIGURATION/security.md) | [API reference](docs/7-DEVELOPMENT/api-reference.md) |

Troubleshooting: [quick fixes](docs/6-TROUBLESHOOTING/quick-fixes.md). Changes: [CHANGELOG](CHANGELOG.md).

## Stack

Python 3.12 · FastAPI · LangGraph · SurrealDB v2 · Next.js / React · surreal-commands worker · OpenRouter (or any
provider via [Esperanto](https://github.com/lfnovo/esperanto)) · optional SearXNG.

## Relationship to Open Notebook

Brain Notebook is a personal fork. Code identifiers keep upstream's names (the `open_notebook` Python package,
`OPEN_NOTEBOOK_*` environment variables, the `open_notebook` database namespace) so upstream fixes can still be
merged. Upstream's Docker images (`lfnovo/open_notebook`) do **not** contain any of the features above; build this
repository instead. Open Notebook's community channels are for Open Notebook, not this fork.

## License

MIT, like Open Notebook. See [LICENSE](LICENSE). Open Notebook © 2024 Luis Novo.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

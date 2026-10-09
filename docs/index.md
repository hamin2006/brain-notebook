# Brain Notebook Documentation

Brain Notebook is a self-hosted research notebook whose chat is a research agent: it searches, reads and *looks at*
your documents, then answers with page citations. It is a fork of [Open Notebook](https://github.com/lfnovo/open-notebook);
most of Open Notebook's features (sources, notes, transformations, podcasts, 20+ providers) are still here.

![The notebook workspace: an answer with page citations and the cited slide beside it](assets/screenshots/workspace.webp)

New here? Start with **[0-START-HERE](0-START-HERE/index.md)**. For a tour of the interface, see
[Interface Overview](3-USER-GUIDE/interface-overview.md).

| Section | Read it when you want to… |
|---|---|
| **[0-START-HERE](0-START-HERE/index.md)** | Install for the first time and get a cited answer from your own PDFs |
| **[1-INSTALLATION](1-INSTALLATION/index.md)** | Choose an install route: Docker Compose (builds this repo) or from source with systemd services |
| **[2-CORE-CONCEPTS](2-CORE-CONCEPTS/index.md)** | Understand the research agent, how documents are ingested, notebooks/sources/notes |
| **[3-USER-GUIDE](3-USER-GUIDE/index.md)** | Add sources, chat with the agent, read citations, search and Ask, take notes, make [cheat sheets](3-USER-GUIDE/cheat-sheets.md) |
| **[4-AI-PROVIDERS](4-AI-PROVIDERS/index.md)** | Connect a provider and pick the models the agent uses |
| **[5-CONFIGURATION](5-CONFIGURATION/index.md)** | Research agent settings (rerank, visual search, concept graph, memory, web search), MCP, environment variables, security |
| **[6-TROUBLESHOOTING](6-TROUBLESHOOTING/index.md)** | Fix something that isn't working |
| **[7-DEVELOPMENT](7-DEVELOPMENT/index.md)** | Architecture, development setup, tests and evals, API reference, decision records |

## Common questions

- **The chat answers but cites no pages.** The source was added before page-aware ingestion, or isn't a PDF with a text layer. Re-add it, or see [How documents are ingested](2-CORE-CONCEPTS/ingestion.md).
- **Which models should I use?** [Models for the research agent](4-AI-PROVIDERS/index.md#models-for-the-research-agent).
- **Can it search the web?** Yes, through a self-hosted SearXNG, in notebooks set to allow general knowledge: [Web search](5-CONFIGURATION/research-agent.md#web-search).
- **Can Claude Code use my notebooks?** Yes, over MCP: [MCP integration](5-CONFIGURATION/mcp-integration.md).
- **Something's broken.** [Quick Fixes](6-TROUBLESHOOTING/quick-fixes.md) · [AI & Chat Issues](6-TROUBLESHOOTING/ai-chat-issues.md) · [Processing Issues](6-TROUBLESHOOTING/processing-issues.md)

## Getting help

Brain Notebook is a personal fork: open an issue at https://github.com/hamin2006/brain-notebook/issues. Open
Notebook's Discord and issue tracker are for upstream Open Notebook.

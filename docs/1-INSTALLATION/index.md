# Installation Guide

Pick the route that fits your setup. Both end the same way: open the UI and set up the models
([script or by hand](../4-AI-PROVIDERS/index.md#models-for-the-research-agent)).

| Route | For | You need |
|---|---|---|
| **[Docker Compose](docker-compose.md)** (recommended) | Laptops, home servers, VPS | Docker with Compose v2, git |
| **[From source + systemd services](from-source.md)** | A Linux machine you keep running (the reference deployment), and development | Python 3.11–3.12, uv, Node.js 22, Docker or a SurrealDB v2 binary, ffmpeg |
| [Windows Native](windows-native.md) | Windows without Docker or WSL | Python via uv, Node.js 22, SurrealDB 2.x, ffmpeg (not tested by this fork) |
| [Single Container](single-container.md) | Hosts that run one container per app | Build the `single` target yourself (not tested by this fork) |

The Docker Compose file **builds this repository**. Upstream Open Notebook's prebuilt images
(`lfnovo/open_notebook`) don't contain the research agent; don't use them for Brain Notebook.

---

## System requirements

- **RAM:** about 2.5 GB in use for the app and SurrealDB with a few hundred PDF pages ingested (SurrealDB is the
  largest part, about 1.9 GB, because it keeps the embeddings in memory). Optional SearXNG adds about 120 MB.
  4 GB free is comfortable; local models need much more.
- **Disk:** the app image (~600 MB), your documents (originals are kept so the agent can look at pages), and the
  database.
- **GPU:** not needed unless you run local models.
- **Network:** to reach your AI provider. Everything else (database, search, web search) runs locally.

## AI providers

The recommended setup is **OpenRouter**: one key covers the answer model, the cheap research model, embeddings,
reranking and page-image embeddings. Any provider supported by Open Notebook can run chat and embeddings; reranking
and visual page search are OpenRouter-only and can be turned off. See [AI Providers](../4-AI-PROVIDERS/index.md).

---

## After installing

1. Set up the models: [Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent).
2. Create a notebook, upload a PDF and ask a question: [User Guide](../3-USER-GUIDE/index.md).
3. Optional: [web search](../5-CONFIGURATION/research-agent.md#web-search), [MCP for Claude Code](../5-CONFIGURATION/mcp-integration.md).

## Before exposing it to a network

The defaults are for a single user on a trusted machine: authentication is off and CORS is open.

- Set `OPEN_NOTEBOOK_PASSWORD`: [Security](../5-CONFIGURATION/security.md)
- Prefer a private network (Tailscale, a VPN) or HTTPS: [Reverse Proxy](../5-CONFIGURATION/reverse-proxy.md)
- MCP clients on other machines must be allowed explicitly: [MCP](../5-CONFIGURATION/mcp-integration.md)

## Need help?

- [Quick Fixes](../6-TROUBLESHOOTING/quick-fixes.md)
- [GitHub Issues](https://github.com/hamin2006/brain-notebook/issues)

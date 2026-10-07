# MCP Integration

Brain Notebook is an [MCP](https://modelcontextprotocol.io) server. Claude Code, Claude Desktop, VS Code and other
MCP clients can use your notebooks two ways:

- **`ask`**: the built-in research agent answers a question with page citations (10–60 s).
- **The agent's own tools**: the client's model does the research itself with `list_documents`, `grep`, `search`,
  `outline`, `read`, `graph` and `view`. `view` returns the page **as an image**, so a client like Claude can read
  diagrams with its own vision.

## Endpoint

The API serves MCP over streamable HTTP at **`/mcp`** (stateless, JSON responses). The web UI proxies it, so use
whichever address you open the UI with:

| Setup | URL |
|---|---|
| Docker Compose | `http://localhost:8502/mcp` (or `http://localhost:5055/mcp` directly) |
| From source (systemd) | `http://<ui-host>:3000/mcp` |
| Development | `http://localhost:5055/mcp` |

## Connect a client

**Claude Code**

```bash
claude mcp add --transport http brain http://localhost:8502/mcp
```

**VS Code** (`.vscode/mcp.json`)

```json
{
  "servers": {
    "brain": { "type": "http", "url": "http://localhost:8502/mcp" }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`), through the `mcp-remote` bridge:

```json
{
  "mcpServers": {
    "brain": { "command": "npx", "args": ["-y", "mcp-remote", "http://localhost:8502/mcp"] }
  }
}
```

If `OPEN_NOTEBOOK_PASSWORD` is set, every request needs `Authorization: Bearer <password>`: for Claude Code add
`--header "Authorization: Bearer <password>"`; for `mcp-remote` add `"--header", "Authorization: Bearer <password>"`
to `args`.

## From another machine

Requests are checked against an allowed-hosts list (protection against DNS rebinding): `localhost`, `127.0.0.1` and
`::1` are allowed; anything else must be listed in **`OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS`** on the API, as
comma-separated `host:port` patterns:

```env
OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS=100.120.164.122:*,notebook.lan:*
```

(Docker Compose: add `- OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS=...` to the `open_notebook` service's `environment:` block.)
Then connect to `http://<that host>:<ui port>/mcp`. A private network such as Tailscale is the simplest safe way to
reach it.

## Tools

Every tool takes an optional `notebook`: a notebook id (`notebook:abc`) or its name (case-insensitive). Omit it to
use all notebooks.

| Tool | Arguments | Returns |
|---|---|---|
| `list_notebooks` | | Notebooks with ids and document/note counts |
| `ask` | `question`, `notebook`, `effort` (`quick` / `standard` / `deep`) | The research agent's cited answer |
| `list_documents` | `doc_type`, `course`, `sequence`, `title_contains`, `sort` | The document catalog |
| `grep` | `pattern` (regex), `addresses` | Every match, with counts and pages |
| `search` | `query`, `level` (`passage` / `section` / `document` / `page`), `addresses`, `like`, `limit` | Ranked hits with addresses |
| `outline` | `source` | Metadata and sections with page ranges |
| `read` | `address` (`source:abc#p12-18`, `#s3`, `/summary`, `note:xyz`), `limit` | Text |
| `graph` | `concept`, `limit` | Where a concept appears and its relations, or the most shared concepts |
| `view` | `address` (a page) | A short text plus the page image |

All tools return [addresses](../2-CORE-CONCEPTS/research-agent.md#addresses-and-citations); the server's
instructions tell clients to cite them. Results are plain text, the same as the built-in agent sees.

`ask` uses the notebook's grounding and your default models; web search is available to it only in notebooks set to
*Notebook + general knowledge* with web search turned on.

## Troubleshooting

- **HTTP 421 / "Invalid Host header"**: the host you connect with isn't in `OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS`.
- **401**: a password is set; send the Bearer header.
- **`ask` returns nothing after ~30 s through the UI port**: an old UI build with Next.js's default proxy timeout;
  current builds wait up to 10 minutes (`API_PROXY_TIMEOUT_MS`). Rebuild the UI.
- **`view` says the file isn't stored**: the source's original file was deleted (`auto_delete_files`); re-add it.

The community `open-notebook-mcp` package wraps upstream Open Notebook's REST API; it isn't needed here.

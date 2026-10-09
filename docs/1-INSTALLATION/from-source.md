# From Source Installation

Run Brain Notebook directly on a machine, without the app container. Two ways to run it:

- **As services (Linux, systemd)**: the API, worker and a production build of the UI run as user services that start
  on boot and restart on failure. This is how the reference deployment runs (a Linux desktop reached over Tailscale).
- **For development**: each process in its own terminal, with hot reload. See [Development](#5b-development-mode).

Both need the same preparation (steps 1–4).

| Process | Service | Port |
|---|---|---|
| SurrealDB (Docker) | `docker compose up -d surrealdb` | 127.0.0.1:8000 |
| API (FastAPI; runs migrations on start) | `brain-api` | 127.0.0.1:5055 |
| Background worker (ingestion, embeddings, analysis) | `brain-worker` | none |
| Web UI (proxies `/api` and `/mcp` to the API) | `brain-frontend` | 3000 (you choose the address) |
| SearXNG, optional (web search) | Docker, `scripts/brain/searxng` | 127.0.0.1:8888 |

## Prerequisites

- **Python 3.11 or 3.12** (3.13 isn't supported yet); [uv](https://docs.astral.sh/uv/) installs one for you:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node.js 22** (20.9 is the minimum Next.js 16 accepts)
- **Docker**, for SurrealDB (and SearXNG). A SurrealDB v2 binary works too.
- **git**, and **ffmpeg** if you'll add audio/video sources or make podcasts
- Optional: **LibreOffice** (`sudo apt install --no-install-recommends libreoffice-impress libreoffice-writer`), so
  PowerPoint and Word uploads are converted to PDF and get pages, captions and an outline

## 1. Clone and install dependencies

```bash
git clone https://github.com/hamin2006/brain-notebook.git
cd brain-notebook
uv sync
```

## 2. Create `.env`

```bash
cp .env.example .env
uv run python -c "import secrets; print(secrets.token_hex(32))"   # your encryption key
```

Edit `.env`:

```env
OPEN_NOTEBOOK_ENCRYPTION_KEY=<the value you generated>
SURREAL_URL=ws://127.0.0.1:8000/rpc
```

Keep the key: if it changes, stored API keys can't be decrypted. The example file's `SURREAL_URL` points at
`surrealdb`, a host name that only exists inside Docker Compose; processes on the host use `127.0.0.1`.

Optional lines (all documented in [Environment Reference](../5-CONFIGURATION/environment-reference.md)):

```env
# Smaller embedding batches if your provider times out on large ones
OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE=16
# SearXNG for web search (this is the default)
SEARXNG_URL=http://127.0.0.1:8888
# MCP clients reaching this machine by another address (e.g. a Tailscale IP)
OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS=100.64.0.10:*
```

## 3. Start SurrealDB

```bash
docker compose up -d surrealdb
```

It uses the repository's `docker-compose.yml` (data in `./surreal_data`, port bound to `127.0.0.1:8000`) and reads
`SURREAL_USER` / `SURREAL_PASSWORD` from `.env`, so the database and the API agree on credentials. `make database` does
the same.

## 4. Build the UI

```bash
bash scripts/brain/build_frontend.sh
```

This runs `npm ci` and a production build, and copies the static assets next to the standalone server (about 30 s on
a desktop).

## 5a. Run as services (Linux)

```bash
bash scripts/brain/install_services.sh --host 127.0.0.1 --port 3000
```

It writes `brain-api`, `brain-worker` and `brain-frontend` to `~/.config/systemd/user/` for this checkout, enables and
starts them. `--host` is where the UI listens: `127.0.0.1` for this machine only, a Tailscale or LAN address to reach
it from other devices, or `0.0.0.0` for every interface (set a password first: [Security](../5-CONFIGURATION/security.md)).
The API stays on `127.0.0.1:5055`; the UI proxies `/api` and `/mcp` to it.

To keep the services running when you're logged out and start them at boot:

```bash
sudo loginctl enable-linger "$USER"
```

Check them with `systemctl --user status brain-api brain-worker brain-frontend` and follow logs with
`journalctl --user -u brain-worker -f`.

**Updating** an installed checkout: `bash scripts/brain/deploy_pc.sh`. It fast-forwards the current branch, syncs
dependencies, rebuilds the UI when `frontend/` changed, moves units written by an older installer to the current
settings, restarts the API and waits for it (up to 10 minutes; migrations run on start), then restarts the worker and
the UI. It says when LibreOffice is missing.

The units cap memory: API 1 GB, worker 2.5 GB (with its PDF parsers), UI 512 MB; SurrealDB from `docker-compose.yml`
is limited to 1.5 GB. Peaks during a large upload are about 2 GB in total. After pulling a change to
`docker-compose.yml`, apply it with `docker compose up -d surrealdb`.

## 5b. Development mode

Four terminals (or `make start-all` / `make stop-all` once everything works):

```bash
make database                       # 1: SurrealDB
make api                            # 2: API on :5055, auto-reload
make worker                         # 3: background worker
cd frontend && npm install && npm run dev   # 4: UI on http://localhost:3000, hot reload
```

Without the worker, new sources stay queued forever. More in [Development Setup](../7-DEVELOPMENT/development-setup.md).

## 6. Set up the models

With the API running:

```bash
OPENROUTER_API_KEY=sk-or-... python3 scripts/brain/provision_models.py
```

or by hand: [Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent). Then open the UI,
create a notebook, upload a PDF and ask a question.

## 7. Optional: web search and MCP

```bash
cd scripts/brain/searxng
echo "SEARXNG_SECRET=$(openssl rand -hex 32)" > .env
docker compose up -d                 # SearXNG on 127.0.0.1:8888, 512 MB cap
```

Then **Settings → Research agent → Web search**. Details: [Web search](../5-CONFIGURATION/research-agent.md#web-search).
For Claude Code: `claude mcp add --transport http brain http://<ui-host>:3000/mcp` ([MCP](../5-CONFIGURATION/mcp-integration.md)).

---

## Troubleshooting

- **Wrong Python version**: `uv sync --python 3.12`.
- **API can't reach the database**: `SURREAL_URL` must use `127.0.0.1`; check `docker compose ps` and
  `docker compose logs surrealdb`.
- **Sources stay queued**: the worker isn't running (`systemctl --user status brain-worker`).
- **UI shows "cannot connect to API"**: the API isn't up yet (first start runs migrations) or `brain-api` failed:
  `journalctl --user -u brain-api -n 50`.
- **Services stop when you log out**: run `sudo loginctl enable-linger $USER`.
- **Port 5055 is taken**: set `API_PORT` in `.env`, and build the UI with `INTERNAL_API_URL=http://127.0.0.1:<port>`
  (the proxy target is fixed at build time).

More in [Troubleshooting](../6-TROUBLESHOOTING/index.md).

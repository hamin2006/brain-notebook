# Development Setup

This is the one page for running Brain Notebook from a source checkout for development. To run it as a long-lived service, see [From source + systemd](../1-INSTALLATION/from-source.md). Other pages (README.dev.md, the contributing guide, the quick start) link here instead of repeating it.

The stack has four processes. Start them in this order, because each one depends on the one before it:

| # | Process | Port | Command |
|---|---|---|---|
| 1 | SurrealDB | 8000 | `make database` |
| 2 | API (FastAPI) | 5055 | `make api` |
| 3 | Background worker | — | `make worker-start` |
| 4 | Frontend (Next.js) | 3000 | `make frontend` |

The worker is not optional. Source processing, embeddings and podcasts are background jobs; without a worker they stay queued forever and nothing reports an error.

## Prerequisites

- **Python 3.11 or 3.12** (`pyproject.toml` requires `>=3.11,<3.13`; `.python-version` pins 3.12, which uv picks up)
- **[uv](https://docs.astral.sh/uv/)** for Python dependencies
- **Node.js 22** (20.9 is the minimum Next.js 16 accepts; the Docker image uses 22)
- **Docker** with the Compose plugin, for SurrealDB
- **ffmpeg** if you work on podcasts or audio/video sources (the Docker image installs it)

## 1. Clone and install

```bash
git clone https://github.com/hamin2006/brain-notebook.git
cd brain-notebook
git remote add upstream https://github.com/lfnovo/open-notebook.git   # optional: to merge upstream fixes

uv sync                          # Python deps, including the dev group (pytest, ruff, mypy)
cd frontend && npm install && cd ..
```

Upstream Brain Notebook is merged occasionally (`git fetch upstream && git merge upstream/main`). Code identifiers
keep upstream's names to keep that possible; expect conflicts in files the fork rewrote (chat routers, the source
graph, chat UI).

## 2. Create `.env`

```bash
cp .env.example .env
```

Then edit two values in `.env`:

```bash
# .env.example points at the Docker Compose hostname "surrealdb", which does not
# resolve from your host. The API and worker run on the host, so use localhost:
SURREAL_URL=ws://localhost:8000/rpc

# Required to store provider credentials. Any string works; there is no default.
OPEN_NOTEBOOK_ENCRYPTION_KEY=some-local-dev-secret
```

Leave `SURREAL_USER` / `SURREAL_PASSWORD` as they are (`root` / `root`). `make database` starts SurrealDB through `docker-compose.yml`, which reads the same `.env`, so the database and the API always use the same credentials.

`OPEN_NOTEBOOK_PASSWORD` is unset by default, which disables the API password. Set it if you want to test the login flow.

The API loads `.env` itself (`load_dotenv()` in `api/main.py`); `make api` and `make worker-start` also pass `--env-file .env`.

## 3. Start the stack

All at once, in one terminal:

```bash
make start-all    # SurrealDB, API, worker, then the frontend in the foreground
make status       # which of the four are running
make stop-all     # stops all four (also runs `docker compose down`)
```

Or one terminal per process, which makes logs easier to read:

```bash
make database       # terminal 1: SurrealDB in Docker (data in ./surreal_data)
make api            # terminal 2: API on 127.0.0.1:5055, auto-reload on
make worker-start   # terminal 3: surreal-commands worker
make frontend       # terminal 4: Next.js dev server on :3000
```

`make api` runs `run_api.py`, which reads `API_HOST` (default `127.0.0.1`), `API_PORT` (default `5055`) and `API_RELOAD` (default `true`). There is no `python -m api.main` entry point.

The frontend proxies `/api/*` to `INTERNAL_API_URL` (default `http://localhost:5055`, see `frontend/next.config.ts`), so it needs no `.env` of its own.

## 4. Check that it works

```bash
curl http://localhost:5055/health        # {"status":"healthy"}
open http://localhost:5055/docs          # Swagger UI for every endpoint
open http://localhost:3000               # the app
```

Database migrations run automatically when the API starts. The API log shows one of:

```
Current database version: N
Database is already at the latest version. No migrations needed.
```

or, on a fresh or outdated database:

```
Database migrations are pending. Running migrations...
Running migration N
Migrations completed successfully. Database is now at version N
```

To use AI features, set up models: `OPENROUTER_API_KEY=… python3 scripts/brain/provision_models.py`, or by hand under **Manage → Models** ([Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent)). Upload a PDF to exercise the whole ingestion pipeline (the worker log shows each stage), then ask in notebook chat; the research steps show which tools ran.

Optional services: SearXNG for web search (`scripts/brain/searxng`, see [Web search](../5-CONFIGURATION/research-agent.md#running-searxng)), and an MCP client pointed at `http://localhost:5055/mcp`.

## Before you open a PR

Run what CI runs. The list lives in [contributing.md](contributing.md#before-you-open-a-pr) so it is maintained in one place.

Optional: `uv run pre-commit install` installs git hooks (`.pre-commit-config.yaml`) that run ruff, ruff format and mypy on each commit.

## Docker-based workflows

| Command | What it does | Use it for |
|---|---|---|
| `docker compose build` | Builds `brain-notebook:local` from your checkout (the root compose file) | Checking the production image |

`make dev` / `make full` use upstream's example compose files; check they build from your checkout. The `docker-push*` / `docker-release` targets publish upstream's images and don't apply to this fork.

## Troubleshooting

**Sources stay "Queued", embeddings or podcasts never finish.** The worker isn't running. Start it with `make worker-start` and check its log.

**The API can't connect to SurrealDB.** Check that `SURREAL_URL` in `.env` uses `localhost`, not `surrealdb`, and that the container is up (`docker compose ps surrealdb`). The API retries the connection on startup, so it may log a few failures while SurrealDB starts.

**A port is already in use.** Another project may own 3000, 5055 or 8000. Run the frontend on another port with `PORT=3001 npm run dev` (inside `frontend/`), or the API with `API_PORT=5056 make api` (then set `INTERNAL_API_URL=http://localhost:5056` for the frontend).

**Import errors after pulling.** Run `uv sync` and `npm install` again; dependencies change often.

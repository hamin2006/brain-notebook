# Docker Compose Installation (Recommended)

This is the standard way to run Brain Notebook. It uses the [`docker-compose.yml`](../../docker-compose.yml) in the root of the repository, which **builds the app image from your checkout** and starts:

| Service | What it runs | Ports | Data folder |
|---|---|---|---|
| `surrealdb` | The database | `8000` (bound to `127.0.0.1` only) | `./surreal_data` |
| `open_notebook` | Web UI, REST API (incl. `/mcp`) and the background worker | `8502` (UI), `5055` (API) | `./notebook_data` |
| `searxng` (optional, profile `web`) | Self-hosted metasearch for the agent's web search | none (internal) | none |

The background worker runs inside the `open_notebook` container, so ingestion (page extraction, captions, analysis, embeddings, concept graph) works without extra services.

> **Don't swap in upstream images.** `lfnovo/open_notebook` / `ghcr.io/lfnovo/open-notebook` are upstream Open Notebook, without the research agent; the database migrations also differ.

## Prerequisites

- **Docker with Compose v2.** On macOS and Windows install [Docker Desktop](https://www.docker.com/products/docker-desktop/). On Linux install Docker Engine and the Compose plugin. Check with `docker compose version`.
- **4 GB of free RAM** or more.
- **An AI provider**: an API key from a cloud provider, or a local model server such as Ollama. You add it in the UI after installing.

---

## Step 1: Get the code

```bash
git clone https://github.com/hamin2006/brain-notebook.git
cd brain-notebook
```

The image is built from this folder, so keep the whole checkout (not just the compose file).

## Step 2: Set your encryption key

Open `docker-compose.yml` and find this line in the `open_notebook` service:

```yaml
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=change-me-to-a-secret-string
```

Replace `change-me-to-a-secret-string` with a long random secret that you generate yourself. Don't copy an example value from any guide. Either of these prints a suitable value:

```bash
openssl rand -hex 32                                   # macOS, Linux
```

```powershell
[guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")   # Windows PowerShell
```

Brain Notebook uses this key to encrypt the provider API keys it stores.

> **Keep this key.** If it changes later, the keys you saved can no longer be decrypted and you have to enter them again.

## Step 3: Decide who can reach it

The shipped file publishes ports `8502` (UI) and `5055` (API) on **all network interfaces**, and authentication is off until you set a password. If other people or devices can reach this machine (shared network, server, VPS), do one of these **before starting**:

- **Keep it on this machine only:** in `docker-compose.yml`, change the two port lines of the `open_notebook` service to `"127.0.0.1:8502:8502"` and `"127.0.0.1:5055:5055"`.
- **Require a password:** add `- OPEN_NOTEBOOK_PASSWORD=your-password` to the `environment:` block of the `open_notebook` service.

See [Access from another machine](#access-from-another-machine) if you do want to use it from other devices.

## Step 4: Build and start

```bash
docker compose up -d --build
```

The first build takes a few minutes (frontend build, Python dependencies). Check that both services are running:

```bash
docker compose ps
```

The API runs database migrations when it starts (`docker compose logs open_notebook | grep version` should end at *version 29*). After 20–30 seconds it should answer:

```bash
curl http://localhost:5055/health
# {"status":"healthy"}
```

## Step 5: Open the UI and set up the models

Open **http://localhost:8502**. Then, from the checkout folder:

```bash
OPENROUTER_API_KEY=sk-or-... python3 scripts/brain/provision_models.py
```

This connects OpenRouter and sets the recommended defaults (answer model, research model, embeddings). To use another provider or pick models yourself, see [Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent). Chat won't work until the default models are set.

---

## Changing settings

Every Brain Notebook setting is an environment variable on the **`open_notebook`** service. Add it to that service's `environment:` block and apply it with:

```bash
docker compose up -d
```

`up -d` recreates the container when its configuration changed. `docker compose restart` does **not** apply new settings.

For example, to require a password:

```yaml
  open_notebook:
    environment:
      # ...existing lines...
      - OPEN_NOTEBOOK_PASSWORD=choose-a-password
```

A few things to know:

- **`.env` is not loaded into the container.** The shipped compose file has no `env_file:`. A `.env` file next to `docker-compose.yml` only fills the `${...}` placeholders in the file (the shipped file uses it for `SURREAL_USER` and `SURREAL_PASSWORD`). Anything else you put in `.env` is ignored.
- **Database credentials** default to `root:root`, and the database port is only reachable from the same machine. To use other credentials, put `SURREAL_USER=...` and `SURREAL_PASSWORD=...` in a `.env` file before the first start; both services read them. See [`.env.example`](../../.env.example).
- **Optional extraction engines** (Docling, Crawl4AI) are commented out in the compose file. When enabled they are installed on the next start, which then takes several minutes. See the [Environment Reference](../5-CONFIGURATION/environment-reference.md).
- **Keep your changes in an override file (optional).** Docker Compose automatically merges a `docker-compose.override.yml` in the same folder. Putting your additions there leaves `docker-compose.yml` untouched, so `git pull` updates cleanly. The variants below use this file.

The full list of settings is in the [Environment Reference](../5-CONFIGURATION/environment-reference.md).

---

## Variants

### Web search (SearXNG)

The research agent can search the web through a self-hosted SearXNG (no API key, no per-search cost). Put a secret in a `.env` file next to `docker-compose.yml` and start the `web` profile:

```bash
echo "SEARXNG_SECRET=$(openssl rand -hex 32)" >> .env
docker compose --profile web up -d
```

The app already points at it (`SEARXNG_URL=http://searxng:8080`). Turn it on in **Settings → Research agent → Web search**; it's used only in notebooks whose answers may add general knowledge. See [Web search](../5-CONFIGURATION/research-agent.md#web-search). Later `docker compose` commands need `--profile web` to include it.

### Ollama in Docker (local models)

Create `docker-compose.override.yml` next to `docker-compose.yml`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ./ollama_models:/root/.ollama
    restart: always
```

Start it and download a chat model and an embedding model:

```bash
docker compose up -d
docker compose exec ollama ollama pull qwen3
docker compose exec ollama ollama pull nomic-embed-text
```

When you [connect a provider](../4-AI-PROVIDERS/index.md#connect-a-provider), pick **Ollama** and set **Base URL** to `http://ollama:11434`. The research agent's **Tools Model** must support tool calling (`qwen3` does), and slide captions need a vision model; see the notes in the [Local Quick Start](../0-START-HERE/quick-start-local.md). GPU setup, model choices and timeouts are in the [Ollama guide](../5-CONFIGURATION/ollama.md).

### Ollama installed on the host

Brain Notebook runs in a container, so `localhost` there is the container, not your computer. Use `host.docker.internal` instead.

1. Create `docker-compose.override.yml` so that name resolves on every platform (Docker Desktop already provides it; Docker Engine on Linux needs this line):

   ```yaml
   services:
     open_notebook:
       extra_hosts:
         - "host.docker.internal:host-gateway"
   ```

2. Make Ollama reachable from containers:

   - **macOS and Windows (Docker Desktop):** Docker Desktop forwards `host.docker.internal` to the host, so Ollama's default setup usually works as is. If the connection test fails, make Ollama listen on all interfaces: on macOS run `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, then quit and reopen the Ollama app (this setting is lost when you log out or reboot, so run it again after each login, or follow Ollama's FAQ for a permanent setup); on Windows add a user environment variable `OLLAMA_HOST` = `0.0.0.0:11434`, then quit and restart Ollama. See Ollama's [documentation](https://github.com/ollama/ollama/tree/main/docs) (FAQ, "How do I configure Ollama server?").
   - **Linux:** Ollama listens on `127.0.0.1` by default, which containers can't reach. For the systemd service, run `sudo systemctl edit ollama`, add these lines, save, then run `sudo systemctl restart ollama`:

     ```ini
     [Service]
     Environment="OLLAMA_HOST=0.0.0.0:11434"
     ```

     If you start Ollama by hand, use `OLLAMA_HOST=0.0.0.0:11434 ollama serve`.

   `OLLAMA_HOST=0.0.0.0` exposes Ollama's API, which has no authentication, on every network interface. Allow port 11434 only from this host and its Docker networks (for example with your firewall), never from untrusted networks.

3. Run `docker compose up -d`.
4. When you [connect a provider](../4-AI-PROVIDERS/index.md#connect-a-provider), pick **Ollama** and set **Base URL** to `http://host.docker.internal:11434`.

### Single container

The Dockerfile can also build an all-in-one image with the database inside (`--target single`). See [Single Container](single-container.md).

---

## Access from another machine

By default the browser loads the UI from port `8502` and then calls the API directly on port `5055` of the same host name. So for access from another machine, either:

- make **both** ports `8502` and `5055` reachable, or
- set `API_URL` to the address you open the UI with (for example `- API_URL=http://192.168.1.50:8502`). The browser then sends API calls through the UI server, and only port `8502` needs to be reachable.

**MCP clients** (Claude Code on another machine) connect to `http://<host>:8502/mcp`; add `- OPEN_NOTEBOOK_MCP_ALLOWED_HOSTS=<host>:*` to the `environment:` block, otherwise requests that arrive with another host name are refused. See [MCP](../5-CONFIGURATION/mcp-integration.md).

Authentication is off unless you set `OPEN_NOTEBOOK_PASSWORD`, so set it whenever the ports are reachable from other machines (see [Step 3](#step-3-decide-who-can-reach-it)). For HTTPS and domains, see [Reverse Proxy](../5-CONFIGURATION/reverse-proxy.md) and [Security](../5-CONFIGURATION/security.md).

---

## Common tasks

### View logs

```bash
docker compose logs -f open_notebook   # UI, API and worker
docker compose logs -f surrealdb       # database
```

### Stop and start

```bash
docker compose down    # stops and removes the containers; data folders stay
docker compose up -d
```

### Back up

Your data lives in the `surreal_data/` and `notebook_data/` folders. Stop the services and copy both:

```bash
docker compose down
tar czf brain-notebook-backup.tgz surreal_data notebook_data
docker compose up -d
```

On Linux the folders are owned by root (the database runs as root for the bind mount), so you may need `sudo tar ...`.

### Update

Back up first, then:

```bash
git pull
docker compose up -d --build
```

The API applies new database migrations when it starts. Migrations only move forward in normal use; to roll back, restore the backup you made before the update.

### Delete everything

`docker compose down -v` does **not** delete your data: the shipped compose file uses bind-mounted folders, not named volumes. To wipe the installation, stop it and delete the folders:

```bash
docker compose down
rm -rf surreal_data notebook_data   # permanent; use sudo on Linux
```

---

## Troubleshooting

**The UI loads but can't reach the API.** The API may still be starting; check `docker compose logs -f open_notebook`. If you open the UI from another machine, see [Access from another machine](#access-from-another-machine).

**Port already in use.** Change the host side of the mapping, for example `"8503:8502"`, run `docker compose up -d` and open `http://localhost:8503`.

**`Permission denied` or `Failed to create RocksDB directory` in the database logs (Linux).** The `surrealdb` service needs `user: root` to write to the bind-mounted folder. The shipped file has it; add it if your compose file is older, then run `docker compose up -d`.

**Sources stay queued.** The worker runs inside `open_notebook`; look for errors in `docker compose logs open_notebook`.

**Chat fails right after installing.** The default models aren't set. See step 4 of [Connect a provider](../4-AI-PROVIDERS/index.md#4-set-default-models).

More: [Quick Fixes](../6-TROUBLESHOOTING/quick-fixes.md) · [Connection Issues](../6-TROUBLESHOOTING/connection-issues.md).

---

## Other examples

The [`examples/`](../../examples/) folder has compose files from upstream Brain Notebook for other setups (Ollama, a fully local stack, a speech server). They reference upstream images: replace the `open_notebook` service's `image:` with `build: .` / `image: brain-notebook:local` as in the root `docker-compose.yml` before using one.

## Next steps

- [User Guide](../3-USER-GUIDE/index.md)
- [Security](../5-CONFIGURATION/security.md) and [Reverse Proxy](../5-CONFIGURATION/reverse-proxy.md) before exposing it to a network


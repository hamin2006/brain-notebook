# Single Container Installation

> **Not tested by this fork.** The Dockerfile's `single` target (inherited from upstream Open Notebook) bundles
> SurrealDB, the API, the background worker and the web UI in one container. Brain Notebook's tested routes are
> [Docker Compose](docker-compose.md) and [from source](from-source.md); prefer them.

It is mostly useful on hosting platforms that run exactly one container per app. There is no published image for
Brain Notebook; build it from a checkout:

```bash
git clone https://github.com/hamin2006/brain-notebook.git && cd brain-notebook
docker build --target single -t brain-notebook:single .
```

(Upstream's `lfnovo/open_notebook:v1-latest-single` is Brain Notebook without the research agent.)

## What the container needs

Whatever runs it (Docker on your machine or a hosting platform) must provide:

| Need | Value |
|---|---|
| **Port** | `8502` (web UI). Port `5055` (API) too, unless you set `API_URL` (below). |
| **Persistent storage** | Two paths: `/app/data` (uploads, app data) **and** `/mydata` (the database). Without `/mydata` on persistent storage the database is lost every time the container is recreated, including on every image update. |
| **`OPEN_NOTEBOOK_ENCRYPTION_KEY`** | Required. A long random secret; keep it, or saved API keys can't be decrypted. |
| **`SURREAL_URL`** | `ws://localhost:8000/rpc` (the database runs inside the same container). |
| **`SURREAL_USER`, `SURREAL_PASSWORD`** | Both `root` (see below). |
| **`OPEN_NOTEBOOK_PASSWORD`** | Required on anything reachable from a network. Authentication is off when it's unset. |
| **`API_URL`** | Set it to the public URL of the app (for example `https://notebook.example.com`) when only one port is reachable. The browser then sends API calls through the UI server instead of to port 5055. |

The embedded database always starts with user `root` and password `root`, so set `SURREAL_USER=root` and `SURREAL_PASSWORD=root`. Any other value breaks the connection. Don't publish port `8000`; nothing outside the container needs it.

## Run it locally with Docker

```yaml
# docker-compose.yml
services:
  open_notebook:
    image: brain-notebook:single   # built with --target single (above)
    ports:
      - "8502:8502"  # Web UI
      - "5055:5055"  # API
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=change-me-to-a-secret-string
      - SURREAL_URL=ws://localhost:8000/rpc
      - SURREAL_USER=root
      - SURREAL_PASSWORD=root
      - SURREAL_NAMESPACE=open_notebook
      - SURREAL_DATABASE=open_notebook
    volumes:
      - ./notebook_data:/app/data   # app data
      - ./surreal_data:/mydata      # database
    restart: always
```

Replace the encryption key with a long random secret you generate yourself (see [Set your encryption key](docker-compose.md#step-2-set-your-encryption-key)). If other devices can reach this machine, also add `- OPEN_NOTEBOOK_PASSWORD=...` or bind the ports to `127.0.0.1`. Then:

```bash
docker compose up -d
```

Open **http://localhost:8502** and set up the models: [Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent). Chat works once the default models are set.

Settings go in the `environment:` block and are applied with `docker compose up -d` (not `restart`). Logs: `docker compose logs -f open_notebook`.

## Hosting platforms

Push your built image to a registry your platform can pull from, then use the table above to fill in its form: the image, port `8502`, persistent storage for **both** `/app/data` and `/mydata`, and the environment variables. Platforms that can't give you persistent storage at both paths will lose data on redeploy; use a platform or VPS that runs Docker Compose instead.

After deploying, open the app's URL and set up the models: [Models for the research agent](../4-AI-PROVIDERS/index.md#models-for-the-research-agent).

### EasyPanel

Upstream's EasyPanel template in `examples/easypanel/` deploys upstream Open Notebook images; it would need adapting
to a Brain Notebook image you publish yourself.

## Moving to Docker Compose

1. **Get the data out of the old container.** If `/mydata` was mounted to a host folder, that folder holds the database. Older versions of this guide only mounted `/app/data`, so on those setups the database lives **inside the container**: copy it out before you remove the container. From the folder with the old `docker-compose.yml`:

   ```bash
   docker compose stop
   docker compose cp open_notebook:/mydata ./surreal_data
   docker compose cp open_notebook:/app/data ./notebook_data   # skip if /app/data was already a host folder
   ```

   On a hosting platform, use its volume or file export instead. Don't run `docker compose down` until the copy is done: removing the container deletes an unmounted database.
2. Set up [Docker Compose](docker-compose.md) in a new folder with the **same** `OPEN_NOTEBOOK_ENCRYPTION_KEY`.
3. Before the first start, move the copied `surreal_data/` (it must contain `mydatabase.db`) and `notebook_data/` into the new folder.

The single image's database uses `root:root`, which matches the compose default. The database path inside both setups is `/mydata/mydatabase.db`.

---


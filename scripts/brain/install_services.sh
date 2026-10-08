#!/usr/bin/env bash
# Install Brain Notebook as systemd user services (Linux), for this checkout:
#   brain-api       FastAPI on 127.0.0.1:5055 (runs DB migrations on start)
#   brain-worker    background jobs (ingestion, embeddings, analysis)
#   brain-frontend  the web UI (production build; proxies /api and /mcp to the API)
#
# Usage: scripts/brain/install_services.sh [--host 127.0.0.1] [--port 3000]
#   --host  address the UI listens on: 127.0.0.1 (this machine only), a Tailscale
#           or LAN IP to reach it from other devices, or 0.0.0.0 (all interfaces)
# Prerequisites: SurrealDB running, `uv sync` done, .env configured,
# scripts/brain/build_frontend.sh run once. See docs/1-INSTALLATION/from-source.md.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST=127.0.0.1
PORT=3000
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
NODE="$(command -v node)"
UNITS="$HOME/.config/systemd/user"
mkdir -p "$UNITS"

cat > "$UNITS/brain-api.service" <<UNIT
[Unit]
Description=Brain Notebook API
After=network-online.target

[Service]
WorkingDirectory=$REPO
Environment=API_RELOAD=false
ExecStart=$UV run --env-file .env run_api.py
Restart=on-failure
RestartSec=5
MemoryMax=1G

[Install]
WantedBy=default.target
UNIT

cat > "$UNITS/brain-worker.service" <<UNIT
[Unit]
Description=Brain Notebook background worker
After=brain-api.service

[Service]
WorkingDirectory=$REPO
# Two malloc arenas instead of one per thread: PDF parsing and rendering run in
# threads, and per-thread arenas kept the worker at its peak after ingestion.
Environment=MALLOC_ARENA_MAX=2
# Jobs are async tasks in one process, mostly waiting on model calls, so
# several at once cost little memory (a few hundred MB at 8).
ExecStart=$UV run --env-file .env python -m commands.worker --max-tasks 8
Restart=on-failure
RestartSec=5
MemoryMax=2560M

[Install]
WantedBy=default.target
UNIT

cat > "$UNITS/brain-frontend.service" <<UNIT
[Unit]
Description=Brain Notebook web UI
After=brain-api.service

[Service]
WorkingDirectory=$REPO/frontend/.next/standalone
Environment=HOSTNAME=$HOST
Environment=PORT=$PORT
# browsers call this server, which proxies /api to the API on 127.0.0.1:5055
Environment=API_URL=relative
ExecStart=$NODE server.js
Restart=on-failure
RestartSec=5
MemoryMax=512M

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now brain-api brain-worker brain-frontend
echo "installed; UI at http://$HOST:$PORT (API 127.0.0.1:5055)"
echo "keep services running after logout: sudo loginctl enable-linger $USER"

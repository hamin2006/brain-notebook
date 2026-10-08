#!/usr/bin/env bash
# Update an installed Brain Notebook (systemd services from install_services.sh):
# pull, sync dependencies, rebuild the frontend when it changed, restart.
# The API applies database migrations on startup.
#   scripts/brain/deploy_pc.sh            # current branch
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
export GIT_PAGER=cat PAGER=cat
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

branch=$(git rev-parse --abbrev-ref HEAD)
if [ -z "${DEPLOY_FROM:-}" ]; then
  before=$(git rev-parse --short HEAD)
  git fetch -q origin "$branch"
  git merge --ff-only -q "origin/$branch"
  # Continue with the version of this script just pulled: bash reads a script
  # as it runs, so the old copy would skip steps added since.
  exec env DEPLOY_FROM="$before" bash "$0" "$@"
fi
before="$DEPLOY_FROM"
after=$(git rev-parse --short HEAD)
echo "code ($branch): $before -> $after"

"$UV" sync --all-extras -q
if [ ! -f frontend/.next/standalone/server.js ] || ! git diff --quiet "$before" "$after" -- frontend/; then
  bash scripts/brain/build_frontend.sh >/dev/null
  echo "frontend rebuilt"
fi

# Units written by an older install_services.sh start the worker without its
# startup recovery (re-queue interrupted jobs, reprocess outdated sources).
unit="$HOME/.config/systemd/user/brain-worker.service"
if [ -f "$unit" ] && grep -q "surreal-commands-worker" "$unit"; then
  sed -i 's#surreal-commands-worker --import-modules commands#python -m commands.worker#' "$unit"
  systemctl --user daemon-reload
  echo "brain-worker.service now runs python -m commands.worker"
fi

# Units from before 2026-10-08: 2 worker slots, per-thread malloc arenas and
# memory caps summing to 6 GB without SurrealDB. Only the old defaults are
# replaced, so values changed by hand are kept.
units="$HOME/.config/systemd/user"
changed=0
if [ -f "$units/brain-worker.service" ] && grep -q -- "--max-tasks 2$" "$units/brain-worker.service"; then
  sed -i -e 's/--max-tasks 2$/--max-tasks 8/' -e 's/^MemoryMax=3G$/MemoryMax=2560M/' \
    -e 's/^\(ExecStart=.*commands.worker.*\)$/Environment=MALLOC_ARENA_MAX=2\n\1/' \
    "$units/brain-worker.service"
  changed=1
fi
if [ -f "$units/brain-api.service" ] && grep -q "^MemoryMax=2G$" "$units/brain-api.service"; then
  sed -i 's/^MemoryMax=2G$/MemoryMax=1G/' "$units/brain-api.service"
  changed=1
fi
if [ -f "$units/brain-frontend.service" ] && grep -q "^MemoryMax=1G$" "$units/brain-frontend.service"; then
  sed -i 's/^MemoryMax=1G$/MemoryMax=512M/' "$units/brain-frontend.service"
  changed=1
fi
if [ "$changed" = 1 ]; then
  systemctl --user daemon-reload
  echo "services updated: 8 worker slots, MALLOC_ARENA_MAX=2, caps api 1G / worker 2.5G / frontend 512M"
fi

# The API applies migrations on start: restart it first and wait, so the worker
# never runs jobs against the old schema. Jobs interrupted by the worker's
# restart are re-queued when it starts. /health is the one route outside the
# password check, and the API serves nothing until its migrations succeed.
systemctl --user restart brain-api
api_up=0
for _ in $(seq 1 300); do  # up to 10 minutes: a migration may backfill big tables
  if curl -fs -o /dev/null http://127.0.0.1:5055/health; then
    api_up=1
    echo "api up"
    break
  fi
  sleep 2
done
if [ "$api_up" != 1 ]; then
  echo "api did not come up; worker not restarted. Last API log lines:" >&2
  journalctl --user -u brain-api -n 30 --no-pager >&2 || true
  exit 1
fi
systemctl --user restart brain-worker brain-frontend
for unit in brain-api brain-worker brain-frontend; do
  echo "$unit: $(systemctl --user is-active "$unit")"
done
if ! command -v soffice >/dev/null 2>&1; then
  echo "note: LibreOffice is not installed, so PowerPoint/Word uploads are ingested as text only" \
    "(sudo apt install --no-install-recommends libreoffice-impress libreoffice-writer)"
fi

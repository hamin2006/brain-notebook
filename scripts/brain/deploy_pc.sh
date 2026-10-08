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

# The API applies migrations on start: restart it first and wait, so the worker
# never runs jobs against the old schema. Jobs interrupted by the worker's
# restart are re-queued when it starts. /health is the one route outside the
# password check, and the API serves nothing until its migrations succeed.
systemctl --user restart brain-api
api_up=0
for _ in $(seq 1 90); do
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

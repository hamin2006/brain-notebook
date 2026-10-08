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
before=$(git rev-parse --short HEAD)
git fetch -q origin "$branch"
git merge --ff-only -q "origin/$branch"
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

# Jobs interrupted by this restart are re-queued when the worker starts.
systemctl --user restart brain-api brain-worker brain-frontend
for _ in $(seq 1 60); do
  if curl -fs -o /dev/null http://127.0.0.1:5055/api/models; then
    echo "api up"
    break
  fi
  sleep 2
done
for unit in brain-api brain-worker brain-frontend; do
  echo "$unit: $(systemctl --user is-active "$unit")"
done

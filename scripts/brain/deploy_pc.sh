#!/usr/bin/env bash
# Deploy the agentic-rag branch on the PC: pull, sync dependencies, restart.
# The API applies database migrations on startup. Run on the PC:
#   bash ~/workplace/open-notebook/scripts/brain/deploy_pc.sh
set -euo pipefail

cd "$HOME/workplace/open-notebook"
export GIT_PAGER=cat PAGER=cat

before=$(git rev-parse --short HEAD)
git fetch -q origin agentic-rag
git merge --ff-only -q origin/agentic-rag
after=$(git rev-parse --short HEAD)
echo "code: $before -> $after"

"$HOME/.local/bin/uv" sync --all-extras -q
if ! git diff --quiet "$before" "$after" -- frontend/package.json frontend/package-lock.json; then
  (cd frontend && npm install --no-audit --no-fund --loglevel=error)
fi

systemctl --user daemon-reload
systemctl --user restart on-api on-worker
systemctl --user enable -q --now on-frontend
systemctl --user restart on-frontend

for _ in $(seq 1 60); do
  if curl -fs -o /dev/null http://127.0.0.1:5055/api/models; then
    echo "api up"
    break
  fi
  sleep 2
done
for unit in on-api on-worker on-frontend; do
  echo "$unit: $(systemctl --user is-active "$unit")"
done

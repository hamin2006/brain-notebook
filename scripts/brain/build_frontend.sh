#!/usr/bin/env bash
# Production build of the frontend (Next.js standalone output), run from anywhere.
# The standalone server needs the static assets and public/ copied next to it
# (the Dockerfile does the same).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO/frontend"
npm ci --no-audit --no-fund --loglevel=error
npm run build
rm -rf .next/standalone/.next/static .next/standalone/public
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public
echo "frontend built: $REPO/frontend/.next/standalone"

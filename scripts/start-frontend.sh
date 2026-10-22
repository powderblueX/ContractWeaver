#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root/frontend"
[[ -x node_modules/.bin/vite ]] || { echo 'Run bash scripts/setup.sh first.' >&2; exit 1; }
echo 'Starting frontend; Ctrl+C to stop. Start the backend separately.'
exec npm run dev -- --host "${CONTRACTWEAVER_FRONTEND_HOST:-127.0.0.1}" --port "${CONTRACTWEAVER_FRONTEND_PORT:-5173}" --strictPort

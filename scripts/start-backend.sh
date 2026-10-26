#!/usr/bin/env bash
# Start the API using project-local Python dependencies.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root/backend"
[[ -x .venv/bin/python && -f .env ]] || { echo 'Run bash scripts/setup.sh first.' >&2; exit 1; }
echo 'Starting backend; Ctrl+C to stop.'
exec .venv/bin/python -m uvicorn app.main:app --host "${CONTRACTWEAVER_BACKEND_HOST:-127.0.0.1}" --port "${CONTRACTWEAVER_BACKEND_PORT:-8000}"

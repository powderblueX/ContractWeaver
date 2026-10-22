#!/usr/bin/env bash
# Linux/macOS initialization; no system package installation or secret overwrite.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
component="${1:-all}"
case "$component" in all|backend|frontend) ;; *) echo 'Usage: bash scripts/setup.sh [all|backend|frontend]' >&2; exit 1 ;; esac
umask 077
if [[ ! -f "$project_root/backend/.env" ]]; then
    cp "$project_root/backend/.env.example" "$project_root/backend/.env"
    echo 'Created backend/.env. Edit LAW_LLM_API_KEY before using model features.'
fi
if [[ "$component" != frontend ]]; then
    python_command="${CONTRACTWEAVER_PYTHON:-python3}"
    "$python_command" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ is required")'
    if [[ ! -x "$project_root/backend/.venv/bin/python" ]]; then
        "$python_command" -m venv "$project_root/backend/.venv"
    fi
    "$project_root/backend/.venv/bin/python" -m pip install --no-cache-dir -r "$project_root/backend/requirements.txt"
fi
if [[ "$component" != backend ]]; then
    node -e 'if(Number(process.versions.node.split(".")[0])<20) { console.error("Node.js 20+ is required"); process.exit(1) }'
    (cd "$project_root/frontend" && npm ci --cache "$project_root/frontend/.npm-cache")
fi
echo 'Setup complete. Edit backend/.env, then run start-backend.sh and start-frontend.sh in separate terminals.'

#!/usr/bin/env bash
# One-command offline demo: builds the UI if needed, then serves UI + API on http://localhost:8000.
# Replays the stored 2018-2024 run from demo_data/runs_final (committed); no live calls. Usage: bash api/demo.sh   (PORT=9000 to change port)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d web/node_modules ] || (cd web && npm ci)
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/index.html -newer web/dist/index.html -print -quit)" ]; then
  (cd web && npm run build)
fi
export DASHBOARD_SOURCE="${DASHBOARD_SOURCE:-demo_data/runs_final}"
PY="python3"; [ -x .venv/bin/python3 ] && PY=".venv/bin/python3"
echo "Demo at http://localhost:${PORT:-8000}"
exec "$PY" -m uvicorn api.main:app --port "${PORT:-8000}"

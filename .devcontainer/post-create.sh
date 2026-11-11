#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Named volumes are created root-owned; hand them to the dev user.
sudo chown -R "$(id -u):$(id -g)" frontend/node_modules backend/.venv "$HOME/.cache/uv"

echo "==> Backend: uv sync"
(cd backend && uv sync --frozen)

echo "==> Frontend: npm ci"
(cd frontend && npm ci --no-audit --no-fund)

mkdir -p backend/data

cat <<'EOF'

Plantasaurus dev container ready.
  Tests:     cd backend && uv run pytest
  Typecheck: cd frontend && npm run typecheck
  Backend:   cd backend && uv run uvicorn app.asgi:app --reload --host 0.0.0.0
  Frontend:  cd frontend && npm run dev -- --host
EOF

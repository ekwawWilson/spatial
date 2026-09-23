#!/usr/bin/env bash
# Phase 0 demo: shows the stack is up, healthy and has its test data.
set -euo pipefail
cd "$(dirname "$0")/.."

API="http://localhost:${API_PORT:-8000}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "1. Services"
docker compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Health}}'

step "2. Health check ($API/api/health/)"
curl -fsS "$API/api/health/" | python3 -m json.tool

step "3. API documentation"
echo "OpenAPI schema: $API/api/schema/"
echo "Swagger UI:     $API/api/docs/"

step "4. Test fixtures"
python3 -m json.tool fixtures/generated/manifest.json
ls fixtures/generated

step "5. Web app"
echo "Open http://localhost:${WEB_PORT:-5173} - it should say 'All services OK'."

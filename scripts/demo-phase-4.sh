#!/usr/bin/env bash
# Phase 4 demo: basemaps via the API. Needs `make up seed`.
set -euo pipefail

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
T=$(curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' \
  -d "{\"email\":\"sma.admin@example.test\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
D=$(curl -fsS "$API/auth/me/" -H "Authorization: Bearer $T" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
H=(-H "Authorization: Bearer $T" -H "X-District-ID: $D" -H 'Content-Type: application/json')

step "1. Basemaps available (keys never shown)"
curl -fsS "$API/basemaps/" "${H[@]}" | python3 -c 'import sys,json; [print(f"  {b[\"name\"]:28} key: {\"set\" if b[\"has_key\"] else (\"missing\" if b[\"requires_key\"] else \"not needed\"):10} offline: {\"allowed\" if b[\"offline_cache_allowed\"] else \"not allowed\"}") for b in json.load(sys.stdin)]'

step "2. Add Google satellite without a key, then ask for its map config"
G=$(curl -fsS -X POST "$API/basemaps/presets/" "${H[@]}" -d '{"preset":"google_satellite"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -sS "$API/basemaps/$G/client-config/" "${H[@]}" -w '\n  HTTP %{http_code}\n'

step "3. OpenStreetMap config for the map"
O=$(curl -fsS "$API/basemaps/" "${H[@]}" | python3 -c 'import sys,json; print(next(b["id"] for b in json.load(sys.stdin) if b["preset"]=="osm"))')
curl -fsS "$API/basemaps/$O/client-config/" "${H[@]}" | python3 -m json.tool

#!/usr/bin/env bash
# Phase 3 demo: a project with layers and a feature, via the API.
# Needs the stack running and demo data seeded: `make up seed`.
set -euo pipefail

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
T=$(curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' \
  -d "{\"email\":\"sma.planner@example.test\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
D=$(curl -fsS "$API/auth/me/" -H "Authorization: Bearer $T" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
H=(-H "Authorization: Bearer $T" -H "X-District-ID: $D" -H 'Content-Type: application/json')
field() { python3 -c "import sys,json; print(json.load(sys.stdin)$1)"; }

step "1. Create a project (takes the default coordinate system)"
P=$(curl -fsS -X POST "$API/projects/" "${H[@]}" -d "{\"name\":\"Demo plan $(date +%s)\",\"community\":\"Kasoa\"}")
echo "$P" | python3 -m json.tool
PID=$(echo "$P" | field '["id"]')

step "2. Add a parcels layer with fields"
L=$(curl -fsS -X POST "$API/layers/" "${H[@]}" -d "{\"project\":$PID,\"name\":\"Parcels\",\"domain\":\"B\",\"geometry_type\":\"polygon\",\"schema\":[{\"name\":\"parcel_id\",\"type\":\"text\",\"required\":true},{\"name\":\"use\",\"type\":\"choice\",\"choices\":[\"residential\",\"commercial\"]}]}")
LID=$(echo "$L" | field '["id"]')
echo "  layer $LID, CRS $(echo "$L" | field '["crs_detail"]["code"]')"

step "3. Add a parcel in Ghana National Grid feet: stored exactly as sent"
curl -fsS -X POST "$API/layers/$LID/features/" "${H[@]}" -d '{"geometry":{"type":"Polygon","coordinates":[[[1190631.4519123456,337708.94461234567],[1190731.45,337708.94],[1190731.45,337808.94],[1190631.4519123456,337708.94461234567]]]},"properties":{"parcel_id":"P-001","use":"residential"}}' | python3 -m json.tool

step "4. A value that breaks the field rules is refused"
curl -sS -X POST "$API/layers/$LID/features/" "${H[@]}" -d '{"properties":{"parcel_id":"P-002","use":"industrial"}}' -w '\n  HTTP %{http_code}\n'

step "5. Layer extent (native feet and WGS 84)"
curl -fsS "$API/layers/$LID/extent/" "${H[@]}" | python3 -m json.tool

step "6. In the browser"
echo "Open http://localhost:${WEB_PORT:-5173}/projects/$PID"

#!/usr/bin/env bash
# Phase 2 demo: coordinate systems, defaults and transformations via the API.
# Needs the stack running and demo data seeded: `make up seed`.
set -euo pipefail

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
token() {
  curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])'
}
T=$(token sma.planner@example.test)
D=$(curl -fsS "$API/auth/me/" -H "Authorization: Bearer $T" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
H=(-H "Authorization: Bearer $T" -H "X-District-ID: $D" -H 'Content-Type: application/json')

step "1. Built-in coordinate systems"
curl -fsS "$API/crs/systems/" "${H[@]}" | python3 -c 'import sys,json; [print(f"  {s[\"code\"]:11} {s[\"name\"]:32} {s[\"units\"]}") for s in json.load(sys.stdin)]'

step "2. Default for new projects"
curl -fsS "$API/crs/defaults/" "${H[@]}" | python3 -c 'import sys,json; e=json.load(sys.stdin)["effective"]; print(f"  {e[\"crs\"][\"code\"]} (from the {e[\"source\"]} default)")'

step "3. GPS point (Accra) -> Ghana National Grid, with the accuracy of the datum shift"
curl -fsS -X POST "$API/crs/transform/" "${H[@]}" -d '{"from_crs":"EPSG:4326","to_crs":"EPSG:2136","points":[[-0.2,5.6]]}' | python3 -m json.tool

step "4. Round trip: back to WGS 84"
curl -fsS -X POST "$API/crs/transform/" "${H[@]}" -d '{"from_crs":"EPSG:2136","to_crs":"EPSG:4326","points":[[1190631.4519,337708.9446]]}' |
  python3 -c 'import sys,json; print("  ", json.load(sys.stdin)["points"][0])'

step "5. All published Accra -> WGS 84 transformations"
curl -fsS "$API/crs/operations/?from_crs=EPSG:2136&to_crs=EPSG:4326" "${H[@]}" |
  python3 -c 'import sys,json; d=json.load(sys.stdin); [print(f"  {\"*\" if o[\"name\"]==d[\"current\"][\"name\"] else \" \"} ±{o[\"accuracy_m\"]} m  {o[\"name\"]}") for o in d["candidates"]]'

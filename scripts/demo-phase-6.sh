#!/usr/bin/env bash
# Phase 6 demo: a planning area from a traverse, its checks and status. Needs `make up seed`.
set -euo pipefail

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
login() { curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])'; }
T=$(login sma.planner@example.test); A=$(login sma.admin@example.test)
D=$(curl -fsS "$API/auth/me/" -H "Authorization: Bearer $T" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
H=(-H "Authorization: Bearer $T" -H "X-District-ID: $D" -H 'Content-Type: application/json')
HA=(-H "Authorization: Bearer $A" -H "X-District-ID: $D" -H 'Content-Type: application/json')
P=$(curl -fsS -X POST "$API/projects/" "${H[@]}" -d "{\"name\":\"Boundary demo $(date +%s)\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

step "1. Traverse (500 ft square, last leg booked 0.10 ft long), Bowditch-adjusted"
TR=$(curl -fsS -X POST "$API/geometry/traverse/" "${H[@]}" -d '{"start":[1190600,337700],"legs":[{"bearing":"N 0 E","distance":500},{"bearing":"90","distance":500},{"bearing":"S 0 E","distance":500},{"bearing":"270 00 00","distance":500.10}],"adjust":true}')
echo "$TR" | python3 -c 'import sys,json; r=json.load(sys.stdin); print(f"  misclosure {r[\"misclosure\"]:.3f} ft, 1 in {r[\"accuracy_ratio\"]:,.0f}, adjusted: {r[\"adjusted\"]}")'

step "2. Use it as the planning area; the report"
POLY=$(echo "$TR" | python3 -c 'import sys,json; print(json.dumps(json.load(sys.stdin)["polygon"]))')
curl -fsS -X PUT "$API/projects/$P/boundary/" "${H[@]}" -d "{\"geometry\":$POLY,\"method\":\"traverse\"}" | python3 -m json.tool

step "3. Planner marks it agreed; approving needs a district administrator"
curl -fsS -X POST "$API/projects/$P/boundary-status/" "${H[@]}" -d '{"status":"agreed"}' >/dev/null && echo "  agreed"
curl -sS -X POST "$API/projects/$P/boundary-status/" "${H[@]}" -d '{"status":"approved"}' -o /dev/null -w '  planner approving: HTTP %{http_code}\n'
curl -fsS -X POST "$API/projects/$P/boundary-status/" "${HA[@]}" -d '{"status":"approved"}' | python3 -c 'import sys,json; print("  admin approving:", json.load(sys.stdin)["status"])'

#!/usr/bin/env bash
# Phase 7 demo: a project's readiness checklist, its measures and score. Needs `make up seed`.
set -euo pipefail

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
login() { curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])'; }
T=$(login sma.planner@example.test)
D=$(curl -fsS "$API/auth/me/" -H "Authorization: Bearer $T" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
H=(-H "Authorization: Bearer $T" -H "X-District-ID: $D" -H 'Content-Type: application/json')
P=$(curl -fsS -X POST "$API/projects/" "${H[@]}" -d "{\"name\":\"Readiness demo $(date +%s)\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
OUT=$(mktemp); trap 'rm -f "$OUT"' EXIT
summary='import sys,json; d=json.load(sys.stdin); print(f"  score {d[\"score\"]}% ({d[\"complete\"]}/{d[\"total\"]}); blockers: {len(d[\"blockers\"])}")'

step "1. A new project gets the checklist"
curl -fsS "$API/projects/$P/checklist/" "${H[@]}" | python3 -c "$summary"

step "2. Planning area (1000 ft square) and a buildings layer covering its west half"
curl -fsS -X PUT "$API/projects/$P/boundary/" "${H[@]}" -d '{"geometry":{"type":"Polygon","coordinates":[[[1190000,337000],[1191000,337000],[1191000,338000],[1190000,338000],[1190000,337000]]]},"method":"coordinates"}' >/dev/null
L=$(curl -fsS -X POST "$API/layers/" "${H[@]}" -d "{\"project\":$P,\"name\":\"Buildings and land use\",\"domain\":\"C\",\"geometry_type\":\"polygon\",\"schema\":[{\"name\":\"use\",\"type\":\"text\"}]}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -fsS -X POST "$API/layers/$L/features/" "${H[@]}" -d '{"geometry":{"type":"Polygon","coordinates":[[[1190000,337000],[1190500,337000],[1190500,338000],[1190000,338000],[1190000,337000]]]},"properties":{"use":"residential"}}' >/dev/null
curl -fsS "$API/projects/$P/checklist/" "${H[@]}" | python3 -c '
import sys,json
item = next(i for i in json.load(sys.stdin)["items"] if i["key"] == "buildings")
m = item["metrics"]
print(f"  buildings: {m[\"feature_count\"]} features, coverage {m[\"coverage\"]:.0f}%, attributes {m[\"attributes\"]:.0f}%")
for c in item["checks"]: print("   ", "ok " if c["ok"] else "NO ", c["label"] if c["ok"] else c["problem"])
print("ITEM", item["id"])' | tee "$OUT"
I=$(grep ^ITEM "$OUT" | cut -d' ' -f2)

step "3. Marking it ready is refused until the rules are met"
curl -sS -X PATCH "$API/checklist-items/$I/" "${H[@]}" -d '{"status":"ready"}' -w '\n  HTTP %{http_code}\n'

step "4. The CSV export"
curl -fsS "$API/projects/$P/checklist/export/?format=csv" -H "Authorization: Bearer $T" -H "X-District-ID: $D" | head -5

#!/usr/bin/env bash
# Phase 5 demo: import a shapefile and export it again, via the API. Needs `make up seed`.
set -euo pipefail
cd "$(dirname "$0")/.."

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
T=$(curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' \
  -d "{\"email\":\"sma.planner@example.test\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
D=$(curl -fsS "$API/auth/me/" -H "Authorization: Bearer $T" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
AUTH=(-H "Authorization: Bearer $T" -H "X-District-ID: $D")
P=$(curl -fsS -X POST "$API/projects/" "${AUTH[@]}" -H 'Content-Type: application/json' -d "{\"name\":\"Import demo $(date +%s)\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

step "1. Upload and inspect fixtures/generated/shp/buildings.zip"
JOB=$(curl -fsS -X POST "$API/transfer/jobs/imports/" "${AUTH[@]}" -F "project=$P" -F "file=@fixtures/generated/shp/buildings.zip")
echo "$JOB" | python3 -c 'import sys,json; l=json.load(sys.stdin)["inspection"]["layers"][0]; print(f"  layer {l[\"name\"]}: {l[\"feature_count\"]} features, CRS EPSG:{l[\"crs\"][\"epsg\"]} ({l[\"crs\"][\"confidence\"]}% match), fields {[f[\"name\"] for f in l[\"fields\"]]}")'
J=$(echo "$JOB" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

step "2. Run the import (new layer, full field names)"
curl -fsS -X POST "$API/transfer/jobs/$J/run/" "${AUTH[@]}" -H 'Content-Type: application/json' -d '{"layers":[{"source":"buildings","crs":"EPSG:2136","new_layer":{"name":"Buildings","domain":"C","geometry_type":"polygon"},"fields":[{"source":"property_i","target":"property_id","type":"text"},{"source":"use","target":"use","type":"text"},{"source":"floors","target":"floors","type":"integer"},{"source":"condition","target":"condition","type":"text"}]}]}' >/dev/null
sleep 3
curl -fsS "$API/transfer/jobs/$J/" "${AUTH[@]}" | python3 -c 'import sys,json; j=json.load(sys.stdin); print("  status:", j["status"], j["error"]); [print("  ", r["target_name"], r["imported"], "imported,", r["skipped"], "skipped") for r in j["report"].get("layers", [])]'
L=$(curl -fsS "$API/transfer/jobs/$J/" "${AUTH[@]}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["report"]["layers"][0]["target_layer"])')

step "3. Export it as a shapefile and list the zip"
E=$(curl -fsS -X POST "$API/transfer/jobs/exports/" "${AUTH[@]}" -H 'Content-Type: application/json' -d "{\"project\":$P,\"layer_ids\":[$L],\"format\":\"shp\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
sleep 3
curl -fsS "$API/transfer/jobs/$E/download/" "${AUTH[@]}" -o /tmp/spatial-demo-export.zip
python3 -m zipfile -l /tmp/spatial-demo-export.zip

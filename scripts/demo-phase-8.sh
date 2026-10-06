#!/usr/bin/env bash
# Phase 8 demo: save a project as .spp, look at the file, open it again. Needs `make up seed`.
set -euo pipefail

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
OUT=$(mktemp -d); trap 'rm -rf "$OUT"' EXIT
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
T=$(curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' -d "{\"email\":\"sma.planner@example.test\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
D=$(curl -fsS "$API/auth/me/" -H "Authorization: Bearer $T" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
H=(-H "Authorization: Bearer $T" -H "X-District-ID: $D")
J=("${H[@]}" -H 'Content-Type: application/json')

step "1. A project with a layer and a feature"
P=$(curl -fsS -X POST "$API/projects/" "${J[@]}" -d "{\"name\":\"File demo $(date +%s)\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
L=$(curl -fsS -X POST "$API/layers/" "${J[@]}" -d "{\"project\":$P,\"name\":\"Parcels\",\"domain\":\"B\",\"geometry_type\":\"polygon\",\"schema\":[{\"name\":\"pid\",\"type\":\"text\"}]}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -fsS -X POST "$API/layers/$L/features/" "${J[@]}" -d '{"geometry":{"type":"Polygon","coordinates":[[[1190600.125,337700.5],[1190800,337700],[1190800,337900],[1190600,337900],[1190600.125,337700.5]]]},"properties":{"pid":"P-1"}}' >/dev/null
echo "  project $P"

step "2. Save as .spp"
curl -fsS -X POST "$API/projects/$P/spp/" "${H[@]}" -o "$OUT/demo.spp"
echo "  $(stat -c %s "$OUT/demo.spp") bytes; first bytes: $(head -c 8 "$OUT/demo.spp" | od -An -c | tr -s ' ')"
python3 -c 'import sys,zipfile; print("  opens as a zip:", zipfile.is_zipfile(sys.argv[1])); print("  contains the text Parcels:", b"Parcels" in open(sys.argv[1],"rb").read())' "$OUT/demo.spp"

step "3. Open it: a new project, same coordinates"
curl -fsS -X POST "$API/spp/open/" "${H[@]}" -F "file=@$OUT/demo.spp" | python3 -m json.tool

step "4. A copy with one byte changed is refused"
python3 -c 'import sys; d=bytearray(open(sys.argv[1],"rb").read()); d[len(d)//2]^=1; open(sys.argv[2],"wb").write(d)' "$OUT/demo.spp" "$OUT/changed.spp"
curl -sS -X POST "$API/spp/open/" "${H[@]}" -F "file=@$OUT/changed.spp" -w '\n  HTTP %{http_code}\n'

step "5. Keys on this server (ids and fingerprints only)"
docker compose exec -T backend python manage.py spp_key list

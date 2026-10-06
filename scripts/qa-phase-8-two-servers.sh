#!/usr/bin/env bash
# Phase 8 gate: a .spp file saved on one server opens on another server that
# holds the same organisation key, and is refused by one that doesn't.
#
# Needs the main stack running and seeded (`make up seed`). Starts a second,
# separate stack (its own database and media) on other ports, and removes it
# at the end.
set -euo pipefail
cd "$(dirname "$0")/.."

PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
A="http://localhost:${API_PORT:-8000}/api"
B_PORT="${B_API_PORT:-8100}"
B="http://localhost:${B_PORT}/api"
WORK=$(mktemp -d)
OVERRIDE="$WORK/other-key.yml"
second() { DB_HOST_PORT="${B_DB_PORT:-5533}" API_PORT="$B_PORT" docker compose -p spatial-b "$@"; }
cleanup() { second down -v --remove-orphans >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
fail() { echo "FAILED: $1" >&2; exit 1; }

login() { curl -fsS -X POST "$1/auth/login/" -H 'Content-Type: application/json' -d "{\"email\":\"sma.planner@example.test\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])'; }
district() { curl -fsS "$1/auth/me/" -H "Authorization: Bearer $2" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])'; }
# The features of a project's "Pegs" layer, exact coordinates, without server-specific ids.
pegs() {
  local layer
  layer=$(curl -fsS "$1/layers/?project=$4" -H "Authorization: Bearer $2" -H "X-District-ID: $3" | python3 -c 'import sys,json; print(next(l["id"] for l in json.load(sys.stdin) if l["name"]=="Pegs"))')
  curl -fsS "$1/layers/$layer/features/?geometry=native" -H "Authorization: Bearer $2" -H "X-District-ID: $3" | python3 -c '
import sys, json
rows = [(f["properties"], f["geometry"], f["meta"]["version"]) for f in json.load(sys.stdin)["features"]]
print(json.dumps(sorted(rows, key=lambda r: r[0]["pid"]), sort_keys=True))'
}

step "1. Server A: a project with exact coordinates, saved as .spp"
TA=$(login "$A"); DA=$(district "$A" "$TA")
HA=(-H "Authorization: Bearer $TA" -H "X-District-ID: $DA")
NAME="Two servers $(date +%s)"
P=$(curl -fsS -X POST "$A/projects/" "${HA[@]}" -H 'Content-Type: application/json' -d "{\"name\":\"$NAME\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
L=$(curl -fsS -X POST "$A/layers/" "${HA[@]}" -H 'Content-Type: application/json' -d "{\"project\":$P,\"name\":\"Pegs\",\"geometry_type\":\"point\",\"schema\":[{\"name\":\"pid\",\"type\":\"text\"}]}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
for row in "A 1190600.123456789 337700.987654321" "B 1190811.000000001 337955.5" "C 1190702.25 337803.0625"; do
  set -- $row
  curl -fsS -X POST "$A/layers/$L/features/" "${HA[@]}" -H 'Content-Type: application/json' -d "{\"geometry\":{\"type\":\"Point\",\"coordinates\":[$2,$3]},\"properties\":{\"pid\":\"$1\"}}" >/dev/null
done
curl -fsS -X POST "$A/projects/$P/spp/" "${HA[@]}" -o "$WORK/project.spp"
echo "  saved $(stat -c %s "$WORK/project.spp") bytes"
python3 - "$WORK/project.spp" <<'PY'
import sys, zipfile
data = open(sys.argv[1], "rb").read()
assert not zipfile.is_zipfile(sys.argv[1]), "the file opens as a zip"
assert b"SQLite format 3" not in data and b"Pegs" not in data, "readable content in the file"
print("  not a zip, not a GeoPackage, no readable names")
PY
BEFORE=$(pegs "$A" "$TA" "$DA" "$P")

step "2. Server B: a separate stack with the same organisation key"
second up -d --wait db redis backend
second exec -T backend python manage.py seed_demo >/dev/null
TB=$(login "$B"); DB=$(district "$B" "$TB")
HB=(-H "Authorization: Bearer $TB" -H "X-District-ID: $DB")
CODE=$(curl -sS -o "$WORK/opened.json" -w '%{http_code}' -X POST "$B/spp/open/" "${HB[@]}" -F "file=@$WORK/project.spp")
[ "$CODE" = 201 ] || { cat "$WORK/opened.json"; fail "server B answered HTTP $CODE"; }
PB=$(python3 -c 'import sys,json; r=json.load(open(sys.argv[1])); print(r["project"]); print(f"  opened as project {r[\"project\"]}: {r[\"layers\"]} layer(s), {r[\"features\"]} features, {r[\"new_feature_ids\"]} new ids", file=sys.stderr)' "$WORK/opened.json")
AFTER=$(pegs "$B" "$TB" "$DB" "$PB")
[ "$BEFORE" = "$AFTER" ] || { echo "A: $BEFORE"; echo "B: $AFTER"; fail "coordinates or attributes differ between the servers"; }
echo "  coordinates and attributes are identical on both servers"

step "3. Server B with a different key refuses the file and says why"
cat > "$OVERRIDE" <<YML
services:
  backend:
    environment:
      SPP_ORG_KEYS: "another-assembly:$(openssl rand -base64 32)"
YML
second -f docker-compose.yml -f "$OVERRIDE" up -d --wait backend
TB=$(login "$B")
CODE=$(curl -sS -o "$WORK/refused.json" -w '%{http_code}' -X POST "$B/spp/open/" -H "Authorization: Bearer $TB" -H "X-District-ID: $DB" -F "file=@$WORK/project.spp")
echo "  HTTP $CODE: $(cat "$WORK/refused.json")"
[ "$CODE" = 400 ] || fail "a server without the key answered HTTP $CODE"
grep -q "which this server doesn't have" "$WORK/refused.json" || fail "the refusal doesn't explain the missing key"

step "4. One changed byte is refused (server A)"
python3 - "$WORK/project.spp" "$WORK/changed.spp" <<'PY'
import sys
data = bytearray(open(sys.argv[1], "rb").read())
data[len(data) // 2] ^= 1
open(sys.argv[2], "wb").write(data)
PY
CODE=$(curl -sS -o "$WORK/changed.json" -w '%{http_code}' -X POST "$A/spp/open/" "${HA[@]}" -F "file=@$WORK/changed.spp")
echo "  HTTP $CODE: $(cat "$WORK/changed.json")"
[ "$CODE" = 400 ] || fail "a changed file answered HTTP $CODE"

printf '\n\033[1mPhase 8 two-server gate: passed\033[0m\n'

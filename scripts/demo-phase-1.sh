#!/usr/bin/env bash
# Phase 1 demo: sign-in, district isolation, roles and the audit log, via the API.
# Needs the stack running and demo data seeded: `make up seed`.
set -euo pipefail
cd "$(dirname "$0")/.."

API="http://localhost:${API_PORT:-8000}/api"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
json() { python3 -m json.tool; }

token() {
  curl -fsS -X POST "$API/auth/login/" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}" |
    python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])'
}
district_id() {
  curl -fsS "$API/auth/me/" -H "Authorization: Bearer $1" |
    python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])'
}

step "1. Sign in as the Sample Municipal Assembly administrator"
SMA=$(token sma.admin@example.test)
SMA_ID=$(district_id "$SMA")
curl -fsS "$API/auth/me/" -H "Authorization: Bearer $SMA" | json

step "2. Members of their district"
curl -fsS "$API/memberships/" -H "Authorization: Bearer $SMA" -H "X-District-ID: $SMA_ID" |
  python3 -c 'import sys,json; [print(f"  {m[\"user\"][\"email\"]:28} {m[\"role\"]}") for m in json.load(sys.stdin)["results"]]'

step "3. The other district's admin asks for SMA's members: refused"
ODA=$(token oda.admin@example.test)
curl -sS -o /dev/stdout -w '\n  HTTP %{http_code}\n' "$API/memberships/" -H "Authorization: Bearer $ODA" -H "X-District-ID: $SMA_ID"

step "4. A viewer asks for the member list: refused by role"
VIEWER=$(token sma.viewer@example.test)
curl -sS -o /dev/stdout -w '\n  HTTP %{http_code}\n' "$API/memberships/" -H "Authorization: Bearer $VIEWER" -H "X-District-ID: $SMA_ID"

step "5. Latest audit entries for SMA"
curl -fsS "$API/audit/?page=1" -H "Authorization: Bearer $SMA" -H "X-District-ID: $SMA_ID" |
  python3 -c 'import sys,json; [print(f"  {e[\"occurred_at\"][:19]}  {e[\"action\"]:6} {e[\"table_name\"]}#{e[\"row_id\"]}  by {e[\"user_email\"] or \"system\"}") for e in json.load(sys.stdin)["results"][:8]]'

step "6. In the browser"
echo "Open http://localhost:${WEB_PORT:-5173} and sign in as any demo account (password: $PASSWORD):"
echo "  admin@example.test (system admin), sma.admin@, sma.planner@, sma.field@, sma.viewer@, oda.admin@"

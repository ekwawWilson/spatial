#!/usr/bin/env bash
# Phase 13: the production configuration starts and behaves. Expects the
# stack started with docker-compose.prod.yml and a .env made by
# scripts/make-production-env.sh.
# For a new, empty stack only: step 4 adds the demo districts and accounts
# (with a password made up here, shown nowhere).
set -euo pipefail
cd "$(dirname "$0")/.."

SITE="http://localhost:${WEB_PORT:-80}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
fail() { echo "FAILED: $1" >&2; exit 1; }

step "1. Django's own deployment checks"
$COMPOSE exec -T backend python manage.py check --deploy --fail-level ERROR

step "2. The web app is served, with security headers"
HEADERS=$(curl -fsS -D - -o /dev/null "$SITE/")
echo "$HEADERS" | grep -i "x-content-type-options: nosniff" >/dev/null || fail "no nosniff header"
echo "$HEADERS" | grep -i "x-frame-options: deny" >/dev/null || fail "no frame-options header"
# Map tile servers (OpenStreetMap) refuse requests that don't say which site they're from.
echo "$HEADERS" | grep -i "referrer-policy: strict-origin-when-cross-origin" >/dev/null || fail "the referrer policy would get map tiles blocked"
curl -fsS "$SITE/" | grep -q '<div id="root"' || fail "the page isn't the web app"
curl -fsS "$SITE/projects/5/checklist" | grep -q '<div id="root"' || fail "deep links don't reach the web app"
echo "  web app served; nosniff and frame-options present; deep links work"

step "3. The API answers through the proxy, and debug is off"
curl -fsS "$SITE/api/health/" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["ok"], d; print("  health ok")'
CODE=$(curl -s -o "$WORK/404" -w '%{http_code}' "$SITE/api/no-such-thing/")
[ "$CODE" = 404 ] || fail "unknown path answered $CODE"
grep -qi "traceback\|DEBUG = True" "$WORK/404" && fail "a debug page is shown" || echo "  no debug pages"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$SITE/api/projects/")
[ "$CODE" = 401 ] || fail "an anonymous request for data answered $CODE"
echo "  data needs a sign-in (401 without one)"

step "4. Sign in and use it"
PASSWORD="Check-$(head -c 18 /dev/urandom | base64 | tr -d '/+=')-9a"
$COMPOSE exec -T backend python manage.py seed_demo --force --password "$PASSWORD" >/dev/null
TOKEN=$(curl -fsS -X POST "$SITE/api/auth/login/" -H 'Content-Type: application/json' -d "{\"email\":\"sma.planner@example.test\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
DISTRICT=$(curl -fsS "$SITE/api/auth/me/" -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
curl -fsS -X POST "$SITE/api/projects/" -H "Authorization: Bearer $TOKEN" -H "X-District-ID: $DISTRICT" -H 'Content-Type: application/json' -d '{"name":"Production check"}' | python3 -c 'import sys,json; print("  created project", json.load(sys.stdin)["id"])'

step "5. Sign-in attempts are rate limited"
LAST=200
for _ in $(seq 1 14); do
  LAST=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$SITE/api/auth/login/" -H 'Content-Type: application/json' -d '{"email":"nobody@example.test","password":"wrong"}')
done
[ "$LAST" = 429 ] || fail "the 14th wrong sign-in in a row answered $LAST, not 429"
echo "  blocked after repeated wrong sign-ins (HTTP 429)"

step "6. The admin's static files are served"
curl -fsS -o /dev/null "$SITE/static/admin/css/base.css" || fail "admin static files are missing"
echo "  ok"

printf '\n\033[1mPhase 13 production check: passed\033[0m\n'

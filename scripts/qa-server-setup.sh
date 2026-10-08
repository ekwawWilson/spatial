#!/usr/bin/env bash
# Checks an installation made by scripts/server-setup.sh: only Caddy is
# reachable, HTTP goes to HTTPS, and the first administrator can sign in.
# The CI test runs it against "localhost"; on a real server, give the address.
#
#   scripts/qa-server-setup.sh [site-address]
set -euo pipefail
cd "$(dirname "$0")/.."

SITE="${1:-$(grep '^SITE_HOST=' .env | cut -d= -f2-)}"
INSECURE=""; [ "$SITE" = localhost ] && INSECURE="-k"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
fail() { echo "FAILED: $1" >&2; exit 1; }

step "1. Only ports 80 and 443 are open to the outside"
PUBLISHED=$(docker compose ps --format json | python3 -c '
import json, sys
ports = set()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    rows = json.loads(line)
    for row in rows if isinstance(rows, list) else [rows]:
        ports |= {(row["Service"], p["PublishedPort"]) for p in row.get("Publishers") or [] if p["PublishedPort"]}
print(" ".join(f"{service}:{port}" for service, port in sorted(ports)))
')
echo "  published: $PUBLISHED"
[ "$PUBLISHED" = "caddy:80 caddy:443" ] || fail "expected only Caddy, on 80 and 443"

step "2. HTTP goes to HTTPS; HTTPS has the security headers"
LOCATION=$(curl -s -o /dev/null -w '%{redirect_url}' "http://$SITE/")
case "$LOCATION" in https://*) echo "  http -> $LOCATION" ;; *) fail "http answered without sending to https ($LOCATION)" ;; esac
HEADERS=$(curl -fsS $INSECURE -D - -o /dev/null "https://$SITE/api/health/")
echo "$HEADERS" | grep -qi "strict-transport-security" || fail "no HSTS header"
echo "$HEADERS" | grep -qi "x-content-type-options: nosniff" || fail "no nosniff header"
echo "  HSTS and nosniff present"

step "3. The first administrator signs in over HTTPS"
EMAIL="first.admin@example.test"
PASSWORD="Check-$(head -c 18 /dev/urandom | base64 | tr -d '/+=')-7b"
docker compose exec -T -e DJANGO_SUPERUSER_PASSWORD="$PASSWORD" backend \
  python manage.py createsuperuser --noinput --email "$EMAIL" >/dev/null
TOKEN=$(curl -fsS $INSECURE -X POST "https://$SITE/api/auth/login/" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
curl -fsS $INSECURE "https://$SITE/api/auth/me/" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["is_system_admin"], d; print("  signed in as", d["email"], "(system administrator)")'

step "4. The web app is served"
curl -fsS $INSECURE "https://$SITE/" | grep -q '<div id="root"' || fail "the page isn't the web app"
echo "  ok"

printf '\n\033[1mServer set-up check: passed\033[0m\n'

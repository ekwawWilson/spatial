#!/usr/bin/env bash
# Phase 13 gate: a backup can be restored. Backs up the running stack,
# restores it into a second, empty stack, and checks the two hold the same
# data: every feature (geometry, attributes, version), the audit log, users,
# checklists, relationships and every uploaded file.
#
# Needs the main stack running with some data in it (`make up seed`).
set -euo pipefail
cd "$(dirname "$0")/.."

WORK=$(mktemp -d)
B_PORT="${B_API_PORT:-8200}"
export_b() { export DB_HOST_PORT="${B_DB_PORT:-5633}" API_PORT="$B_PORT"; }
B_COMPOSE="docker compose -p spatial-restore"
cleanup() { (export_b; $B_COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true); rm -rf "$WORK"; }
trap cleanup EXIT
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
fail() { echo "FAILED: $1" >&2; exit 1; }

FINGERPRINT_SQL="SELECT concat_ws('|',
  (SELECT count(*) FROM projects_feature),
  (SELECT md5(coalesce(string_agg(md5(coalesce(encode(ST_AsEWKB(geom_native), 'hex'), '') || properties::text || version::text || uuid::text), '' ORDER BY id), '')) FROM projects_feature),
  (SELECT count(*) FROM core_auditlog),
  (SELECT count(*) FROM core_user),
  (SELECT count(*) FROM projects_planproject),
  (SELECT count(*) FROM readiness_item),
  (SELECT count(*) FROM relations_relationship),
  (SELECT count(*) FROM imagery_imagery))"
fingerprint() {  # $@: the compose command
  local db files
  db=$("$@" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"$FINGERPRINT_SQL\"")
  files=$("$@" exec -T backend sh -c 'cd /media && find . -type f -exec sha256sum {} + | sort -k2 | sha256sum | cut -d" " -f1; find . -type f | wc -l' | tr '\n' ' ')
  echo "db=$db files=$files"
}

step "1. Let background work finish, then back up the running stack"
sleep 25
scripts/backup.sh "$WORK/backups"
BACKUP=$(find "$WORK/backups" -mindepth 1 -maxdepth 1 -type d | head -1)
BEFORE=$(fingerprint docker compose)
echo "  original: $BEFORE"
case "$BEFORE" in db=0\|*) fail "the running stack has no features: nothing to prove" ;; esac

step "2. A second, empty stack"
(export_b; $B_COMPOSE up -d --wait db redis backend)
EMPTY=$( (export_b; fingerprint $B_COMPOSE) )
echo "  empty:    $EMPTY"
[ "$EMPTY" != "$BEFORE" ] || fail "the second stack isn't empty"

step "3. Restore the backup into it"
(export_b; COMPOSE="$B_COMPOSE" SERVICES="db redis backend" scripts/restore.sh "$BACKUP" --yes)

step "4. Compare"
AFTER=$( (export_b; fingerprint $B_COMPOSE) )
echo "  original: $BEFORE"
echo "  restored: $AFTER"
[ "$AFTER" = "$BEFORE" ] || fail "the restored stack differs from the original"

step "5. The restored server works: sign in and list projects"
PASSWORD="${DEMO_PASSWORD:-Demo-Pass-2026!}"
B="http://localhost:${B_PORT}/api"
TOKEN=$(curl -fsS -X POST "$B/auth/login/" -H 'Content-Type: application/json' -d "{\"email\":\"sma.planner@example.test\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
DISTRICT=$(curl -fsS "$B/auth/me/" -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; print(json.load(sys.stdin)["memberships"][0]["district"]["id"])')
COUNT=$(curl -fsS "$B/projects/" -H "Authorization: Bearer $TOKEN" -H "X-District-ID: $DISTRICT" | python3 -c 'import sys,json; print(json.load(sys.stdin)["count"])')
echo "  signed in; $COUNT project(s) in the district"
[ "$COUNT" -gt 0 ] || fail "the restored server lists no projects"

step "6. A damaged backup is refused"
cp -r "$BACKUP" "$WORK/damaged"
printf 'x' >> "$WORK/damaged/media.tar"
if (export_b; COMPOSE="$B_COMPOSE" SERVICES="db redis backend" scripts/restore.sh "$WORK/damaged" --yes) >/dev/null 2>&1; then
  fail "a backup whose checksum doesn't match was restored"
fi
echo "  refused (checksum mismatch); the restored stack was left alone"
[ "$( (export_b; fingerprint $B_COMPOSE) )" = "$BEFORE" ] || fail "a refused restore changed the stack"

printf '\n\033[1mPhase 13 restore gate: passed\033[0m\n'

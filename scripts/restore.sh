#!/usr/bin/env bash
# Restores a backup made by scripts/backup.sh. EVERYTHING in the running
# database and uploaded files is replaced by the backup. A backup of the
# database only (taken before an update) replaces the database and leaves the
# uploaded files as they are.
#
#   scripts/restore.sh <backup-folder>/<date-time> --yes
#
# Use the same .env the backup's server had (same database role names, and
# the same SPP_ORG_KEYS, or .spp files made before can't be opened).
# COMPOSE can name another stack: COMPOSE="docker compose -p other" scripts/restore.sh ...
# SERVICES can limit what is started afterwards: SERVICES="db redis backend".
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
FROM="${1:-}"
[ -n "$FROM" ] && [ -f "$FROM/db.dump" ] && [ -f "$FROM/manifest.txt" ] || {
  echo "Usage: scripts/restore.sh <backup-folder>/<date-time> --yes" >&2
  echo "(the folder must hold db.dump and manifest.txt)" >&2
  exit 2
}
DB_ONLY=false
if [ ! -f "$FROM/media.tar" ]; then
  # Only a backup that says so may lack the files: a lost media.tar must not pass for one.
  grep -q '^holds: the database only' "$FROM/manifest.txt" || {
    echo "media.tar is missing from $FROM, and its manifest does not say it is a database-only backup." >&2
    exit 2
  }
  DB_ONLY=true
fi
[ "${2:-}" = "--yes" ] || {
  echo "This replaces the whole database and all uploaded files with the backup in $FROM." >&2
  echo "Run it again with --yes to go ahead." >&2
  exit 2
}

echo "Checking the backup's files"
(cd "$FROM" && grep -E '  (db\.dump|media\.tar)$' manifest.txt | sha256sum -c -)

echo "Stopping the application"
$COMPOSE stop backend worker web 2>/dev/null || true

echo "Restoring the database"
$COMPOSE exec -T db sh -c '
  set -e
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" \
    -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""
'
# --no-owner: objects belong to this server's owner role, whatever it is called.
$COMPOSE exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < "$FROM/db.dump"
# Database-level rights aren't part of a dump.
$COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "GRANT CONNECT ON DATABASE \"$POSTGRES_DB\" TO \"$APP_DB_USER\"" -c "GRANT USAGE ON SCHEMA public TO \"$APP_DB_USER\""'

if [ "$DB_ONLY" = true ]; then
  echo "Uploaded files are left as they are (this backup holds the database only)"
else
  echo "Restoring uploaded files"
  $COMPOSE run --rm --no-deps -T backend sh -c 'find /media -mindepth 1 -delete && tar -C /media -xf -' < "$FROM/media.tar"
fi

echo "Starting the application (applies any newer migrations)"
# SERVICES limits what is started (default: everything).
# shellcheck disable=SC2086
$COMPOSE up -d --wait ${SERVICES:-}
echo "Restored from $FROM"

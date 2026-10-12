#!/usr/bin/env bash
# Backs up the platform: the database and every uploaded file.
#
#   scripts/backup.sh [backup-folder]        (default: ./backups)
#
# Makes backup-folder/<date-time>/ with:
#   db.dump        the whole database (pg_dump custom format)
#   media.tar      uploaded files: attachments, photos, imagery
#   manifest.txt   when, what, sizes and SHA-256 checksums
# and removes backups older than KEEP_DAYS (default 14).
#
# DB_ONLY=true leaves out media.tar: for the copy taken before an update,
# which changes the database's shape but never the uploaded files. KEEP_LAST=n
# keeps only the newest n backups in the folder, whatever their age.
#
# NOT included, on purpose: .env. It holds the secrets, including the
# organisation key for .spp files. Keep a copy of it somewhere safe and
# separate; without it a restored server can't open .spp files.
#
# Run it from cron on the server, and copy the folder off the server.
# COMPOSE can name another stack: COMPOSE="docker compose -p other" scripts/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
ROOT="${1:-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DB_ONLY="${DB_ONLY:-false}"
KEEP_LAST="${KEEP_LAST:-}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$ROOT/$STAMP"
mkdir -p "$OUT"

echo "Backing up to $OUT"
# As the owner role: it sees every district's rows (the app role doesn't).
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT/db.dump"
FILES="db.dump"
if [ "$DB_ONLY" != true ]; then
  $COMPOSE exec -T backend tar -C /media -cf - . > "$OUT/media.tar"
  FILES="db.dump media.tar"
fi

[ -s "$OUT/db.dump" ] || { echo "The database dump is empty: backup failed." >&2; exit 1; }
{
  echo "taken: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host: $(hostname)"
  echo "commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "features: $($COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM projects_feature"')"
  [ "$DB_ONLY" != true ] || echo "holds: the database only (uploaded files are not in this backup)"
  # shellcheck disable=SC2086
  (cd "$OUT" && sha256sum $FILES)
  # shellcheck disable=SC2086
  (cd "$OUT" && du -h $FILES)
} > "$OUT/manifest.txt"
cat "$OUT/manifest.txt"

# Old backups go, but never the one just made.
find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime "+$KEEP_DAYS" ! -name "$STAMP" -exec rm -rf {} +
if [ -n "$KEEP_LAST" ]; then
  # Names are dates, so sorted is oldest first.
  find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort | head -n "-$KEEP_LAST" | xargs -r rm -rf
fi
echo "Done: $OUT"

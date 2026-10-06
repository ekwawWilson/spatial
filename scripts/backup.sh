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
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$ROOT/$STAMP"
mkdir -p "$OUT"

echo "Backing up to $OUT"
# As the owner role: it sees every district's rows (the app role doesn't).
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT/db.dump"
$COMPOSE exec -T backend tar -C /media -cf - . > "$OUT/media.tar"

[ -s "$OUT/db.dump" ] || { echo "The database dump is empty: backup failed." >&2; exit 1; }
{
  echo "taken: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host: $(hostname)"
  echo "commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "features: $($COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM projects_feature"')"
  (cd "$OUT" && sha256sum db.dump media.tar)
  (cd "$OUT" && du -h db.dump media.tar)
} > "$OUT/manifest.txt"
cat "$OUT/manifest.txt"

# Old backups go, but never the one just made.
find "$ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$KEEP_DAYS" ! -name "$STAMP" -exec rm -rf {} +
echo "Done: $OUT"

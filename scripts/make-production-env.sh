#!/usr/bin/env bash
# Prints a production .env: the example file with every secret replaced by a
# random value, debug off, and the site's address filled in.
#
#   scripts/make-production-env.sh planning.example.gov.gh > .env
#   chmod 600 .env
#
# Keep a copy of the result somewhere safe and separate from the server: it
# holds the organisation key for .spp files and the database passwords.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${1:-}"
[ -n "$HOST" ] || { echo "Usage: scripts/make-production-env.sh <site address, e.g. planning.example.gov.gh>" >&2; exit 2; }
rand() { openssl rand -base64 "$1" | tr -d '\n=+/' ; }
KEY_ID="org-$(date +%Y%m%d)"

sed \
  -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(rand 60)|" \
  -e "s|^DJANGO_DEBUG=.*|DJANGO_DEBUG=false|" \
  -e "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${HOST},localhost,backend|" \
  -e "s|^CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=https://${HOST}|" \
  -e "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://${HOST}|" \
  -e "s|^WEB_APP_URL=.*|WEB_APP_URL=https://${HOST}|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand 30)|" \
  -e "s|^APP_DB_PASSWORD=.*|APP_DB_PASSWORD=$(rand 30)|" \
  -e "s|^FIELD_ENCRYPTION_KEY=.*|FIELD_ENCRYPTION_KEY=$(rand 48)|" \
  -e "s|^SPP_ORG_KEYS=.*|SPP_ORG_KEYS=${KEY_ID}:$(openssl rand -base64 32)|" \
  -e "s|^WEB_PORT=.*|WEB_PORT=${WEB_PORT:-80}|" \
  .env.example

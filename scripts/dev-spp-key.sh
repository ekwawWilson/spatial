#!/usr/bin/env bash
# Gives a development .env an organisation key for .spp files if it has none.
# For real deployments use `manage.py spp_key generate` and share the key
# between servers yourself (docs/ops/spp-keys.md).
set -euo pipefail
ENV_FILE="${1:-.env}"
[ -f "$ENV_FILE" ] || exit 0
if grep -qE '^SPP_ORG_KEYS=.+' "$ENV_FILE"; then exit 0; fi
KEY="dev-$(date +%Y%m%d):$(openssl rand -base64 32)"
if grep -qE '^SPP_ORG_KEYS=' "$ENV_FILE"; then
  # '|' can't occur in base64, so it is a safe sed delimiter.
  sed -i "s|^SPP_ORG_KEYS=.*|SPP_ORG_KEYS=${KEY}|" "$ENV_FILE"
else
  printf '\nSPP_ORG_KEYS=%s\n' "$KEY" >> "$ENV_FILE"
fi
echo "Added a development organisation key for .spp files to $ENV_FILE"

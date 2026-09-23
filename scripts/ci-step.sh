#!/usr/bin/env bash
# Runs a CI command. On failure, publishes the last lines of its output as a
# GitHub Actions error annotation, so the cause is visible from the run summary
# and the public API without downloading the full log.
set -uo pipefail

log=$(mktemp)
"$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}

if [ "$status" -ne 0 ]; then
  # Annotation messages need %, CR and LF escaped.
  tail -n 40 "$log" | sed -e 's/%/%25/g' -e 's/\r/%0D/g' | awk 'BEGIN{ORS="%0A"}{print}' \
    | { printf '::error title=%s failed (exit %s)::' "$1" "$status"; cat; echo; }
fi
rm -f "$log"
exit "$status"

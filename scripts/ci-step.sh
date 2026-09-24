#!/usr/bin/env bash
# Runs a CI command. On failure, publishes the last lines of its output as a
# GitHub Actions error annotation, so the cause is visible from the run summary
# and the public API without downloading the full log.
set -uo pipefail

log=$(mktemp)
"$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}

if [ "$status" -ne 0 ]; then
  # Crash dumps (e.g. a segfault in a C extension) print the crashing frames
  # first, far above the tail: include fatal errors and frames from our code
  # (/app/...) before the last lines. Annotation messages need %, CR and LF escaped.
  # Also pytest's own failure lines ("E   ..." and "path.py:NN: Error").
  { grep -m 80 -E 'Fatal Python error|File "/app/|^E  |^[A-Za-z_/]+\.py:[0-9]+: [A-Za-z]+' "$log" || true; echo '...'; tail -n 40 "$log"; } \
    | sed -e 's/%/%25/g' -e 's/\r/%0D/g' | awk 'BEGIN{ORS="%0A"}{print}' \
    | { printf '::error title=%s failed (exit %s)::' "$1" "$status"; cat; echo; }
fi
rm -f "$log"
exit "$status"

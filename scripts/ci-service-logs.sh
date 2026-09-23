#!/usr/bin/env bash
# After a failed `compose up`, publish the last log lines of every service that
# is unhealthy or exited non-zero as a GitHub Actions error annotation.
set -uo pipefail

docker compose ps -a --format '{{.Service}} {{.State}} {{.Health}} {{.ExitCode}}' |
while read -r service state health code; do
  if [ "$health" = "unhealthy" ] || { [ "$state" = "exited" ] && [ "$code" != "0" ]; }; then
    docker compose logs --no-color --tail=40 "$service" 2>&1 |
      sed -e 's/%/%25/g' -e 's/\r/%0D/g' | awk 'BEGIN{ORS="%0A"}{print}' |
      { printf '::error title=service %s (%s %s)::' "$service" "$state" "$health"; cat; echo; }
  fi
done

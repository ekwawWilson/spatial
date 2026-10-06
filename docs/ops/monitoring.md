# Monitoring, logs and housekeeping

*Whoever runs the server.*

## Is it up?
`GET /api/health/` answers `200` with `{"ok": true, ...}` when the database, the cache and the GIS libraries are working, and `503` naming the part that isn't. Point any uptime monitor at it (UptimeRobot, Uptime Kuma, the cloud provider's own).

`docker compose ps` shows each container's health.

## Logs
```bash
docker compose logs --tail=200 backend     # requests and errors
docker compose logs --tail=200 worker      # imports, exports, imagery, nightly runs
docker compose logs --tail=200 web         # nginx
```
In production each container keeps at most 200 MB of logs (10 files of 20 MB), then the oldest are dropped. To keep logs longer, ship them elsewhere with your usual tool.

## What to watch
| Watch | Why | Where |
|---|---|---|
| Disk space | Imagery and photos grow. A full disk stops the database. | `df -h`; the volumes are under `/var/lib/docker/volumes/` |
| The nightly backup | See [backups](backup-restore.md). | its log, and that a new dated folder appears |
| Failed background jobs | An import or imagery upload that fails says so to the user; repeated failures suggest a server problem. | worker log |
| The nightly relationship run | Projects' relationship pages show when it last ran and whether it failed. | worker log around 01:30 |
| Repeated `429` answers | Someone is hitting the rate limits: a script, or an attack on sign-in. | backend and nginx logs |

## The audit log
Every change to data is recorded (who, when, before, after) and is never altered. It grows with use. To remove very old entries, after deciding how long the Assembly must keep them:
```bash
make prune-audit DAYS=2555 DRY=1     # how many would go
make prune-audit DAYS=2555
```
Both commands run as the database owner (the running application can't change the audit log). In production add `COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"` after `make`. The command refuses to keep less than a year. A feature's history comes from the audit log, so history older than the cut-off is lost with it. See [data protection](data-protection.md) before choosing a period.

## Leftover files
Uploaded files whose records have been deleted can be left on disk. To see and remove them:
```bash
make clean-media DRY=1               # list them
make clean-media
```

# Spatial Planning Platform

A community planning GIS platform for Ghanaian MMDAs:
- a web app for physical planners;
- an Android field app for data capture;
- a sync service between them.

## Quick start
Requirements: Docker (with Compose v2) and Node 22+.

```bash
make up          # build and start everything, wait until healthy
make fixtures    # build the sample datasets
make test        # backend + frontend tests
make demo-phase-0
```

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API health | http://localhost:8000/api/health/ |
| API docs | http://localhost:8000/api/docs/ |
| Vector tiles (Martin) | http://localhost:3000 |
| Raster tiles (TiTiler) | http://localhost:8001 |

## Layout
```
backend/            Django + GeoDjango API, Celery worker
packages/map-core/  shared TypeScript: API client, map, editing, forms
apps/web/           planner web app (React + OpenLayers)
apps/mobile/        Android field app (Capacitor), from Phase 9
fixtures/           shared test datasets
db/init/            database bootstrap (roles, extensions)
docs/               developer, user and QA documentation
```

See [docs/dev/getting-started.md](docs/dev/getting-started.md) for details, and [docs/dev/phases.md](docs/dev/phases.md) for delivery status.

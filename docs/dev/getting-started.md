# Getting started (developers)

## Prerequisites
- **Docker Engine with the Compose v2 plugin.** Every backend dependency (PostGIS, GDAL, Redis, tile servers) runs in containers. Nothing GIS-related is installed on the host.
- **Node 22+ with corepack**, which provides pnpm (the version is pinned in `package.json`).

## First run
```bash
make up        # creates .env from .env.example if missing
make fixtures
make test
```

## Database roles
Two PostgreSQL roles, created by `db/init/01-roles.sh` when the volume is first created:

| Role | Used by | Why |
|---|---|---|
| `POSTGRES_USER` (owner, superuser) | migrations, tests | creates tables, extensions, test database |
| `APP_DB_USER` (no superuser, no BYPASSRLS) | running backend, worker, Martin | row-level security (Phase 1) only applies to non-superusers |

`core/tests/test_database.py` fails if the app role could bypass row-level security.

If you change the role passwords in `.env` after the first run, recreate the volume with `docker compose down -v` (this **deletes local data**).

## Tests
| Command | What |
|---|---|
| `make test-backend` | pytest inside the backend container, against real PostGIS |
| `make test-web` | Vitest unit tests (map-core, web) |
| `make e2e` | Playwright against the running stack |
| `make check` | lint + type-check + tests, as in CI |

## Fixtures
See [fixtures/README.md](../../fixtures/README.md). Rebuild them with `make fixtures`. CI fails if the committed manifest is out of date.

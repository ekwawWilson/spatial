# Delivery phases: status

The full plan, with scope and exit gates for each phase, is in the approved implementation plan. A phase is complete only when its exit gate **and** the Definition of Done below both pass.

## Definition of Done (every phase)
1. Tests for new code (pytest / Vitest / Playwright); CI green.
2. New tables tenant-scoped with row-level security, plus a cross-district test.
3. Create, update and delete actions audit-logged.
4. Role checks on every endpoint, plus a forbidden-role test.
5. No silent reprojection of stored coordinates.
6. Reversible migrations.
7. `docs/user/` and the OpenAPI schema updated.
8. `make demo-phase-N` works.

Items 2–4 apply from Phase 1 onwards, once the tenancy and role framework exists.

## Status
| Phase | Title | Status |
|---|---|---|
| 0 | Engineering foundation | **complete**: gate passed in CI on 2026-09-23 (`f24f940`) |
| 1 | Identity, tenancy, administration | **complete**: gate passed in CI on 2026-09-24 (`519edd6`) |
| 2 | Coordinate reference systems | not started, **needs official control points** (fixtures/README.md) |
| 3 | Projects, layer engine, web map shell | not started |
| 4 | Basemaps | not started |
| 5 | Import and export | not started |
| 6 | Editing and boundary creation | not started |
| 7 | Readiness checklist | not started |
| 8 | `.spp` project files | not started |
| 9 | Android field app (offline) | not started |
| 10 | Sync, conflicts, ground-truthing | not started |
| 11 | Drone and raster imagery | not started |
| 12 | Relationship layer and procedures | not started |
| 13 | Hardening and release | not started |

## Open items carried forward
- **Phase 3:** Martin (vector tiles) connects as the app role, so row-level security hides tenant tables from it until tile requests carry a district context (e.g. per-district function sources, or tiles served through the API). Design this in Phase 3; don't grant Martin BYPASSRLS.
- **Management commands and Celery tasks** that touch tenant tables must run inside `core.tenancy.tenant_context()`; `seed_demo` shows the pattern.
- Official survey control points for the Phase 2 gate.

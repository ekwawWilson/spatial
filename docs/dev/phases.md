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
| 2 | Coordinate reference systems | **complete except official control points** (decision 2026-09-24): gate passed in CI (`2f87af6`); the control-point test runs automatically once points are added to `fixtures/source/control_points.csv` |
| 3 | Projects, layer engine, web map shell | in progress on branch `phase-3` |
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

## Phase 2 notes
- **Datum-shift accuracy:** the best published Accra → WGS 84 transformation is ±6 m (others ±25 m). Conversions state their accuracy; better parameters can be pinned when the Survey and Mapping Division supplies them.
- **Exact round trips:** PROJ's inverse of a 2D datum shift leaves up to ~3 mm error across Ghana. The platform uses one operation per pair of systems and inverts it numerically, so round trips are exact (< 1e-6 mm). Tested in `crs/tests/test_crs.py`.
- **Web map definitions:** pyproj's PROJ strings omit the datum shift, which would place Accra-datum data about 313 m from the server's position. The API sends proj4 strings with `+towgs84` from the server's operation; tests check that proj4js agrees within 1 cm.
- **Gate item "changing a default doesn't change existing projects":** projects arrive in Phase 3. Phase 2 tests that a default change touches nothing but the setting; Phase 3 adds the project-level test.

## Phase 3 notes
- **Tiles are served by Django** (`ST_AsMVT` inside the request's tenant context), not Martin: row-level security then applies to tiles with no extra machinery. The 100k-feature gate is measured by `test_tiles_for_a_100k_feature_layer_are_fast`, which covers zooms 14–17. The web map draws layers with more than 2,000 features from tiles at zoom 14 and above. Martin stays in docker-compose, unused, until a need appears.
- **Native geometry** has no ORM field; `projects.geometry` is the only reader and writer. Triggers reject SRID mismatches and CRS changes on populated layers.
- **Basemap:** OpenStreetMap is a placeholder until the Phase 4 basemap manager.
- **Smooth panning** of the 100k layer in a browser is a manual QA check (`docs/qa/phase-3-map-performance.md`); the automated gate covers tile response times.

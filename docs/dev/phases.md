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
| 3 | Projects, layer engine, web map shell | **complete except manual panning QA** (decision 2026-09-24): gate passed in CI (`2d702d9`); open item in `docs/qa/phase-3-map-performance.md` |
| 4 | Basemaps | **complete except live-key QA** (decision 2026-09-24): gate passed in CI (`e17bc7b`); open item in `docs/qa/phase-4-basemap-keys.md` |
| 5 | Import and export | **complete except manual QGIS check and DWG verification** (decision 2026-09-24): gate passed in CI (`37e8604`); open items in `docs/qa/phase-5-qgis-exports.md` and the Phase 5 notes |
| 6 | Editing and boundary creation | gate in CI on branch `phase-6`; awaiting the merge decision |
| 7 | Readiness checklist | in progress on branch `phase-7` |
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

## Phase 4 notes
- **Offline caching:** no provider preset allows it (OSM tile policy; Google, Esri and Bing terms). `basemaps.services.assert_offline_allowed()` is the single check, and the Phase 9 packager must call it.
- **API keys** are Fernet-encrypted at rest (`FIELD_ENCRYPTION_KEY`, falling back to a key derived from `SECRET_KEY`), write-only in the API, and left out of audit records. Keys that tile URLs need (Google, Bing) do reach the browser; restrict them by referrer.
- **Gate item "each preset renders with a valid key":** CI has no provider keys. OSM and Esri render in the e2e test. Google session creation and key rejection are tested against a mocked Google API. A live check with real keys is a manual QA item (`docs/qa/phase-4-basemap-keys.md`).

## Phase 5 notes
- **Exactness:** coordinates move between OGR and the platform as GeoJSON with 17 significant figures. Round trips are exact for GPKG, SHP and GeoJSON, within 1e-9° for KML (text precision) and within 1e-6 ft for DXF. See `transfer/tests/test_transfer.py::test_round_trip*`.
- **DWG** needs LibreDWG, which isn't packaged for Ubuntu 24.04. The backend image builds it from source only with `--build-arg WITH_LIBREDWG=true`; that build is **not yet verified**. Without it, DWG import/export says so plainly and the DWG test is skipped.
- **One transaction per import:** a failure or "abort" adds nothing. Progress goes through the cache (Redis db 1), so it's visible while the transaction is open.
- **Gate item "exports open correctly in QGIS"** is manual: `docs/qa/phase-5-qgis-exports.md`.

## Phase 6 notes
- **Map edits** leave the map in EPSG:3857 and are converted server-side (`geometry_crs`), so coordinates of record never depend on the browser's maths.
- **Editing is limited to layers loaded as GeoJSON** (≤ 2,000 features); very large tiled layers are view-only on the map.
- **Undo/redo** replays saves through the API; each step is a new version, so history is complete.
- **GPS-walk boundaries** (method `gps`) are accepted by the API; the field capture that produces them comes in Phase 10.
- **Traverses** use grid bearings; ground distances can be reduced with a scale factor. The known-survey gate test is `projects/tests/test_traverse.py`.
- **Development builds** expose the OpenLayers map as `window.__spatialMap` for browser tests (snapping precision). Production builds don't.

## Phase 7 notes
- **Templates** are copied into each project when it's created (a signal on `PlanProject`), so later template changes never rewrite a project's checklist. "Add new template items" copies what's missing. The platform default has no district; a district's own copy follows the tenant rule.
- **Metrics are live:** computed on each read (`readiness.services`), so the score follows imports and edits without a refresh job. Coverage uses a ~100-cell grid over the planning area in Web Mercator. It measures how spread out the data is, not a survey quantity, and treats points, lines and polygons the same way.
- **Rules gate statuses:** ready and verified need the item's rules met. Only `checklist.verify` (district admins) can verify, or change a verified item.
- **Linking:** an unlinked layer item links to the one project layer with its exact title. Import and Draw from the item create the layer under that title.
- **Send to field** is disabled until Phase 10 (ground-truthing tasks).
- **History fix (from Phase 6 QA):** a save writes the row and then its exact geometry, so each version produced two audit records. Feature history now shows one entry per version, with its complete state.

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
| 6 | Editing and boundary creation | **complete** (decision 2026-09-24): gate passed in CI (`1e796b6`) |
| 7 | Readiness checklist | **complete** (decision 2026-10-06): gate passed in CI (`f1c733e`); "Send to field" was enabled in Phase 10 |
| 8 | `.spp` project files | **complete** (decision 2026-10-06): gate passed in CI (`23e1624`), including the two-server check; saving and opening run inside one request (500 MB limit) |
| 9 | Android field app (offline) | **complete except the on-device test** (decision 2026-10-06): CI passed (`f87aa90`) and the APK builds; open item in `docs/qa/phase-9-field-app-on-device.md` |
| 10 | Sync, conflicts, ground-truthing | **complete except the on-device test and background retry** (decision 2026-10-06): gate passed in CI (`dd932eb`); open items in `docs/qa/phase-10-sync-on-device.md` and the Phase 10 notes |
| 11 | Drone and raster imagery | **complete except the offline basemap on a device** (decision 2026-10-06): gate passed in CI (`5b34526`); the device check is in `docs/qa/phase-9-field-app-on-device.md` |
| 12 | Relationship layer and procedures | **complete** (decision 2026-10-06): gate passed in CI (`1ce4708`) |
| 13 | Hardening and release | **complete except an iOS build, an RTK receiver test and an independent security test** (decision 2026-10-06): gate passed in CI (`bf4c73d`); see the Phase 13 notes |
| 14 | Zoning standards and zoning register | **complete** (2026-10-11): gate passed in CI and deployed (`91acc29`) |
| 15 | Development and planning permits | **complete** (2026-10-12): gate passed in CI and deployed (`ffa5a8d`); what is left is listed in the phase's notes |
| 16 | Online Public Data Room and public register | **complete** (2026-10-12): gate passed in CI and deployed (`ffa5a8d`); what is left is listed in the phase's notes |
| 17 | Enforcement notices and change detection | **complete** (2026-10-12): gate passed in CI and deployed (`ffa5a8d`); what is left is listed in the phase's notes |
| 18 | Re-zoning, change of use, subdivision and consolidation | **complete** (2026-10-12): gate passed in CI and deployed (`4024030`); what is left is listed in the phase's notes |
| 19 | Plan preparation and consultation; plan sheets | **complete** (2026-10-12): gate passed in CI and deployed (`fc79118`); what is left is listed in the phase's notes |
| 20 | Street naming and property addressing | codes and numbers **complete** (2026-10-12, `ffa5a8d`); street naming as a workflow is not built |

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

## Phase 8 notes
- **Two layers:** `spp/container.py` is the encrypted file (AES-256-GCM, chunked, a data key per file wrapped by the organisation key); `spp/package.py` is what's inside (a zip with a manifest, `project.json`, `data.gpkg`, feature history, attachments). Each has its own version number.
- **Exactness:** native geometry goes through OGR as GeoJSON with 17 significant figures, the path Phase 5 proved exact, and is inserted as written. `geom_4326` is derived again on the opening server.
- **Opening makes a new project** in the current district, in one transaction. Ids are new. Feature UUIDs are kept when free on the server and replaced when taken (found with a SECURITY DEFINER function, because row-level security hides other districts' features).
- **History** travels with the features. Ids are reserved from the sequence, the earlier versions are written to the audit log by `app_import_feature_history` (which refuses ids that already have a feature), and the features are inserted last.
- **Custom coordinate systems** are matched by definition or added to the opening district, with a new SRID if needed. EPSG systems must already be enabled on the opening server.
- **Bug fixed on the way:** custom SRIDs were allocated from the systems the current district could see, so a second district's custom system clashed. They now come from `spatial_ref_sys`.
- **Keys:** `SPP_ORG_KEYS`, first key active, others for older files. `manage.py spp_key` generates, installs and lists. `make env` adds a development key. See `docs/ops/spp-keys.md`.
- **"Autosave of drafts":** every edit is already saved on the server through the API as it's made, so there is no separate draft store. A `.spp` file is a snapshot.
- **Gate item "older format version still opens":** version 1 is the only package version so far. The test drives the upgrade path with a stand-in version 2.
- **Gate item "two instances":** `scripts/qa-phase-8-two-servers.sh` starts a second stack with its own database and runs in the CI e2e job.
- **Limits:** files are built and opened inside the request (no background job yet), with the 500 MB upload limit. Very large projects may need the job queue later.
- **Demo scripts** (`make demo-phase-N`) need Python 3.12 or newer on the host. Their summary lines had a quoting mistake in every phase until this one (they were never run: no local Docker, and CI doesn't run demos). Fixed and syntax-checked here; a real run of each is still to do.

## Phase 9 notes
- **Expo, not Capacitor** (decision 2026-10-06): the field app is an Expo (React Native) project laid out like the user's hirepurchase mobile app, with a prebuilt `android/` folder and a local `build-apk.sh`. The earlier plan was a Capacitor wrapper around the web map.
- **What this changes:** the web app's OpenLayers map and editing tools can't be reused on the device (they need a browser). The field app gets its own map (MapLibre React Native) and its own capture screens. The API client, types and CRS maths in `@spatial/map-core` are plain TypeScript and are shared.
- **Server side:** `backend/field` builds the field package (chosen layers, forms, features that touch the planning area, in WGS 84) and an offline basemap (MBTiles) from sources whose terms allow it. The server fetches those tiles itself, so tile addresses inside its own network are refused.
- **Captured positions are WGS 84.** The device shows project coordinates for reading only (with the server's proj4 definition). The server converts captures when they are synced (Phase 10).
- **The app is a standalone npm project** (`apps/mobile`), outside the pnpm workspace. It has its own small API client rather than importing `@spatial/map-core`, to keep Metro's module resolution simple.
- **`android/` is generated** by `expo prebuild` on each build and isn't committed (hirepurchase commits its `android/`). Versions live in `app.json`.
- **Offline sign-in:** a PBKDF2-SHA256 hash of the password (30,000 rounds, random salt) is kept in the phone's secure storage after an online sign-in. The app asks for the password each time it starts.
- **Offline basemap:** no provider preset may be stored offline, so until the Assembly has its own imagery (Phase 11) the offline map has a plain background. With a connection and no offline basemap, OpenStreetMap is shown live.
- **Gate:** the airplane-mode test on a real device and an emulator is a manual check, `docs/qa/phase-9-field-app-on-device.md`. CI covers the server side and the app's logic (type check, unit tests, Expo's project checks).

## Phase 10 notes
- **Push** (`POST /api/sync/push/`): each change has an id and is applied once in its own savepoint; a repeat returns the first result. A create for a feature UUID the server already has is reported as a duplicate, not added again. Rejected changes aren't recorded, so a corrected change can reuse the id.
- **Positions:** devices send WGS 84; `sync.services._native` converts to the layer's CRS with the platform's operation. The round trip back to WGS 84 is exact (Phase 2), so the device's map and the server agree.
- **Conflicts:** an update whose base version isn't the server's goes to `sync_conflict`, never applied automatically. Resolutions: keep office, keep field, merge by field (and optionally the field's shape). Each writes a new version.
- **Pull** is incremental by `updated_at` with a 10-second look-back, and includes tombstones. A trigger on `projects_feature` leaves a tombstone for every delete, whichever code path deletes.
- **Photos:** chunked `PUT` at an explicit offset; the server accepts a chunk only at the size it has on disk and verifies SHA-256 before marking the photo complete.
- **Ground-truthing:** `FieldTask` per feature (one open task per feature). Confirmed and corrected set `verified` and bump `updated_at` but not `version`, so pending edits don't conflict.
- **Device:** unsent work is never overwritten by a pull. A feature's change id is renewed on every local save. Sync runs when the user asks; there is no background service yet, so "retries in the background" from the plan is not met: the app retries when the user syncs again.
- **GPS-walk boundary** (Phase 6, method 5): "Use as the planning area" on a field polygon in the web app.
- **Gate:** the server-side gate tests are in `sync/tests/test_sync.py`. The device side (sync on a real phone, cutting the network mid-upload) is a manual check: `docs/qa/phase-10-sync-on-device.md`.

## Phase 11 notes
- **Tiles are served by Django**, not TiTiler (`imagery/raster.py`: `gdal.Warp` from the COG to a 256-pixel Web Mercator PNG). The same reason as Phase 3: tiles are district data, and TiTiler has no way to apply the tenant rules. TiTiler stays in docker-compose, unused.
- **The stored image is never resampled:** the COG keeps the upload's CRS and pixel grid. Only tiles are warped.
- **Basemap:** a ready orthophoto gets a district `BasemapSource` (XYZ, relative URL, `offline_cache_allowed=True`). The web map loads those tiles through the signed-in API (`basemapSource(..., loadOwnTile)`).
- **Offline:** `field.mbtiles.local_tiles` renders the district's own imagery directly, so the Phase 9 offline-basemap flow now has something to package. No outside service is contacted.
- **Contours** are derived features (`origin=derived`) in the project CRS, converted from the DEM's CRS with the platform's operation. The DEM's CRS must be enabled in the registry.
- **Checklist:** the imagery item's rule `imagery_max_age_days` (365) is evaluated from the newest ready orthophoto's capture date. A migration adds the rule to the default template and to existing project items that had none.
- **Gate:** alignment is tested by finding a building's edges in rendered tiles of the fixture image: within 1 m (one source pixel) on all four sides. The MBTiles content is tested on the server; opening it on a device is part of `docs/qa/phase-9-field-app-on-device.md`.
- **Limits:** 500 MB per upload; images must be north-up; DEM tiles are drawn as a grey stretch (no hillshade).

## Phase 12 notes
- **Roles:** layers are generic, so `relations.LayerRole` says which layer of a project holds the properties, streets and so on (`relations/registry.py` lists the 14 roles and 12 link types). Unmapped roles make their procedures skip, and say so.
- **Procedures** (`relations/procedures.py`) return candidate links; `services.reconcile` makes the stored links match them with the fewest changes. An unchanged link isn't touched, so a nightly run with no data changes writes nothing (and nothing to the audit log).
- **People's decisions win:** a link with `decided_at` set (confirmed, rejected, or made by hand) is never changed or remade by a run.
- **Measurements** use the WGS 84 copy of each geometry as geography, so layers in different coordinate systems can be compared in metres. They are analysis values. The setback check allows 5 cm.
- **Standards** are per district and zone (`DevelopmentStandard`), falling back to the district default (empty zone), then to the platform's 3 m setback.
- **Runs** are all-or-nothing and record a per-procedure report and the totals. Triggers: on request, nightly (`CELERY_BEAT_SCHEDULE`; the docker-compose worker runs with `-B`), and after edits (a signal on feature saves, collapsed to one refresh per 20 seconds; a property is refreshed alone, anything else refreshes the project).
- **Not built:** drainage links are confirmed in the web app, not yet as a field task; needs are a layer the planner supplies (the platform doesn't derive needs from gaps in service).

## Phase 13 notes
- **Gate, and where each part is proved:**
  - *Restore test:* `scripts/qa-phase-13-restore.sh` backs up the running stack, restores into an empty second stack and compares every feature, the audit log and every file. Runs in the CI e2e job.
  - *Load test:* `core/tests/test_load.py` (500,000 features, with time targets for tiles, lists, the field package, a pull and a relationship run) in the backend job; `scripts/load-sync.py` (20 simulated devices syncing at once, some batches sent twice) in the e2e job.
  - *Security:* `docs/ops/security-review.md`. A review by the developer against the code and tests, **not an independent penetration test**. No high or critical findings open; five lower ones accepted with reasons.
- **Restricted fields** (`projects/privacy.py`): a schema flag, redacted for roles without `data.sensitive` in every output. The per-request flag is a context variable set by the authenticator and cleared by the middleware.
- **Rate limits** (`core/throttling.py`) read their rates from settings on each request; off in tests except `test_throttling.py`.
- **Production** (`docker-compose.prod.yml`): gunicorn from the image, nginx serving the built web app, log rotation, no published database port. The server refuses to start with example secrets (`core/checks.py`). A CI job starts it and runs `scripts/qa-phase-13-production.sh`.
- **Housekeeping:** `make prune-audit DAYS=…` (never less than a year) and `make clean-media`, both as the database owner.
- **Field app:** `build-apk.sh --aab` and signing with the Assembly's own key.
- **Not done, and said so in the guides:** an iOS build (needs a Mac and an Apple account); testing with an external RTK receiver; an independent security test; read-access logging; two-factor sign-in; background sync on the phone.
- **Manual and training:** `docs/manual/user-manual.html` is built from the user guides by `scripts/build-manual.py`; courses are in `docs/training/`.

## After Phase 13: the statutory roadmap
From 2026-10-11 the platform grows from a planning GIS into the system an Assembly runs its statutory planning work on, following the Land Use and Spatial Planning Act, 2016 (Act 925), the Regulations (L.I. 2384) and LUSPA's standards and guidelines. Changes go straight to `main`; the deploy job only deploys a commit whose every check passed. Phases, in order:

| Phase | What | Source |
|---|---|---|
| 14 | Zoning standards and zoning register | Revised Zoning Guidelines and Planning Standards (2025); L.I. 2384 r.29, r.47 |
| 15 | Development and planning permits, application to certificate | L.I. 2384 r.43–46; LUSPA permitting guidelines |
| 16 | Online Public Data Room and public register | L.I. 2384 r.64, r.67–68 |
| 17 | Enforcement notices and change detection | L.I. 2384 r.30, r.55–59 |
| 18 | Re-zoning, change of use, subdivision and consolidation | L.I. 2384 r.33, r.34, r.54 |
| 19 | Plan preparation and consultation; plan sheets | L.I. 2384 r.23–27, r.65 |
| 20 | Street naming and property addressing | L.I. 2384 r.28 |
| 21 | Property register, revenue link and betterment | Act 936 s.144; L.I. 2384 r.40–42 |
| 22 | Reports and national links | L.I. 2384 r.29(6), r.32 |

Built from the published law and standards. What needs the Assembly's own documents (its fee-fixing resolution, forms, letterhead, committee membership, approved plans) is made configurable and filled in later.

## Phase 14 notes
- **The national standards as data** (`relations/zoning.py`): 36 zones with codes, colours and groups; site standards and uses for the five residential zones. Transcribed from LUSPA's scanned PDF (section 2.6 and Tables 2–7), so `test_the_national_zones_and_their_standards` pins every site value to the printed table. The document's list of zones swaps the descriptions of Re C and Re D; the section headings and the standards table agree with each other and are followed.
- **Nothing national applies until adopted:** `POST /api/standards/adopt-national/` copies the standards into the district's own rows (`source = luspa-2025`); an edit clears `source`, and adopting again then leaves that row alone unless `replace`.
- **Front, side and back** (`procedures.plot_edges`): each parcel's boundary is taken edge by edge; edges within the nearest quarter of the spread of distances to a street are the front, the farthest quarter the back, the rest sides. Corner plots get two fronts. No street within about 200 m: front unknown, and the smallest setback is asked of every side.
- **Prohibited uses** are keyword matches on the recorded use: inferred, confidence 0.7, for a person to decide.
- **Zone colours:** patterns in the standards (stripes, dots) aren't drawn; such zones get their background colour.
- **Not done:** site standards for non-residential zones (the national document gives facility standards, not a site table, for those); they are Phase 19's facility checks.

## Phase 15 notes
- **Gate:** `permits/tests/test_permits.py`: one application through every step with the right role at each (`test_an_application_from_receipt_to_certificate`), the deadlines at their boundaries, each automatic check against a seeded problem, and the certificate's code checked by an anonymous client. `e2e/phase15.spec.ts` does the journey in the browser and opens the public check page signed out.
- **What the Regulations fix is data** (`permits/registry.py`): the categories of r.44(1) and r.45(1), the documents of r.44(3) and r.45(9), the four deadlines of r.44(6)-(10), the 13 inspection points of r.44(7)(f).
- **The site is a feature** in the project's layer in the "permits" role (made on first use), so it is on the map, in field packages and in the relationship layer's permit matching.
- **Automatic checks** (`permits/checks.py`) are stored on the application as advice; setbacks and coverage need the block plan and are reported as "check on the drawings" with the zone's values.
- **Deadlines are calendar days** from the day of receipt, as the Regulations word them.
- **The public check** (`/api/public/permits/<token>/`) needs no sign-in: the token (24 random bytes) is made when the permit is issued, kept out of the audit log, and looked up across districts. Only issued permits answer.
- **Waiting for the Assembly:** the certificate and letters are plain layouts until its letterhead and the exact Schedule forms (42B, 43C, 43E) arrive; fees are entered by the district administrator from the fee-fixing resolution; acknowledgements are PDFs to hand over or send, with SMS and email to follow once a sender is agreed.
- **Added after the first cut:** the Certificate of Habitation (a completion inspection, then the certificate within 14 days, r.45(18)) and the Land Use Certificate for an application's site (r.46).
- **Not done yet:** reviews and appeals (Form 53), renewals, site inspection from the field app, committee agendas and minutes, and drawing the site on the map from the form.

## Phase 16 notes
- **Gate:** `dataroom/tests/test_dataroom.py`: nothing is public until the room is opened and a project published; the register shows r.67(3)'s particulars with no personal data (`test_the_register_of_permits`); the zone lookup answers from a zoning layer and the adopted standards; requests for information get the five-day date and are kept.
- **Public views** (`dataroom/public.py`) take no sign-in. Each finds the district by its code, requires its room to be open, then reads inside `tenant_context(district)`: row-level security does the scoping, so a public request can never read another district.
- **Personal data:** names only with `show_applicants`; contact details never. The application status lookup works for any application of the district (the applicant holds the number) and returns no name.
- **The register is assembled from the records** (permits, zoning schemes, fees) at each request: no copy to fall out of date.
- **Requests for information** number in their own series (`<district>/IR/<year>/<n>`), sharing `permits.Counter`.
- **Not done yet:** a public map (the lookup is by location or coordinates); SMS replies to status queries; the register as a downloadable file; comments on a draft plan (Phase 19).

## Phase 17 notes
- **Gate:** `enforcement/tests/test_enforcement.py`: a case through rectification notice, service, the r.57(2) and r.57(4) dates and closing; and `test_changes_are_classed_by_permits_and_known_buildings`, where a later image with three painted-in squares yields exactly three changes: one new, one at a known building, one where a permit is granted. `test_the_comparison_finds_what_changed_and_only_that` shows a brighter day alone finds nothing and a 2 x 2 m speck is ignored.
- **Notices are worded after the Schedule's forms** (47, 48A, 48B, 49, 50), read from the published L.I. 2384 (`enforcement/documents.py`). r.55(2)'s four named notices have no Schedule form and share a plain layout.
- **Change detection** (`enforcement/change.py`): both images warped to one grid at about a metre a cell; brightness compared after removing the median difference between the flights; cells over a threshold sieved to patches of 16 m2 or more and polygonised. It needs numpy, which comes with the GDAL image (not pinned in requirements, to keep one build of it).
- **Detections are features** in a layer "Changes found between images", so they are on the map and in field packages; a case opened on one writes its number back to the feature.
- **Runs inside the request** for now: fine for a neighbourhood (the limit is 60 million cells); a district-wide comparison should become a background job.
- **Not done yet:** sending detections to the field app as tasks; photos on a case; acquisition of land as enforcement (r.59, Form 51); the public register's list of enforcement notices (r.67(3)(d)).

## The statutory deadlines page (part of Phase 22, built early)
- `reports/services.compliance`: one count of every statutory clock for the district: permits (r.44), requests for information (r.64(7)), enforcement steps (r.57), zoning scheme duties (r.29), with the share met in time this year. `GET /api/reports/compliance/` and a PDF at `/pdf/`. No models: counted from the other apps' records at each request.
- Open to every role (`reports.view`): it carries numbers, application and case numbers, never names.
- `reports/tests/test_reports.py::test_every_statutory_clock_is_counted` builds one late item of each kind and checks each is counted once under its own heading.

## Plan sheets (part of Phase 19, built early)
- `projects/sheet.py` draws the project's visible layers with reportlab at a true scale in the project's own coordinates: no reprojection, so a distance on the sheet times the scale is the grid distance. `GET /api/projects/<id>/sheet/?paper=&scale=&title=`; the scale used comes back in `X-Sheet-Scale`.
- `projects/geometry.py` stays the only reader of `geom_native`: it gained `in_box` (features touching a box in native coordinates) and `centre`, which the permit and enforcement papers now use.
- Tested: the helpers (frame, scale fitting, grid interval) on known values, and the endpoint on the fixture community (`projects/tests/test_sheet.py`). The drawing itself is checked by eye.
- **Not done:** imagery or a basemap under the plan; the national colour patterns (stripes, dots); a sheet index for areas that need several sheets.

## Phase 20 notes (street codes and property numbers)
- `relations/addressing.py`: `propose` gives every street a code (kept where it has one, else the next free `<district code>-nnn`) and every property a number from its distance along its nearest street, odd on one side and even on the other. Three methods: every 10 m, every metre, or one after another. `apply` writes only the values that differ, through the audited feature table.
- `GET /api/projects/<id>/addressing/` previews (open to `project.view`), `?type=csv` is the whole schedule, `POST` applies (`relations.edit`). No new models: the numbers live in the layers' own fields (`street_code`, `house_no`, `street`).
- The side of the street is the turn from the street's heading to the property's bearing; numbering from the far end swaps the sides.
- `relations/tests/test_addressing.py` checks the fixture's six buildings on Main Street against numbers worked out by hand.
- **Not done:** street naming as a workflow (proposal, Assembly approval, gazette); a street drawn as several lines is numbered per line; address labels on the plan sheet; ghanapostgps digital addresses; the national manual's exact convention is a setting until the Assembly confirms its own.

## Phase 18 notes (re-zoning, change of use, subdivision and consolidation)
- App `landchange`. `registry.py` holds what L.I. 2384 fixes for each kind, read from the published text: the steps of r.33 and r.54 with their days and what the days run from, the grounds of r.33(2)-(3), and the tests of r.34. `services.clocks` works every due date from that registry, so a step is added or corrected in one place.
- Steps are stored as `{code: {on, note}}` on the application. Steps that apply only in some cases (referral of objections; what follows an approval) appear when the case arises.
- **Abutting land** (`services.abutting`): the parcels within 0.5 m of the application's parcels, in the same layer. Gate: on the fixture, exactly the parcels that touch.
- **Readings of the text where it is silent or loose:** with no objection, the 60 days of r.33(15) are counted from the end of the 28-day comment period; a change of use takes the 30 days of a planning permit (r.44(10)); an approval is refused while the comment period runs, a refusal is not.
- An approved re-zoning is written to the parcels' zone field by `services.apply_zone`, one audited change per parcel. Subdivision and consolidation are not drawn automatically.
- Papers (`documents.py`): public notice, notice to abutting owners, decision, notice to the Lands Commission. They say what the Regulations require; the Schedule's layouts (Forms 33A/B, 35, 46, 59) are wanted from the Assembly.
- Public: `GET /api/public/rooms/<code>/land-applications/` lists what is on display, without personal details.
- Permissions: the permit ones (`permit.view`, `permit.process`, `permit.decide`).
- Gate: `landchange/tests/test_landchange.py` (every clock of r.33 and r.54, r.34's tests, the abutting list, the map change, the public listing); `apps/web/e2e/phase18.spec.ts`.
- The statutory deadlines page counts these applications too (`land` in `reports/services.compliance`).
- **Not done:** the public sending Form 59 online; the draft re-zoning report (Form 34); drawing an approved subdivision from the application; fees.

## Phase 19 notes (making a local plan, and consultation)
- App `planmaking`. `registry.py` holds the steps of L.I. 2384 r.23, r.25 and r.26 with their forms and times, the seventeen items of r.24(1), the conditions of r.27 and the stages of consultation, all read from the published text. One `PlanProcess` per project (made on first write), steps stored as `{code: {on, note}}`.
- Clocks: twelve calendar months from the structure plan (r.23(1)); sixty days of comment from the notice (r.23(5)); seven days to publish the approval (r.25(5)); for a plan prepared by another person, ninety days to decide (r.25(1)) and the r.26 confirmation steps (28 and 7 days). The approval is refused while the sixty days run.
- `Consultation` with minutes as a PDF, displayed in the Public Data Room when marked (r.65(3)). `PlanComment` from the office or, through `POST /api/public/rooms/<code>/plans/<project>/comments/`, from anyone while comments are open; commenters are never shown publicly.
- Permissions: `project.view` to read, `project.edit` to record, `permit.decide` for the approval and confirmation steps.
- Gate: `planmaking/tests/test_planmaking.py`; `apps/web/e2e/phase19.spec.ts`.
- **Not done:** the facility checks against the planning standards (schools, clinics, markets per head of population); comments pinned to a place on the map; Forms 27 to 31 and 56 in the Schedule's own layout; the structure plan and Spatial Development Framework procedures (r.9 to r.22), which are regional or district-wide and not per community.


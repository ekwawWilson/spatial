# Phase 3 design: projects, layers and the map shell

Decisions to settle before building Phase 3. Scope and the exit gate are in the plan (see `docs/dev/phases.md`).

## 1. Storing geometry without silent reprojection
Definition of Done item 5: coordinates are stored exactly as given, in the layer's native CRS.

**Problem.** GeoDjango's `GeometryField(srid=N)` creates a column constrained to SRID N. Layers have different native systems (EPSG:2136, a custom grid, UTM…), and GeoDjango transforms geometries whose SRID differs from the field's. That is exactly the silent reprojection we must avoid.

**Decision.**
- `feature.geom_native`: an **unconstrained** PostGIS `geometry` column (no SRID typmod), created by a `RunSQL` migration. Each row carries its layer's SRID inside the geometry. A `CHECK`-style trigger rejects a feature whose SRID differs from `layer.srid`, so a wrong-CRS write fails loudly instead of being converted.
- Reads and writes of `geom_native` go through a small repository module using explicit SQL (`ST_GeomFromWKB(..., srid)`), not a GeoDjango field. There is no ORM magic on the coordinates of record.
- `feature.geom_4326`: GeoDjango `GeometryField(srid=4326)`, used for display, tiles and cross-layer queries. It is **derived, never edited**.

**How `geom_4326` is computed.** PostGIS's `ST_Transform` picks its own operation, which may differ from the platform's pinned or canonical one (Phase 2). Instead:
- `geom_4326` is computed with **`ST_TransformPipeline(geom_native, <pipeline>, 4326)`** (PostGIS ≥ 3.4), using the pipeline from `crs.services` for (layer CRS → WGS 84). Map display, tiles and the server's conversions then all use one operation.
- When an admin pins a different operation, a Celery job recomputes `geom_4326` for affected layers. `geom_native` is untouched.

To verify when Phase 3 starts: `ST_TransformPipeline` availability in `postgis/postgis:16-3.5` and its performance on 100k features.

## 2. Tenancy
`plan_project`, `layer` and `feature` all carry `district_id` and use `tenant_rls_sql()`. `feature.district_id` is denormalised, rather than joined through the layer, so the row-level security check stays a plain column comparison, which matters for tile queries.

## 3. Vector tiles and row-level security
Martin connects as the app role, so it sees nothing in tenant tables (noted in Phase 1).

**Decision:** tiles are served by a PostGIS **function source** `layer_tiles(z, x, y, query_params)`:
- Martin passes the request's query parameters. The web app sends a short-lived signed tile token (issued by the API: user, district, layer ids, expiry).
- The function verifies the token's HMAC with a secret held in a table only the function owner can read (`SECURITY DEFINER`), sets the tenant context for the statement, and returns MVT for the permitted layers.
- The browser never gets database-level trust; the token only narrows what the function returns.

Fallback, if Martin function sources prove awkward: serve MVT from Django (`ST_AsMVT` via the API) with HTTP caching. This is simpler, but slower under load. Decide after a spike at the start of Phase 3.

## 4. Layer schema (fields)
`layer.schema` is JSON: a list of `{name, label, type, required, choices, default}`.
- Types: text, integer, decimal, boolean, date, choice.
- Validation runs server-side in one function, used by the API, the importer (Phase 5) and field sync (Phase 10). The web forms mirror it for instant feedback, but the server is the authority.
- Changing a field's type validates existing values first. The change is refused if any value wouldn't convert, and the offending feature ids are listed.

## 5. The web map
- OpenLayers.
- The **view projection is the project's CRS** when the basemap allows it. Otherwise it's EPSG:3857, with coordinates always *displayed and entered* in the project CRS (proj4 definitions from Phase 2).
- Layer tree state (order, visibility, opacity, style) is saved per layer on the server, so every user and the field app see the same map.
- Measurement uses geodesic calculations in metres and shows project units alongside.

## 6. Gate carried over from Phase 2
Test: after a project is created in CRS X, changing the system, district and user defaults leaves the project's CRS and every feature's `geom_native` byte-identical.

# Test fixtures

Shared datasets used by backend, web and mobile tests.

## `generated/`: sample community (rebuild with `make fixtures`)
Built by `backend/core/management/commands/build_fixtures.py`. Deterministic, so it's safe to commit.

Layers: district, communities, parcels, buildings, streets, drains, flood_zones. The same data is written as GPKG, GeoJSON, SHP (plus zipped), KML and DXF, along with a synthetic drone orthophoto (GeoTIFF).

Native CRS: **EPSG:2136** (Ghana National Grid). GeoJSON and KML are WGS84. DXF carries no CRS. `shp_no_crs/` deliberately has no `.prj`.

Conditions planted on purpose, which later phases test against (see `manifest.json`):

| Condition | Where | Used by |
|---|---|---|
| Communities A and B overlap by 10 m | x = 990–1000 m | Phase 6 overlap report |
| Building B-006 inside flood zone F-001 | southern parcel row | Phase 12 flood procedure |
| Building B-003 0.5 m from its east boundary (normal 3 m) | parcel P-003 | Phase 12 setback rule |

## `source/control_points.csv`: survey control points (**action needed**)
The Phase 2 exit gate checks CRS transforms against **official** control points: published coordinates in both the Ghana National Grid and WGS84. The file is currently only a header.

Obtain 5–10 points spread across the country, with stated accuracy, from the Survey and Mapping Division (Lands Commission) and fill in the file. Until then the control-point test is **skipped** and reported as such. Do not fill the file with values computed by PROJ: that would only test PROJ against itself.

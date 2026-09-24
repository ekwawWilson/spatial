# QA: Phase 5 exports open correctly in QGIS

**Status:** not yet run (needs QGIS and a running stack).

## Steps
1. `make up seed`, sign in as `sma.planner@example.test`, and create a project.
2. Import `fixtures/generated/sample.gpkg` (all layers) and `fixtures/generated/shp/buildings.zip`.
3. Export all layers as each format: GeoPackage, Shapefile, GeoJSON, KML, KMZ, DXF (and DWG if enabled).
4. For each download, open it in QGIS 3.34 or later and check:
   - the layer's CRS (Layer Properties → Information) matches the README;
   - features line up with the originals (drag `sample.gpkg` in as a reference);
   - attributes are present (not for DXF/DWG); for Shapefile, `*_fields.csv` lists the full names;
   - text with non-ASCII characters (e.g. "Adwoa's plot – Ɛ") displays correctly.

## Record
| Date | Tester | QGIS version | Format | CRS ok | Aligned | Attributes | Notes |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

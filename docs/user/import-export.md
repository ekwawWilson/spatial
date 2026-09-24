# Importing and exporting data

*Physical planners and district administrators.*

## Importing
In a project, choose **Import data**.

1. **Choose a file.** Accepted: Shapefile (zip the .shp together with its .shx, .dbf and .prj), GeoPackage, GeoJSON, KML/KMZ, DXF, DWG (if the server supports it) and CSV with coordinate columns (x/y, lon/lat or easting/northing). Up to 500 MB.
2. **Check what's in it.** For each layer in the file you'll see its features, shape types and fields, and the coordinate system the file says it uses.
3. **Decide:**
   - **Coordinates are in:** the coordinate system of the file's coordinates. If the file doesn't say, or it's a DXF, DWG or CSV file (these never reliably record it), you must choose one **and tick the confirmation**. Nothing is guessed.
   - **Import into:** a new layer, which keeps the file's coordinate system unchanged, or an existing layer. If the existing layer uses a different system, the coordinates are converted and the report names the transformation and its accuracy.
   - **Fields:** what each field in the file becomes. Shapefiles cut names to 10 characters (e.g. `property_i`); give them their full names here. Files exported from this platform restore them automatically.
   - **Invalid shapes:** skip them, try to repair them, or stop the whole import.
   - **Duplicates**, and **values that don't fit** a field's rules: keep/leave empty, or skip.
   - **CAD layers** (DXF/DWG): which drawing layers to take.
4. **Import.** Progress is shown. At the end, a report lists how many features were imported or skipped, and why, row by row.

An import either completes or changes nothing: if it fails or you chose "stop the import", no features are added.

## Exporting
In a project, choose **Export**, then pick layers (or tick **Only the selected feature**), a format and a coordinate system.

| Format | Notes |
|---|---|
| GeoPackage | best all-round choice; keeps everything |
| Shapefile | field names cut to 10 characters; `<layer>_fields.csv` in the zip lists the full names |
| GeoJSON | in each layer's own system unless you choose one |
| KML / KMZ | always WGS 84 (Google Earth) |
| DXF / DWG | CAD: shapes and layer names only, no attribute values; DWG only if the server supports it |

Exports keep **each layer's own coordinate system** unless you choose another. Coordinates then come out exactly as stored. Every download includes a `README.txt` stating the coordinate system, and naming any conversion with its accuracy.

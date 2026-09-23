"""Builds the shared test datasets in FIXTURES_DIR/generated.

The sample community is designed in metres (UTM 30N) with deliberately seeded
conditions that later phases test against:

* the two communities overlap by a 10 m strip       -> Phase 6 overlap report
* building B-006 lies inside the flood-prone zone   -> Phase 12 flood procedure
* building B-003 is 0.5 m from its parcel boundary  -> Phase 12 setback rule

Outputs (native CRS = EPSG:2136 Ghana National Grid, unless stated):
  sample.gpkg                 all layers
  geojson/<layer>.geojson     WGS84 (EPSG:4326), full precision
  shp/<layer>.shp (+ .zip)    with .prj and .cpg
  shp_no_crs/parcels.shp      no .prj -> CRS must be asked for on import
  kml/<layer>.kml             WGS84, as the KML spec requires
  sample.dxf                  all layers, no CRS (CAD convention)
  drone_ortho.tif             200 x 200 m synthetic orthophoto, 1 m pixels, EPSG:32630
  manifest.json               expected facts the tests check
"""

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

DESIGN_EPSG = 32630  # UTM 30N, metres
NATIVE_EPSG = 2136  # Ghana National Grid (Accra datum, Gold Coast feet)
WGS84_EPSG = 4326

# Lower-left corner of the sample district, in UTM 30N metres (near Accra).
ORIGIN_E = 806_000.0
ORIGIN_N = 617_000.0


def srs(epsg: int) -> osr.SpatialReference:
    ref = osr.SpatialReference()
    ref.ImportFromEPSG(epsg)
    ref.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return ref


def rect(x0: float, y0: float, x1: float, y1: float) -> str:
    """Polygon WKT from local offsets (metres from the origin)."""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return "POLYGON((" + ",".join(f"{ORIGIN_E + x} {ORIGIN_N + y}" for x, y in pts) + "))"


def line(*pts: tuple[float, float]) -> str:
    return "LINESTRING(" + ",".join(f"{ORIGIN_E + x} {ORIGIN_N + y}" for x, y in pts) + ")"


# layer name -> (geometry type, field definitions, features[(wkt, attrs)])
Field = tuple[str, int]
LayerSpec = tuple[int, list[Field], list[tuple[str, dict[str, Any]]]]


def design_layers() -> dict[str, LayerSpec]:
    s, i, r = ogr.OFTString, ogr.OFTInteger, ogr.OFTReal

    parcels: list[tuple[str, dict[str, Any]]] = []
    buildings: list[tuple[str, dict[str, Any]]] = []
    # Two rows of three 30 x 30 m parcels either side of Main Street (y = 1000),
    # each starting 10 m from the street centreline (the road reserve).
    rows = [(1010.0, 1040.0), (960.0, 990.0)]
    n = 0
    for y0, y1 in rows:
        for k in range(3):
            n += 1
            x0 = 520.0 + 30.0 * k
            x1 = x0 + 30.0
            parcels.append((
                rect(x0, y0, x1, y1),
                {"parcel_id": f"P-{n:03d}", "land_use": "residential",
                 "tenure": "customary", "area_m2": 900.0},
            ))
            # Normal setback is 3 m on every side. B-003 is built 0.5 m from
            # its eastern boundary (seeded setback breach).
            east_setback = 0.5 if n == 3 else 3.0
            buildings.append((
                rect(x0 + 3.0, y0 + 3.0, x1 - east_setback, y1 - 3.0),
                {"property_id": f"B-{n:03d}", "use": "residential",
                 "floors": 2 if n % 2 else 1, "condition": "good"},
            ))

    return {
        "district": (ogr.wkbPolygon, [("name", s), ("code", s)], [
            (rect(0, 0, 2000, 2000), {"name": "Sample Municipal Assembly", "code": "SMA"}),
        ]),
        "communities": (ogr.wkbPolygon, [("name", s), ("code", s)], [
            # 10 m overlap strip between x = 990 and x = 1000 (seeded).
            (rect(0, 0, 1000, 2000), {"name": "Community A", "code": "SMA-A"}),
            (rect(990, 0, 2000, 2000), {"name": "Community B", "code": "SMA-B"}),
        ]),
        "parcels": (ogr.wkbPolygon, [("parcel_id", s), ("land_use", s), ("tenure", s),
                                      ("area_m2", r)], parcels),
        "buildings": (ogr.wkbPolygon, [("property_id", s), ("use", s), ("floors", i),
                                        ("condition", s)], buildings),
        "streets": (ogr.wkbLineString, [("name", s), ("street_code", s), ("hierarchy", s)], [
            (line((0, 1000), (2000, 1000)),
             {"name": "Main Street", "street_code": "SMA-001", "hierarchy": "collector"}),
            (line((500, 0), (500, 2000)),
             {"name": "Asafo Road", "street_code": "SMA-002", "hierarchy": "local"}),
            (line((1500, 0), (1500, 2000)),
             {"name": "Market Road", "street_code": "SMA-003", "hierarchy": "local"}),
        ]),
        "drains": (ogr.wkbLineString, [("drain_id", s), ("type", s), ("condition", s)], [
            # Roadside drain on the north side of Main Street, flowing east.
            (line((500, 1006), (700, 1006)),
             {"drain_id": "D-001", "type": "open_concrete", "condition": "silted"}),
        ]),
        "flood_zones": (ogr.wkbPolygon, [("zone_id", s), ("risk", s)], [
            # Covers the eastern part of the southern parcel row: hits B-006.
            (rect(590, 940, 700, 1000), {"zone_id": "F-001", "risk": "high"}),
        ]),
    }


class Command(BaseCommand):
    help = "Build the shared test datasets in FIXTURES_DIR/generated."

    def handle(self, *args: Any, **options: Any) -> None:
        out = Path(settings.FIXTURES_DIR) / "generated"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)

        layers = design_layers()
        design = srs(DESIGN_EPSG)
        native = srs(NATIVE_EPSG)
        wgs84 = srs(WGS84_EPSG)
        to_native = osr.CoordinateTransformation(design, native)
        to_wgs84 = osr.CoordinateTransformation(design, wgs84)

        self._write(out / "sample.gpkg", "GPKG", layers, native, to_native, multi_layer=True)
        for sub, driver, ext, ref, ct in (
            ("geojson", "GeoJSON", "geojson", wgs84, to_wgs84),
            ("shp", "ESRI Shapefile", "shp", native, to_native),
            ("kml", "LIBKML", "kml", wgs84, to_wgs84),
        ):
            (out / sub).mkdir()
            for name in layers:
                self._write(out / sub / f"{name}.{ext}", driver, {name: layers[name]}, ref, ct,
                            options=["ENCODING=UTF-8"] if driver == "ESRI Shapefile" else [])
        self._zip_shapefiles(out / "shp")

        (out / "shp_no_crs").mkdir()
        self._write(out / "shp_no_crs" / "parcels.shp", "ESRI Shapefile",
                    {"parcels": layers["parcels"]}, native, to_native)
        (out / "shp_no_crs" / "parcels.prj").unlink()

        self._write_dxf(out / "sample.dxf", layers, to_native)
        self._write_ortho(out / "drone_ortho.tif", design)
        self._write_manifest(out / "manifest.json", layers)
        self.stdout.write(self.style.SUCCESS(f"Fixtures written to {out}"))

    def _write(self, path: Path, driver_name: str, layers: dict[str, LayerSpec],
               ref: osr.SpatialReference, ct: osr.CoordinateTransformation,
               multi_layer: bool = False, options: list[str] | None = None) -> None:
        ds = gdal.GetDriverByName(driver_name).Create(str(path), 0, 0, 0, gdal.GDT_Unknown)
        for name, (gtype, fields, feats) in layers.items():
            lyr = ds.CreateLayer(name, ref, gtype, options=options or [])
            for fname, ftype in fields:
                lyr.CreateField(ogr.FieldDefn(fname, ftype))
            for wkt, attrs in feats:
                geom = ogr.CreateGeometryFromWkt(wkt)
                geom.Transform(ct)
                feat = ogr.Feature(lyr.GetLayerDefn())
                feat.SetGeometry(geom)
                for key, value in attrs.items():
                    feat.SetField(key, value)
                lyr.CreateFeature(feat)
        ds.Close()

    def _zip_shapefiles(self, folder: Path) -> None:
        for shp in folder.glob("*.shp"):
            with zipfile.ZipFile(folder / f"{shp.stem}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
                for part in folder.glob(f"{shp.stem}.*"):
                    if part.suffix != ".zip":
                        zf.write(part, part.name)

    def _write_dxf(self, path: Path, layers: dict[str, LayerSpec],
                   ct: osr.CoordinateTransformation) -> None:
        # DXF keeps only the CAD layer name, so each source layer becomes a DXF layer.
        ds = gdal.GetDriverByName("DXF").Create(str(path), 0, 0, 0, gdal.GDT_Unknown)
        lyr = ds.CreateLayer("entities")
        for name, (_gtype, _fields, feats) in layers.items():
            for wkt, _attrs in feats:
                geom = ogr.CreateGeometryFromWkt(wkt)
                geom.Transform(ct)
                feat = ogr.Feature(lyr.GetLayerDefn())
                feat.SetField("Layer", name)
                feat.SetGeometry(geom)
                lyr.CreateFeature(feat)
        ds.Close()

    def _write_ortho(self, path: Path, design: osr.SpatialReference) -> None:
        # Synthetic 3-band image over the parcels: grey ground, dark road strip
        # along Main Street, lighter squares where buildings stand.
        size = 200
        x0, y_top = ORIGIN_E + 450.0, ORIGIN_N + 1100.0
        bands = [bytearray([150] * size * size) for _ in range(3)]
        for row in range(size):
            y = 1100.0 - row - 0.5
            for col in range(size):
                x = 450.0 + col + 0.5
                idx = row * size + col
                if 995.0 <= y <= 1005.0:
                    value = (60, 60, 60)
                elif any(523 + 30 * k <= x <= 547 + 30 * k for k in range(3)) and (
                    1013 <= y <= 1037 or 963 <= y <= 987
                ):
                    value = (210, 200, 190)
                else:
                    value = (110, 140, 90)
                for b in range(3):
                    bands[b][idx] = value[b]
        ds = gdal.GetDriverByName("GTiff").Create(str(path), size, size, 3, gdal.GDT_Byte,
                                                   options=["COMPRESS=DEFLATE"])
        ds.SetGeoTransform((x0, 1.0, 0.0, y_top, 0.0, -1.0))
        ds.SetProjection(design.ExportToWkt())
        for b in range(3):
            ds.GetRasterBand(b + 1).WriteRaster(0, 0, size, size, bytes(bands[b]))
        ds.SetMetadata({"CAPTURE_DATE": "2026-09-01", "SOURCE": "synthetic test orthophoto"})
        ds.Close()

    def _write_manifest(self, path: Path, layers: dict[str, LayerSpec]) -> None:
        manifest = {
            "native_crs": f"EPSG:{NATIVE_EPSG}",
            "design_crs": f"EPSG:{DESIGN_EPSG}",
            "layers": {name: len(spec[2]) for name, spec in layers.items()},
            "seeded": {
                "community_overlap": {"a": "SMA-A", "b": "SMA-B", "width_m": 10.0},
                "building_in_flood_zone": {"property_id": "B-006", "zone_id": "F-001"},
                "setback_breach": {"property_id": "B-003", "parcel_id": "P-003",
                                   "side": "east", "setback_m": 0.5, "normal_setback_m": 3.0},
            },
        }
        path.write_text(json.dumps(manifest, indent=2) + "\n")

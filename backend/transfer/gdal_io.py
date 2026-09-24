"""Reading and writing geodata files with GDAL/OGR.

Coordinates move between OGR and the platform as GeoJSON with 17 significant
figures, enough to reproduce every double exactly, so nothing is rounded on the
way in or out.
"""

import csv
import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

EXACT_JSON = ["SIGNIFICANT_FIGURES=17"]

# Formats whose files carry no reliable CRS: the user must always confirm one.
CONFIRM_CRS_FORMATS = {"dxf", "dwg", "csv"}

EXTENSIONS = {
    ".zip": "shp_zip",
    ".shp": "shp",
    ".dxf": "dxf",
    ".dwg": "dwg",
    ".kml": "kml",
    ".kmz": "kmz",
    ".gpkg": "gpkg",
    ".geojson": "geojson",
    ".json": "geojson",
    ".csv": "csv",
}

OGR_TO_FIELD = {
    ogr.OFTInteger: "integer",
    ogr.OFTInteger64: "integer",
    ogr.OFTReal: "decimal",
    ogr.OFTString: "text",
    ogr.OFTDate: "date",
    ogr.OFTDateTime: "text",
    ogr.OFTTime: "text",
}

# Geometry families the platform stores (see projects.models.GeometryType).
FAMILY = {
    "Point": "point",
    "MultiPoint": "point",
    "LineString": "line",
    "MultiLineString": "line",
    "Polygon": "polygon",
    "MultiPolygon": "polygon",
}


def detect_format(filename: str) -> str:
    fmt = EXTENSIONS.get(Path(filename).suffix.lower())
    if fmt is None:
        supported = ", ".join(sorted({k for k in EXTENSIONS if k != ".json"}))
        raise ValidationError(f"Unsupported file type. Supported: {supported}.")
    return fmt


def dwg_available() -> bool:
    return shutil.which("dwg2dxf") is not None and shutil.which("dxf2dwg") is not None


def prepare(file: Path, fmt: str) -> tuple[str, Path | None]:
    """The path GDAL should open, and the folder a zip was unpacked into.

    Zipped shapefiles are checked (safety.check_zip) and unpacked, so companion
    files such as our <layer>_fields.csv are readable too.
    """
    if fmt == "shp_zip":
        import zipfile

        from .safety import check_zip

        check_zip(file)
        target = file.parent / "unpacked"
        if not target.exists():
            with zipfile.ZipFile(file) as archive:
                archive.extractall(target)  # noqa: S202 - members checked by check_zip
        if not any(target.rglob("*.shp")):
            raise ValidationError("The zip file contains no shapefile (.shp).")
        return str(target), target
    return gdal_path(file, fmt), None


def gdal_path(file: Path, fmt: str) -> str:
    """The path GDAL should open; converts DWG to DXF first (LibreDWG)."""
    if fmt == "dwg":
        if not dwg_available():
            raise ValidationError("DWG isn't available on this server (LibreDWG is not installed).")
        dxf = file.with_suffix(".converted.dxf")
        if not dxf.exists():
            result = subprocess.run(  # noqa: S603 - fixed tool, our own file paths
                ["dwg2dxf", "-y", "-o", str(dxf), str(file)],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode != 0 or not dxf.exists():
                raise ValidationError(f"Couldn't read the DWG file: {result.stderr.strip()[:300]}")
        return str(dxf)
    return str(file)


def open_options(
    fmt: str, encoding: str | None = None, csv_columns: dict[str, str] | None = None
) -> list[str]:
    options = []
    if fmt in ("shp", "shp_zip") and encoding:
        options.append(f"ENCODING={encoding}")
    if fmt == "csv":
        columns = csv_columns or {}
        options += [
            f"X_POSSIBLE_NAMES={columns.get('x', 'x,lon,long,longitude,easting,e')}",
            f"Y_POSSIBLE_NAMES={columns.get('y', 'y,lat,latitude,northing,n')}",
            "KEEP_GEOM_COLUMNS=NO",
            "AUTODETECT_TYPE=YES",
        ]
    return options


def open_dataset(path: str, fmt: str, **kwargs: Any) -> gdal.Dataset:
    # In CAD drawings, parcels and buildings are closed polylines: read them as
    # polygons rather than lines.
    config = {"DXF_CLOSED_LINE_AS_POLYGON": "TRUE"} if fmt in ("dxf", "dwg") else {}
    try:
        with gdal.config_options(config):
            return gdal.OpenEx(
                path, gdal.OF_VECTOR | gdal.OF_READONLY, open_options=open_options(fmt, **kwargs)
            )
    except RuntimeError as exc:
        raise ValidationError(f"GDAL couldn't open the file: {exc}") from exc


def describe_srs(srs: osr.SpatialReference | None) -> dict[str, Any]:
    """The file's CRS: best EPSG match and PROJ's confidence in it (0-100)."""
    if srs is None:
        return {"found": False, "epsg": None, "confidence": 0, "name": None, "wkt": None}
    matches = srs.FindMatches() or []
    epsg, confidence = None, 0
    if matches:
        match, confidence = matches[0]
        if match.GetAuthorityName(None) == "EPSG":
            epsg = int(match.GetAuthorityCode(None))
    return {
        "found": True,
        "epsg": epsg if confidence >= 70 else None,
        "confidence": int(confidence),
        "name": srs.GetName(),
        "wkt": srs.ExportToWkt(["FORMAT=WKT2_2019"]),
    }


def _shp_field_mapping(root: Path) -> dict[str, dict[str, str]]:
    """Full field names from our own SHP exports (<layer>_fields.csv beside the
    shapefile): {layer: {short: full}}."""
    mapping: dict[str, dict[str, str]] = {}
    for csv_file in root.rglob("*_fields.csv"):
        layer = csv_file.name[: -len("_fields.csv")]
        with open(csv_file, newline="", encoding="utf-8") as fh:
            mapping[layer] = {row["shapefile_name"]: row["full_name"] for row in csv.DictReader(fh)}
    return mapping


def inspect(file: Path, fmt: str, **kwargs: Any) -> dict[str, Any]:
    """What a file contains, for the user to decide how to import it."""
    path, extracted = prepare(file, fmt)
    ds = open_dataset(path, fmt, **kwargs)
    full_names = _shp_field_mapping(extracted) if extracted else {}
    layers = []
    for i in range(ds.GetLayerCount()):
        layer = ds.GetLayer(i)
        defn = layer.GetLayerDefn()
        geometry_types: dict[str, int] = {}
        cad_layers: set[str] = set()
        has_z = False
        for feature in layer:
            geom = feature.GetGeometryRef()
            name = "None" if geom is None else _family_name(geom)
            geometry_types[name] = geometry_types.get(name, 0) + 1
            if geom is not None and geom.Is3D():
                has_z = True
            if fmt in ("dxf", "dwg"):
                cad_layers.add(str(feature.GetField("Layer")))
        layer.ResetReading()
        fields = []
        for j in range(defn.GetFieldCount()):
            field = defn.GetFieldDefn(j)
            source_name = field.GetName()
            fields.append(
                {
                    "name": source_name,
                    "suggested_name": full_names.get(layer.GetName(), {}).get(
                        source_name, source_name
                    ),
                    "type": OGR_TO_FIELD.get(field.GetType(), "text"),
                }
            )
        encoding = (
            layer.GetMetadataItem("SOURCE_ENCODING", "SHAPEFILE")
            if fmt in ("shp", "shp_zip")
            else "UTF-8"
        )
        layers.append(
            {
                "name": layer.GetName(),
                "feature_count": layer.GetFeatureCount(),
                "geometry_types": geometry_types,
                "has_z": has_z,
                "fields": fields,
                "crs": describe_srs(layer.GetSpatialRef()),
                "encoding": encoding or None,
                "cad_layers": sorted(cad_layers),
            }
        )
    return {
        "format": fmt,
        "layers": layers,
        "crs_confirmation_required": fmt in CONFIRM_CRS_FORMATS,
    }


def _family_name(geom: ogr.Geometry) -> str:
    """OGR geometry type as a GeoJSON type name (curves as their linear forms)."""
    geom_type = ogr.GT_Flatten(geom.GetGeometryType())
    names = {
        ogr.wkbPoint: "Point",
        ogr.wkbMultiPoint: "MultiPoint",
        ogr.wkbLineString: "LineString",
        ogr.wkbMultiLineString: "MultiLineString",
        ogr.wkbPolygon: "Polygon",
        ogr.wkbMultiPolygon: "MultiPolygon",
        ogr.wkbCircularString: "LineString",
        ogr.wkbCompoundCurve: "LineString",
        ogr.wkbMultiCurve: "MultiLineString",
        ogr.wkbCurvePolygon: "Polygon",
        ogr.wkbMultiSurface: "MultiPolygon",
        ogr.wkbGeometryCollection: "GeometryCollection",
    }
    return names.get(geom_type, ogr.GeometryTypeToName(geom_type))


def to_geojson(geom: ogr.Geometry) -> dict[str, Any]:
    """Exact 2D GeoJSON for an OGR geometry (curves become lines)."""
    geom = geom.Clone()
    if geom.HasCurveGeometry():
        geom = geom.GetLinearGeometry()
    geom.FlattenTo2D()
    geojson: dict[str, Any] = json.loads(geom.ExportToJson(EXACT_JSON))
    return geojson


def from_geojson(geometry: dict[str, Any]) -> ogr.Geometry:
    return ogr.CreateGeometryFromJson(json.dumps(geometry))


def iter_features(
    path: str, fmt: str, layer_name: str, **kwargs: Any
) -> Iterator[tuple[int, dict[str, Any] | None, dict[str, Any], ogr.Geometry | None]]:
    """(row number, GeoJSON geometry or None, attributes, raw OGR geometry) per feature."""
    ds = open_dataset(path, fmt, **kwargs)
    layer = ds.GetLayerByName(layer_name)
    if layer is None:
        raise ValidationError(f"The file has no layer called {layer_name!r}.")
    defn = layer.GetLayerDefn()
    names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
    for row, feature in enumerate(layer, start=1):
        attrs = {}
        for i, name in enumerate(names):
            if not feature.IsFieldSetAndNotNull(i):
                attrs[name] = None
                continue
            field_type = defn.GetFieldDefn(i).GetType()
            if field_type in (ogr.OFTInteger, ogr.OFTInteger64):
                attrs[name] = feature.GetFieldAsInteger64(i)
            elif field_type == ogr.OFTReal:
                attrs[name] = feature.GetFieldAsDouble(i)
            elif field_type == ogr.OFTDate:
                year, month, day, *_ = feature.GetFieldAsDateTime(i)
                attrs[name] = f"{year:04d}-{month:02d}-{day:02d}"
            else:
                attrs[name] = feature.GetFieldAsString(i)
        geom = feature.GetGeometryRef()
        geom = geom.Clone() if geom is not None else None
        yield row, (to_geojson(geom) if geom is not None else None), attrs, geom


SAFE_NAME = re.compile(r"[^a-z0-9_]+")


def safe_field_name(name: str, taken: set[str]) -> str:
    """A schema-valid field name (lowercase, starts with a letter, unique)."""
    base = SAFE_NAME.sub("_", name.strip().lower()).strip("_") or "field"
    if not base[0].isalpha():
        base = f"f_{base}"
    base = base[:63]
    candidate, n = base, 2
    while candidate in taken:
        suffix = f"_{n}"
        candidate = base[: 63 - len(suffix)] + suffix
        n += 1
    taken.add(candidate)
    return candidate

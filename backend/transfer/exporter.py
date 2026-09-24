"""Runs an export job.

Plan: {"layer_ids": [..], "format": "gpkg", "crs": null | "EPSG:4326",
       "feature_ids": null | [..]  (a selection, single layer)}

Coordinates are written from geom_native. They're converted only when a target
CRS is chosen (or the format requires WGS 84: KML/KMZ), with the platform's
operation, which the README in the download names.
"""

import csv
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone
from osgeo import ogr, osr

from crs.models import CoordinateSystem
from crs.services import describe_operation, transform_geojson
from projects.models import Layer

from . import gdal_io
from .models import DataJob

DRIVERS = {
    "gpkg": ("GPKG", ".gpkg"),
    "shp": ("ESRI Shapefile", ".shp"),
    "geojson": ("GeoJSON", ".geojson"),
    "kml": ("LIBKML", ".kml"),
    "kmz": ("LIBKML", ".kmz"),
    "dxf": ("DXF", ".dxf"),
    "dwg": ("DXF", ".dxf"),  # written as DXF, then converted by LibreDWG
}
WGS84_ONLY = {"kml", "kmz"}
FIELD_TYPES = {
    "text": ogr.OFTString,
    "choice": ogr.OFTString,
    "integer": ogr.OFTInteger64,
    "decimal": ogr.OFTReal,
    "boolean": ogr.OFTInteger,
    "date": ogr.OFTDate,
}
GEOMETRY_TYPES = {
    "Point": ogr.wkbPoint,
    "MultiPoint": ogr.wkbMultiPoint,
    "LineString": ogr.wkbLineString,
    "MultiLineString": ogr.wkbMultiLineString,
    "Polygon": ogr.wkbPolygon,
    "MultiPolygon": ogr.wkbMultiPolygon,
}
MULTI = {"point": ogr.wkbMultiPoint, "line": ogr.wkbMultiLineString, "polygon": ogr.wkbMultiPolygon}


def _srs(system: CoordinateSystem) -> osr.SpatialReference:
    ref = osr.SpatialReference()
    if system.code.startswith("EPSG:"):
        ref.ImportFromEPSG(int(system.code.split(":")[1]))
    else:
        ref.ImportFromWkt(system.wkt)
    ref.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return ref


def _rows(
    layer: Layer, feature_ids: list[int] | None
) -> list[tuple[int, dict[str, Any] | None, dict[str, Any]]]:
    selection = " AND id = ANY(%s)" if feature_ids else ""
    # Only constant fragments are joined; values are bound parameters.
    sql = (
        "SELECT id, ST_AsGeoJSON(geom_native, 17), properties FROM projects_feature"  # noqa: S608
        f" WHERE layer_id = %s{selection} ORDER BY id"
    )
    params: list[Any] = [layer.pk] + ([feature_ids] if feature_ids else [])
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return [
            (
                fid,
                json.loads(g) if g else None,
                props if isinstance(props, dict) else json.loads(props),
            )
            for fid, g, props in cursor.fetchall()
        ]


def _short_names(schema: list[dict[str, Any]]) -> dict[str, str]:
    """Shapefile field names (max 10 characters, unique)."""
    taken: set[str] = set()
    result = {}
    for field in schema:
        base = field["name"][:10]
        name, n = base, 1
        while name.lower() in taken:
            suffix = str(n)
            name = base[: 10 - len(suffix)] + suffix
            n += 1
        taken.add(name.lower())
        result[field["name"]] = name
    return result


def _set_value(feature: ogr.Feature, index: int, field: dict[str, Any], value: Any) -> None:
    if value is None:
        feature.SetFieldNull(index)
    elif field["type"] == "boolean":
        feature.SetField(index, 1 if value else 0)
    elif field["type"] == "date":
        year, month, day = (int(p) for p in str(value).split("-"))
        feature.SetField(index, year, month, day, 0, 0, 0, 0)
    else:
        feature.SetField(index, value)


def write_layer(
    ds: ogr.DataSource, fmt: str, layer: Layer, rows: list[Any], target: CoordinateSystem, out: Path
) -> dict[str, Any]:
    convert = target.pk != layer.crs.pk
    geometries = []
    for _, geojson, _ in rows:
        if geojson is not None and convert:
            geojson, _ = transform_geojson(geojson, layer.crs, target)
        geometries.append(geojson)
    types = {g["type"] for g in geometries if g}
    geom_type = GEOMETRY_TYPES[types.pop()] if len(types) == 1 else MULTI[layer.geometry_type]
    options = []
    if fmt == "geojson":
        options = ["SIGNIFICANT_FIGURES=17", "RFC7946=NO"]
    if fmt == "shp":
        options = ["ENCODING=UTF-8"]
    name = "entities" if fmt in ("dxf", "dwg") else layer.name
    olayer = ds.GetLayerByName("entities") if fmt in ("dxf", "dwg") and ds.GetLayerCount() else None
    if olayer is None:
        olayer = ds.CreateLayer(
            name, _srs(target), geom_type if fmt not in ("dxf", "dwg") else ogr.wkbUnknown, options
        )
    short = (
        _short_names(layer.schema) if fmt == "shp" else {f["name"]: f["name"] for f in layer.schema}
    )
    if fmt not in ("dxf", "dwg"):
        for field in layer.schema:
            defn = ogr.FieldDefn(short[field["name"]], FIELD_TYPES[field["type"]])
            if field["type"] == "boolean":
                defn.SetSubType(ogr.OFSTBoolean)
            olayer.CreateField(defn)
    ldefn = olayer.GetLayerDefn()
    for (_fid, _geojson, props), geojson in zip(rows, geometries, strict=True):
        feature = ogr.Feature(ldefn)
        if geojson is not None:
            geom = gdal_io.from_geojson(geojson)
            if fmt == "shp" and ogr.GT_Flatten(geom.GetGeometryType()) != ogr.GT_Flatten(geom_type):
                geom = ogr.ForceTo(geom, geom_type)
            feature.SetGeometry(geom)
        if fmt in ("dxf", "dwg"):
            feature.SetField("Layer", layer.name)
        else:
            for field in layer.schema:
                _set_value(
                    feature,
                    ldefn.GetFieldIndex(short[field["name"]]),
                    field,
                    props.get(field["name"]),
                )
        olayer.CreateFeature(feature)
    if fmt == "shp":
        with open(out / f"{layer.name}_fields.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["shapefile_name", "full_name", "label", "type"])
            for field in layer.schema:
                writer.writerow(
                    [short[field["name"]], field["name"], field["label"], field["type"]]
                )
    return {
        "layer": layer.name,
        "features": len(rows),
        "crs": target.code,
        "converted": convert,
        "operation": describe_operation(layer.crs, target).name if convert else None,
        "accuracy_m": describe_operation(layer.crs, target).accuracy_m if convert else None,
    }


def run_export(job: DataJob, out: Path) -> tuple[Path, dict[str, Any]]:
    plan = job.plan
    fmt = plan["format"]
    if fmt not in DRIVERS:
        raise ValidationError(f"Unknown export format {fmt!r}.")
    if fmt == "dwg" and not gdal_io.dwg_available():
        raise ValidationError(
            "DWG export isn't available on this server (LibreDWG is not installed)."
        )
    layers = list(
        Layer.objects.filter(pk__in=plan["layer_ids"], project=job.project)
        .select_related("crs")
        .order_by("-order", "id")
    )
    if not layers:
        raise ValidationError("Choose at least one layer to export.")
    wgs84 = CoordinateSystem.objects.get(code="EPSG:4326")
    chosen = None
    if plan.get("crs"):
        chosen = CoordinateSystem.objects.filter(code=plan["crs"].upper(), is_active=True).first()
        if chosen is None:
            raise ValidationError(f"Coordinate system {plan['crs']!r} isn't available.")
    feature_ids = plan.get("feature_ids") or None
    if feature_ids and len(layers) != 1:
        raise ValidationError("A selection can only be exported from one layer.")

    driver_name, ext = DRIVERS[fmt]
    driver = ogr.GetDriverByName(driver_name)
    folder = out / "export"
    folder.mkdir(parents=True, exist_ok=True)
    summaries = []
    shared = None
    if fmt in ("gpkg", "dxf", "dwg", "kmz", "kml"):
        shared = driver.CreateDataSource(str(folder / f"{job.project.name}{ext}"))
    for layer in layers:
        target = wgs84 if fmt in WGS84_ONLY else (chosen or layer.crs)
        ds = shared or driver.CreateDataSource(str(folder / f"{layer.name}{ext}"))
        summaries.append(write_layer(ds, fmt, layer, _rows(layer, feature_ids), target, folder))
        if shared is None:
            ds = None
    shared = None  # flush
    if fmt == "dwg":
        dxf = folder / f"{job.project.name}.dxf"
        dwg = dxf.with_suffix(".dwg")
        result = subprocess.run(  # noqa: S603 - fixed tool, our own paths
            ["dxf2dwg", "-y", "-o", str(dwg), str(dxf)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0 or not dwg.exists():
            raise ValidationError(f"DWG conversion failed: {result.stderr.strip()[:300]}")
        dxf.unlink()
    _readme(folder, job, fmt, summaries)
    archive = out / f"{job.project.name}-{fmt}-{timezone.now():%Y%m%d-%H%M}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(folder.iterdir()):
            zf.write(item, item.name)
    shutil.rmtree(folder)
    return archive, {"layers": summaries}


def _readme(folder: Path, job: DataJob, fmt: str, summaries: list[dict[str, Any]]) -> None:
    lines = [
        f"Export of project: {job.project.name}",
        f"Date: {timezone.now():%Y-%m-%d %H:%M} ({timezone.get_current_timezone_name()})",
        f"Format: {fmt}",
        "",
    ]
    for s in summaries:
        lines.append(f"- {s['layer']}: {s['features']} features, CRS {s['crs']}")
        if s["converted"]:
            accuracy = (
                f"±{s['accuracy_m']} m" if s["accuracy_m"] is not None else "accuracy unknown"
            )
            lines.append(
                f"  converted from the layer's own CRS using {s['operation']} ({accuracy})"
            )
    if fmt == "shp":
        lines += [
            "",
            "Shapefile field names are limited to 10 characters;"
            " <layer>_fields.csv lists the full names.",
        ]
    if fmt in ("dxf", "dwg"):
        lines += ["", "CAD formats keep geometry and layer names only, not attribute values."]
    if fmt in WGS84_ONLY:
        lines += ["", "KML/KMZ always use WGS 84 (EPSG:4326)."]
    (folder / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

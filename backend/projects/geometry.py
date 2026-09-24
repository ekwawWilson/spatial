"""The only code that reads or writes feature.geom_native.

Coordinates of record are written exactly as received (GeoJSON in the layer's
native CRS) and read back exactly; nothing here reprojects them. geom_4326 is
derived with crs.services, the same operation the conversion API and the web
map use, so every view of a feature agrees.
"""

import json
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from crs.models import CoordinateSystem
from crs.services import transform_geojson

from .models import ACCEPTED_GEOJSON_TYPES, Feature, Layer

# ST_AsGeoJSON writes the shortest decimal that round-trips a double, up to
# this many decimals: enough to return exactly what was stored.
GEOJSON_DECIMALS = 15
MAX_VERTICES = 100_000


def _wgs84() -> CoordinateSystem:
    return CoordinateSystem.objects.get(code="EPSG:4326")


def _count_positions(coords: Any) -> int:
    if not isinstance(coords, list) or not coords:
        raise TypeError("coordinates must be non-empty nested lists")
    if isinstance(coords[0], int | float):
        if len(coords) < 2 or not all(isinstance(v, int | float) for v in coords):
            raise TypeError("a position needs at least two numbers")
        return 1
    return sum(_count_positions(c) for c in coords)


def check_geometry(geometry: Any, layer: Layer) -> dict[str, Any]:
    """Validates a GeoJSON geometry for a layer; returns it unchanged.

    Checks: GeoJSON shape, a type the layer accepts, a size limit, and PostGIS
    validity (with the reason when invalid, e.g. a self-intersecting ring).
    """
    if not isinstance(geometry, dict) or "type" not in geometry or "coordinates" not in geometry:
        raise ValidationError(
            {"geometry": ["must be a GeoJSON geometry with type and coordinates"]}
        )
    accepted = ACCEPTED_GEOJSON_TYPES[layer.geometry_type]
    if geometry["type"] not in accepted:
        raise ValidationError(
            {
                "geometry": [
                    f"this is a {layer.geometry_type} layer; "
                    f"expected {' or '.join(sorted(accepted))}"
                ]
            }
        )
    try:
        vertices = _count_positions(geometry["coordinates"])
    except (TypeError, IndexError):
        raise ValidationError({"geometry": ["coordinates are malformed"]}) from None
    if vertices > MAX_VERTICES:
        raise ValidationError({"geometry": [f"has more than {MAX_VERTICES} vertices"]})
    try:
        # Savepoint: a PostGIS parse error would otherwise abort the request's
        # whole transaction.
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "SELECT ST_IsValid(g), ST_IsValidReason(g), ST_IsEmpty(g)"
                " FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), %s) AS g) s",
                [json.dumps(geometry), layer.crs.srid],
            )
            valid, reason, empty = cursor.fetchone()
    except DatabaseError as exc:
        raise ValidationError({"geometry": [f"could not be read: {exc}"]}) from exc
    if empty:
        raise ValidationError({"geometry": ["is empty"]})
    if not valid:
        raise ValidationError({"geometry": [f"is invalid: {reason}"]})
    return geometry


def write_geometry(feature: Feature, geometry: dict[str, Any] | None) -> None:
    """Stores a feature's native geometry (already checked) and its WGS 84 copy."""
    layer = feature.layer
    if geometry is None:
        native_json = wgs_json = None
    else:
        wgs, _ = transform_geojson(geometry, layer.crs, _wgs84())
        native_json, wgs_json = json.dumps(geometry), json.dumps(wgs)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE projects_feature SET"
            " geom_native = ST_SetSRID(ST_GeomFromGeoJSON(%s), %s),"
            " geom_4326 = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)"
            " WHERE id = %s",
            [native_json, layer.crs.srid, wgs_json, feature.pk],
        )


def read_geometries(
    feature_ids: Iterable[int], *, native: bool
) -> dict[int, dict[str, Any] | None]:
    """GeoJSON geometries by feature id, native (exact) or WGS 84."""
    ids = list(feature_ids)
    if not ids:
        return {}
    column = "geom_native" if native else "geom_4326"
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, ST_AsGeoJSON({column}, %s) FROM projects_feature WHERE id = ANY(%s)",  # noqa: S608 - column is a constant
            [GEOJSON_DECIMALS, ids],
        )
        return {fid: json.loads(text) if text else None for fid, text in cursor.fetchall()}


def extent(layer: Layer) -> dict[str, list[float] | None]:
    """Bounding boxes of a layer's features: native units and WGS 84 degrees."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_XMin(n), ST_YMin(n), ST_XMax(n), ST_YMax(n),"
            " ST_XMin(w), ST_YMin(w), ST_XMax(w), ST_YMax(w)"
            " FROM (SELECT ST_Extent(geom_native) n, ST_Extent(geom_4326) w"
            " FROM projects_feature WHERE layer_id = %s) s",
            [layer.pk],
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return {"native": None, "wgs84": None}
    return {"native": list(row[:4]), "wgs84": list(row[4:])}


def recompute_wgs84(layer: Layer) -> int:
    """Re-derives geom_4326 for every feature of a layer (after the operation
    between its CRS and WGS 84 changes). geom_native is not touched."""
    geometries = read_geometries(
        Feature.objects.filter(layer=layer).values_list("id", flat=True), native=True
    )
    for feature_id, geometry in geometries.items():
        feature = Feature(pk=feature_id, layer=layer)
        write_geometry(feature, geometry)
    return len(geometries)

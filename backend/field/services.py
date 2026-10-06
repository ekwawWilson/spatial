"""The field package: what the mobile app downloads to work offline.

A package holds the chosen layers of one project (definitions, forms and the
features inside the planning area), the planning area itself, and the
project's coordinate system so the device can show positions in it.

Feature geometry is sent in WGS 84, which is what the device's map and GPS
use. The coordinates of record stay on the server: captured positions come
back as WGS 84 and are converted there (Phase 10), never on the device.
"""

import json
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone

from basemaps.models import BasemapSource
from crs.services import web_proj4
from projects import privacy
from projects.models import Layer, PlanProject

PACKAGE_FORMAT = 1
MAX_FEATURES = 50_000
DECIMALS = 9  # about 0.1 mm in degrees: display precision for the device


def boundary_geojson(project: PlanProject) -> dict[str, Any] | None:
    if project.boundary_feature_id is None:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsGeoJSON(geom_4326, %s) FROM projects_feature WHERE id = %s",
            [DECIMALS, project.boundary_feature_id],
        )
        row = cursor.fetchone()
    return json.loads(row[0]) if row and row[0] else None


def boundary_bbox(project: PlanProject) -> list[float] | None:
    """[west, south, east, north] of the planning area in degrees."""
    if project.boundary_feature_id is None:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g) FROM"
            " (SELECT geom_4326 AS g FROM projects_feature WHERE id = %s) s",
            [project.boundary_feature_id],
        )
        row = cursor.fetchone()
    return list(row) if row and row[0] is not None else None


def _features(layer: Layer, boundary_id: int | None) -> list[dict[str, Any]]:
    """The layer's features, limited to those touching the planning area when
    there is one. Features are sent whole (never cut at the boundary), so what
    comes back from the field is the same feature."""
    inside = ""
    params: list[Any] = [DECIMALS, layer.pk]
    if boundary_id is not None:
        inside = (
            " AND ST_Intersects(f.geom_4326,"
            " (SELECT geom_4326 FROM projects_feature WHERE id = %s))"
        )
        params.append(boundary_id)
    # Only constant fragments are joined; values are bound parameters.
    sql = (
        "SELECT f.id, f.uuid, f.version, f.verified, f.properties,"  # noqa: S608
        " ST_AsGeoJSON(f.geom_4326, %s) FROM projects_feature f"
        f" WHERE f.layer_id = %s AND f.geom_4326 IS NOT NULL{inside} ORDER BY f.id"
    )
    # Restricted (personal) values don't go to devices whose user can't see them.
    hidden = privacy.hidden_fields(layer)
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return [
            {
                "id": fid,
                "uuid": str(uuid),
                "version": version,
                "verified": verified,
                "properties": privacy.redact(
                    props if isinstance(props, dict) else json.loads(props), hidden
                ),
                "geometry": json.loads(geometry),
            }
            for fid, uuid, version, verified, props, geometry in cursor.fetchall()
        ]


def offline_basemaps() -> list[dict[str, Any]]:
    """Basemaps whose terms allow storing tiles on a device. No provider
    preset does; a district's own tiles (e.g. drone imagery) can."""
    return [
        {
            "id": source.pk,
            "name": source.name,
            "attribution": source.attribution,
            "min_zoom": source.min_zoom,
            "max_zoom": source.max_zoom,
        }
        for source in BasemapSource.objects.filter(
            is_active=True, offline_cache_allowed=True, kind=BasemapSource.Kind.XYZ
        ).order_by("order", "id")
    ]


def build_package(project: PlanProject, layer_ids: list[int] | None) -> dict[str, Any]:
    """The package for a project. `layer_ids`: the chosen layers (None: all)."""
    layers = list(project.layers.select_related("crs").order_by("-order", "id"))
    if layer_ids is not None:
        known = {layer.pk for layer in layers}
        unknown = sorted(set(layer_ids) - known)
        if unknown:
            raise ValidationError({"layers": [f"Not layers of this project: {unknown}."]})
        layers = [layer for layer in layers if layer.pk in set(layer_ids)]
    boundary = boundary_geojson(project)
    boundary_id = project.boundary_feature_id if boundary else None

    layer_rows = []
    features: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for layer in layers:
        rows = _features(layer, boundary_id)
        total += len(rows)
        if total > MAX_FEATURES:
            raise ValidationError(
                {
                    "layers": [
                        f"These layers hold more than {MAX_FEATURES:,} features inside the"
                        " planning area. Choose fewer layers for the field."
                    ]
                }
            )
        features[str(layer.pk)] = rows
        layer_rows.append(
            {
                "id": layer.pk,
                "name": layer.name,
                "domain": layer.domain,
                "geometry_type": layer.geometry_type,
                "schema": privacy.visible_schema(layer),
                "style": layer.style,
                "order": layer.order,
                "feature_count": len(rows),
            }
        )
    crs = project.crs
    return {
        "format": PACKAGE_FORMAT,
        "generated_at": timezone.now().isoformat(),
        "project": {
            "id": project.pk,
            "name": project.name,
            "community": project.community,
            "district": project.district_id,
            "boundary": boundary,
            "boundary_status": project.boundary_status,
            "bbox": boundary_bbox(project) if boundary else None,
            "crs": {
                "code": crs.code,
                "name": crs.name,
                "kind": crs.kind,
                "units": crs.units,
                "unit_to_metre": crs.unit_to_metre,
                # The same definition the web map uses, so positions shown on
                # the device agree with the server's conversion.
                "proj4": web_proj4(crs),
            },
        },
        "layers": layer_rows,
        "features": features,
        "feature_total": total,
        "clipped_to_boundary": boundary is not None,
        "offline_basemaps": offline_basemaps(),
    }

"""Editing operations beyond simple create/update: history, restore, split,
merge. All geometry work happens on geom_native, in the layer's own CRS."""

import json
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection

from core.models import AuditLog, User

from . import geometry as geo
from .models import ACCEPTED_GEOJSON_TYPES, Feature, Layer


def history(feature: Feature) -> list[dict[str, Any]]:
    """Every recorded version of a feature, newest first, with its geometry
    (native CRS) and properties as they were, and who changed it when.

    A save writes the row and then its exact geometry (two audit records with
    the same version number); they are one version here, shown with the
    complete state after the geometry write and restored from it."""
    records = list(
        AuditLog.objects.filter(table_name="projects_feature", row_id=str(feature.pk)).order_by(
            "id"
        )
    )
    versions: list[tuple[AuditLog, AuditLog, set[str]]] = []  # (first, last, changed)
    for record in records:
        number = (record.after or record.before or {}).get("version")
        previous = versions[-1] if versions else None
        if (
            previous is not None
            and record.action == "UPDATE"
            and previous[1].action != "DELETE"
            and (previous[1].after or {}).get("version") == number
        ):
            versions[-1] = (previous[0], record, previous[2] | set(record.changed_fields()))
        else:
            versions.append((record, record, set(record.changed_fields())))
    versions.reverse()
    emails = dict(
        User.objects.filter(
            id__in={first.user_id for first, _, _ in versions if first.user_id}
        ).values_list("id", "email")
    )
    geometries: dict[int, Any] = {}
    with connection.cursor() as cursor:
        for _, last, _ in versions:
            hexwkb = (last.after or {}).get("geom_native")
            if hexwkb:
                cursor.execute("SELECT ST_AsGeoJSON(%s::geometry, 17)", [hexwkb])
                geometries[last.pk] = json.loads(cursor.fetchone()[0])
    return [
        {
            "audit_id": last.pk,
            "version": (last.after or last.before or {}).get("version"),
            "action": first.action,
            "at": first.occurred_at.isoformat(),
            "user_email": emails.get(first.user_id) if first.user_id else None,
            "changed_fields": sorted(f for f in changed if f not in ("updated_at", "version")),
            "properties": (last.after or {}).get("properties"),
            "geometry": geometries.get(last.pk),
        }
        for first, last, changed in versions
    ]


def restore(feature: Feature, audit_id: int, user: User) -> Feature:
    """Makes an earlier version current again (as a new version, so the
    history keeps everything)."""
    entry = AuditLog.objects.filter(
        pk=audit_id, table_name="projects_feature", row_id=str(feature.pk)
    ).first()
    if entry is None or not entry.after:
        raise ValidationError("That version doesn't exist for this feature.")
    geometry = None
    if entry.after.get("geom_native"):
        with connection.cursor() as cursor:
            cursor.execute("SELECT ST_AsGeoJSON(%s::geometry, 17)", [entry.after["geom_native"]])
            geometry = json.loads(cursor.fetchone()[0])
    feature.properties = entry.after.get("properties") or {}
    feature.version += 1
    feature.updated_by = user
    feature.save(update_fields=["properties", "version", "updated_by", "updated_at"])
    geo.write_geometry(feature, geometry)
    return feature


def split(feature: Feature, blade: dict[str, Any], user: User) -> list[Feature]:
    """Cuts a line or polygon with a line (in the layer's CRS). The original
    keeps the first piece; the others become new features with the same
    properties. Returns all pieces."""
    layer = feature.layer
    if layer.geometry_type == "point":
        raise ValidationError("Points can't be split.")
    if blade.get("type") != "LineString":
        raise ValidationError({"blade": ["must be a GeoJSON LineString"]})
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsGeoJSON((ST_Dump(ST_Split(geom_native,"
            " ST_SetSRID(ST_GeomFromGeoJSON(%s), %s)))).geom, 17)"
            " FROM projects_feature WHERE id = %s",
            [json.dumps(blade), layer.crs.srid, feature.pk],
        )
        pieces = [json.loads(row[0]) for row in cursor.fetchall()]
    if len(pieces) < 2:
        raise ValidationError("The line doesn't cut this feature into pieces.")
    first, *rest = pieces
    feature.version += 1
    feature.updated_by = user
    feature.save(update_fields=["version", "updated_by", "updated_at"])
    geo.write_geometry(feature, first)
    created = [feature]
    for piece in rest:
        new = Feature.objects.create(
            district_id=feature.district_id,
            layer=layer,
            properties=dict(feature.properties),
            origin=Feature.Origin.DRAWN,
            created_by=user,
            updated_by=user,
        )
        geo.write_geometry(new, piece)
        created.append(new)
    return created


def merge(features: list[Feature], keep: Feature, user: User) -> Feature:
    """Unites features of one layer into `keep` (whose properties stay); the
    others are deleted (their history stays in the audit log). Only touching or
    overlapping features can be merged, so a merge never silently creates a
    multi-part feature out of scattered pieces."""
    if len(features) < 2:
        raise ValidationError("Choose at least two features to merge.")
    layer_ids = {f.layer_id for f in features}
    if len(layer_ids) != 1:
        raise ValidationError("Only features of the same layer can be merged.")
    layer: Layer = features[0].layer
    ids = [f.pk for f in features]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsGeoJSON(ST_UnaryUnion(ST_Collect(geom_native)), 17),"
            " ST_NumGeometries(ST_UnaryUnion(ST_Collect(geom_native)))"
            " FROM projects_feature WHERE id = ANY(%s)",
            [ids],
        )
        merged_json, parts = cursor.fetchone()
    if merged_json is None:
        raise ValidationError("These features have no geometry to merge.")
    merged = json.loads(merged_json)
    if parts > 1 and layer.geometry_type != "point":
        raise ValidationError(
            "These features don't touch, so merging them would create a multi-part shape."
        )
    if merged["type"] not in ACCEPTED_GEOJSON_TYPES[layer.geometry_type]:
        raise ValidationError(
            f"The merged shape is a {merged['type']}, which doesn't fit this layer."
        )
    keep.version += 1
    keep.updated_by = user
    keep.save(update_fields=["version", "updated_by", "updated_at"])
    geo.write_geometry(keep, merged)
    Feature.objects.filter(pk__in=[i for i in ids if i != keep.pk]).delete()
    return keep

"""Applying what devices send, and working out what to send back.

Rules:
* Devices send positions in WGS 84. They are converted to the layer's CRS
  here, with the platform's operation: coordinates of record are never
  computed on a device.
* A change is applied once. Sending it again (a retry after a lost reply)
  returns the first result and changes nothing.
* An edit based on an older version than the server's is not applied. It goes
  to the conflict queue for a person to resolve.
"""

import json
import uuid as uuid_module
from datetime import UTC, datetime, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import User
from crs.models import CoordinateSystem
from crs.services import transform_geojson
from field.services import DECIMALS
from projects import geometry as geo
from projects import schema as schema_rules
from projects.boundary import LAYER_NAME as BOUNDARY_LAYER
from projects.models import Feature, Layer, PlanProject

from .models import AppliedChange, Capture, Conflict, FieldTask, Tombstone

# Pulls look back a little before "since", so a change committed just after
# the last pull's timestamp was taken is never missed. Applying a feature
# twice on the device is harmless.
PULL_OVERLAP = timedelta(seconds=10)
MAX_CHANGES = 500


def _wgs84() -> CoordinateSystem:
    return CoordinateSystem.objects.get(code="EPSG:4326")


def _messages(exc: ValidationError) -> list[str]:
    if hasattr(exc, "error_dict"):
        return [f"{field}: {'; '.join(msgs)}" for field, msgs in exc.message_dict.items()]
    return list(exc.messages)


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = parse_datetime(value)
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, UTC)
    return parsed


def _native(geometry: dict[str, Any], layer: Layer) -> dict[str, Any]:
    """A device's WGS 84 geometry in the layer's CRS, checked for the layer."""
    if not isinstance(geometry, dict) or "coordinates" not in geometry:
        raise ValidationError({"geometry": ["must be a GeoJSON geometry"]})
    converted, _ = transform_geojson(geometry, _wgs84(), layer.crs)
    geo.check_geometry(converted, layer)
    return converted


def _record_capture(feature: Feature, change: dict[str, Any], device_id: str, user: User) -> None:
    capture = change.get("capture") or {}
    method = capture.get("method") or ""
    Capture.objects.create(
        district_id=feature.district_id,
        feature=feature,
        feature_version=feature.version,
        method=method if method in Capture.Method.values else "",
        accuracy_m=capture.get("accuracy_m"),
        fix_time=_when(capture.get("fix_time")),
        readings=capture.get("readings"),
        captured_at=_when(capture.get("captured_at")),
        captured_by=user,
        device_id=device_id,
        notes=str(capture.get("notes") or "")[:5000],
    )


def _feature_result(feature: Feature) -> dict[str, Any]:
    return {"id": feature.pk, "uuid": str(feature.uuid), "version": feature.version}


def _create(change: dict[str, Any], district_id: int, device_id: str, user: User) -> dict[str, Any]:
    feature_uuid = uuid_module.UUID(str(change["feature_uuid"]))
    existing = Feature.objects.filter(uuid=feature_uuid, district_id=district_id).first()
    if existing is not None:
        # The same capture arriving under a new change id: already here.
        return {"status": "applied", "feature": _feature_result(existing), "duplicate": True}
    layer = (
        Layer.objects.select_related("crs")
        .filter(pk=change.get("layer"), district_id=district_id)
        .first()
    )
    if layer is None:
        raise ValidationError({"layer": ["isn't a layer of this district"]})
    if layer.name == BOUNDARY_LAYER:
        raise ValidationError({"layer": ["the planning area is set in the office"]})
    geometry = _native(change.get("geometry") or {}, layer)
    properties = schema_rules.validate_properties(layer.schema, change.get("properties") or {})
    feature = Feature.objects.create(
        district_id=district_id,
        layer=layer,
        uuid=feature_uuid,
        properties=properties,
        origin=Feature.Origin.FIELD,
        created_by=user,
        updated_by=user,
    )
    geo.write_geometry(feature, geometry)
    _record_capture(feature, change, device_id, user)
    return {"status": "applied", "feature": _feature_result(feature)}


def _update(change: dict[str, Any], district_id: int, device_id: str, user: User) -> dict[str, Any]:
    feature = (
        Feature.objects.select_for_update(of=("self",))
        .select_related("layer", "layer__crs", "layer__project")
        .filter(uuid=change["feature_uuid"], district_id=district_id)
        .first()
    )
    if feature is None:
        raise ValidationError({"feature_uuid": ["this feature no longer exists on the server"]})
    layer = feature.layer
    base = change.get("base_version")
    if not isinstance(base, int):
        raise ValidationError({"base_version": ["is required for an edit"]})
    has_geometry = change.get("geometry") is not None
    properties = change.get("properties")
    if feature.version != base:
        conflict = Conflict.objects.create(
            district_id=district_id,
            project=layer.project,
            feature=feature,
            change_id=change["change_id"],
            device_id=device_id,
            submitted_by=user,
            base_version=base,
            server_version=feature.version,
            field_properties=properties if isinstance(properties, dict) else None,
            field_geometry=change.get("geometry") if has_geometry else None,
            capture=change.get("capture") or {},
        )
        return {"status": "conflict", "conflict": conflict.pk, "feature": _feature_result(feature)}
    if layer.project.boundary_feature_id == feature.pk:
        raise ValidationError({"feature_uuid": ["the planning area is changed in the office"]})
    geometry = _native(change["geometry"], layer) if has_geometry else None
    if isinstance(properties, dict):
        changes = schema_rules.validate_properties(layer.schema, properties, partial=True)
        feature.properties = {**feature.properties, **changes}
    feature.version += 1
    feature.updated_by = user
    feature.save(update_fields=["properties", "version", "updated_by", "updated_at"])
    if geometry is not None:
        geo.write_geometry(feature, geometry)
    _record_capture(feature, change, device_id, user)
    return {"status": "applied", "feature": _feature_result(feature)}


def _task(change: dict[str, Any], district_id: int, user: User) -> dict[str, Any]:
    payload = change.get("task") or {}
    task = (
        FieldTask.objects.select_for_update(of=("self",))
        .select_related("feature")
        .filter(pk=payload.get("id"), district_id=district_id)
        .first()
    )
    if task is None:
        raise ValidationError({"task": ["this task no longer exists"]})
    outcome = payload.get("outcome")
    if outcome not in FieldTask.Outcome.values:
        raise ValidationError({"task": ["outcome must be confirmed, corrected or not_found"]})
    if task.status == FieldTask.Status.DONE:
        return {"status": "applied", "task": task.pk, "duplicate": True}
    complete_task(task, outcome, str(payload.get("notes") or ""), user)
    return {"status": "applied", "task": task.pk, "feature": _feature_result(task.feature)}


def complete_task(task: FieldTask, outcome: str, notes: str, user: User) -> None:
    """Records what the officer found. Confirmed and corrected features become
    verified; a feature that wasn't found is left as it is, for the office."""
    task.status = FieldTask.Status.DONE
    task.outcome = outcome
    task.notes = notes[:5000]
    task.completed_by = user
    task.completed_at = timezone.now()
    task.save()
    if outcome in (FieldTask.Outcome.CONFIRMED, FieldTask.Outcome.CORRECTED):
        # updated_at moves so devices pull the new flag; the version doesn't
        # (the data itself didn't change), so pending edits don't conflict.
        Feature.objects.filter(pk=task.feature_id).update(verified=True, updated_at=timezone.now())


def apply_change(change: Any, district_id: int, device_id: str, user: User) -> dict[str, Any]:
    """Applies one change in its own savepoint. Never raises for bad input:
    the result says what happened."""
    if not isinstance(change, dict):
        return {"change_id": None, "status": "rejected", "errors": ["A change must be an object."]}
    raw_id = change.get("change_id")
    try:
        change_id = uuid_module.UUID(str(raw_id))
    except ValueError:
        return {"change_id": raw_id, "status": "rejected", "errors": ["change_id must be a UUID."]}
    done = AppliedChange.objects.filter(change_id=change_id).first()
    if done is not None:
        return {**done.result, "change_id": str(change_id), "repeat": True}
    change = {**change, "change_id": change_id}
    op = change.get("op")
    try:
        with transaction.atomic():
            if op == "create":
                result = _create(change, district_id, device_id, user)
            elif op == "update":
                result = _update(change, district_id, device_id, user)
            elif op == "task":
                result = _task(change, district_id, user)
            else:
                raise ValidationError({"op": ["must be create, update or task"]})
            result["change_id"] = str(change_id)
            AppliedChange.objects.create(
                district_id=district_id,
                change_id=change_id,
                device_id=device_id,
                user=user,
                result=result,
            )
        return result
    except ValidationError as exc:
        # Not recorded: the device may send a corrected change under the same id.
        return {"change_id": str(change_id), "status": "rejected", "errors": _messages(exc)}
    except (KeyError, ValueError, TypeError) as exc:
        return {"change_id": str(change_id), "status": "rejected", "errors": [f"Malformed: {exc}"]}
    except IntegrityError:
        # Two requests carried the same change at once; the other one won.
        done = AppliedChange.objects.filter(change_id=change_id).first()
        if done is not None:
            return {**done.result, "change_id": str(change_id), "repeat": True}
        return {
            "change_id": str(change_id),
            "status": "rejected",
            "errors": ["Could not be saved; try again."],
        }


# --- Pull ------------------------------------------------------------------------------------


def task_json(task: FieldTask) -> dict[str, Any]:
    return {
        "id": task.pk,
        "feature_uuid": str(task.feature.uuid),
        "layer": task.feature.layer_id,
        "status": task.status,
        "outcome": task.outcome,
        "item": task.item.title if task.item else "",
    }


def pull(project: PlanProject, layer_ids: list[int], since: datetime | None) -> dict[str, Any]:
    """What changed on the server for these layers since `since` (everything
    when None): features to add or replace, features to remove, and tasks."""
    now = timezone.now()
    layers = (
        list(project.layers.filter(pk__in=layer_ids)) if layer_ids else list(project.layers.all())
    )
    ids = [layer.pk for layer in layers]
    cutoff = since - PULL_OVERLAP if since else None
    boundary_id = project.boundary_feature_id

    conditions = ["f.layer_id = ANY(%s)", "f.geom_4326 IS NOT NULL"]
    params: list[Any] = [DECIMALS, ids]
    if cutoff:
        conditions.append("f.updated_at > %s")
        params.append(cutoff)
    if boundary_id:
        conditions.append(
            "ST_Intersects(f.geom_4326, (SELECT geom_4326 FROM projects_feature WHERE id = %s))"
        )
        params.append(boundary_id)
    # Only constant fragments are joined; values are bound parameters.
    sql = (
        "SELECT f.id, f.uuid, f.layer_id, f.version, f.verified, f.properties,"  # noqa: S608
        " ST_AsGeoJSON(f.geom_4326, %s) FROM projects_feature f WHERE "
        + " AND ".join(conditions)
        + " ORDER BY f.id"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        features = [
            {
                "id": fid,
                "uuid": str(uuid),
                "layer": layer_id,
                "version": version,
                "verified": verified,
                "properties": props if isinstance(props, dict) else json.loads(props),
                "geometry": json.loads(geometry),
            }
            for fid, uuid, layer_id, version, verified, props, geometry in cursor.fetchall()
        ]
    deleted: list[str] = []
    if cutoff:
        deleted = [
            str(u)
            for u in Tombstone.objects.filter(layer_id__in=ids, deleted_at__gt=cutoff).values_list(
                "feature_uuid", flat=True
            )
        ]
    tasks = FieldTask.objects.filter(project=project, feature__layer_id__in=ids).select_related(
        "feature", "item"
    )
    if cutoff:
        tasks = tasks.filter(updated_at__gt=cutoff)
    else:
        tasks = tasks.filter(status=FieldTask.Status.OPEN)
    return {
        "server_time": now.isoformat(),
        "full": cutoff is None,
        "layers": [
            {
                "id": layer.pk,
                "name": layer.name,
                "domain": layer.domain,
                "geometry_type": layer.geometry_type,
                "schema": layer.schema,
                "style": layer.style,
                "order": layer.order,
            }
            for layer in layers
        ],
        "features": features,
        "deleted": deleted,
        "tasks": [task_json(task) for task in tasks],
    }


# --- Conflicts -------------------------------------------------------------------------------


def resolve_conflict(
    conflict: Conflict,
    resolution: str,
    user: User,
    *,
    properties: dict[str, Any] | None = None,
    use_field_geometry: bool | None = None,
) -> Feature:
    """Settles a conflict.

    keep_office: the server's version stands. keep_field: the device's values
    replace it. merged: `properties` holds the chosen value per field, and
    `use_field_geometry` says whose shape to keep. Whatever is written becomes
    a new version, so history keeps both sides."""
    if conflict.status != Conflict.Status.OPEN:
        raise ValidationError("This conflict is already resolved.")
    feature = (
        Feature.objects.select_for_update(of=("self",))
        .select_related("layer", "layer__crs")
        .get(pk=conflict.feature_id)
    )
    layer = feature.layer
    new_properties: dict[str, Any] | None = None
    new_geometry: dict[str, Any] | None = None
    if resolution == Conflict.Resolution.KEEP_FIELD:
        new_properties = conflict.field_properties
        if conflict.field_geometry is not None:
            new_geometry = _native(conflict.field_geometry, layer)
    elif resolution == Conflict.Resolution.MERGED:
        if properties is None:
            raise ValidationError({"properties": ["Choose a value for each field."]})
        new_properties = properties
        if use_field_geometry:
            if conflict.field_geometry is None:
                raise ValidationError({"geometry": ["The device didn't change the shape."]})
            new_geometry = _native(conflict.field_geometry, layer)
    elif resolution != Conflict.Resolution.KEEP_OFFICE:
        raise ValidationError({"resolution": ["must be keep_field, keep_office or merged"]})

    if new_properties is not None or new_geometry is not None:
        if new_properties is not None:
            changes = schema_rules.validate_properties(layer.schema, new_properties, partial=True)
            feature.properties = {**feature.properties, **changes}
        feature.version += 1
        feature.updated_by = user
        feature.save(update_fields=["properties", "version", "updated_by", "updated_at"])
        if new_geometry is not None:
            geo.write_geometry(feature, new_geometry)
    conflict.status = Conflict.Status.RESOLVED
    conflict.resolution = resolution
    conflict.resolved_by = user
    conflict.resolved_at = timezone.now()
    conflict.save()
    return feature


# --- Ground-truthing --------------------------------------------------------------------------


def send_layer_to_field(layer: Layer, item: Any, user: User) -> dict[str, int]:
    """Makes a task for every feature of the layer that isn't verified and
    doesn't already have an open task."""
    busy = set(
        FieldTask.objects.filter(feature__layer=layer, status=FieldTask.Status.OPEN).values_list(
            "feature_id", flat=True
        )
    )
    features = Feature.objects.filter(layer=layer, verified=False).exclude(pk__in=busy)
    tasks = [
        FieldTask(
            district_id=layer.district_id,
            project_id=layer.project_id,
            item=item,
            feature=feature,
            created_by=user,
        )
        for feature in features
    ]
    FieldTask.objects.bulk_create(tasks)
    return {
        "created": len(tasks),
        "already_open": len(busy),
        "verified": Feature.objects.filter(layer=layer, verified=True).count(),
    }

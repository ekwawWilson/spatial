"""Runs an import job according to its plan.

Plan (job.plan), one entry per source layer to import:
    {"layers": [{
        "source": "parcels",                    # layer name in the file
        "crs": "EPSG:2136",                     # CRS of the file's coordinates
        "target_layer": 12,                     # existing layer, or
        "new_layer": {"name": "Parcels", "domain": "B", "geometry_type": "polygon"},
        "fields": [{"source": "PROPERTY_I", "target": "property_id", "type": "text"}],
        "invalid_geometry": "fix" | "skip" | "abort",
        "duplicates": "keep" | "skip",
        "bad_values": "blank" | "skip_feature",
        "cad_layers": ["parcels"],              # DXF/DWG only: which CAD layers
        "encoding": "CP1252"                    # optional override (shapefiles)
    }]}

Everything runs in one transaction: a failure or "abort" leaves nothing half
imported. Coordinates are only converted when the target layer's CRS differs
from the file's, with the platform's operation, which the report names.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction

from crs.models import CoordinateSystem
from crs.services import transform_geojson
from projects import geometry as geo
from projects import schema as schema_rules
from projects import styles
from projects.models import Feature, Layer

from . import gdal_io
from .models import DataJob

PROGRESS_EVERY = 250
MAX_REPORTED_ROWS = 200


class ImportAborted(Exception):
    pass


def progress_key(job: DataJob) -> str:
    return f"transfer-progress:{job.uuid}"


def set_progress(job: DataJob, done: int, total: int, stage: str) -> None:
    # In the cache, not the job row: the import runs in one transaction, so
    # row updates wouldn't be visible to anyone polling until the very end.
    cache.set(progress_key(job), {"done": done, "total": total, "stage": stage}, 24 * 3600)


def _system(code: str) -> CoordinateSystem:
    system = CoordinateSystem.objects.filter(code=code.strip().upper(), is_active=True).first()
    if system is None:
        raise ValidationError(f"Coordinate system {code!r} isn't available in this district.")
    return system


class Report:
    def __init__(self, source: str, target: Layer) -> None:
        self.data: dict[str, Any] = {
            "source": source,
            "target_layer": target.pk,
            "target_name": target.name,
            "imported": 0,
            "skipped": 0,
            "fixed_geometries": 0,
            "duplicates": 0,
            "blanked_values": 0,
            "z_dropped": 0,
            "operation": None,
            "problems": [],
        }

    def problem(self, row: int, message: str) -> None:
        if len(self.data["problems"]) < MAX_REPORTED_ROWS:
            self.data["problems"].append({"row": row, "message": message})


def _target_layer(item: dict[str, Any], job: DataJob, source_crs: CoordinateSystem) -> Layer:
    if item.get("target_layer"):
        layer = (
            Layer.objects.filter(pk=item["target_layer"], project=job.project)
            .select_related("crs")
            .first()
        )
        if layer is None:
            raise ValidationError("The target layer isn't in this project.")
        return layer
    new = item.get("new_layer") or {}
    taken: set[str] = set()
    schema = [
        {"name": gdal_io.safe_field_name(f["target"], taken), "type": f.get("type", "text")}
        for f in item.get("fields", [])
        if f.get("target")
    ]
    schema = schema_rules.validate_schema(schema)
    top = max((layer.order for layer in job.project.layers.all()), default=0)
    return Layer.objects.create(
        district_id=job.district_id,
        project=job.project,
        name=new.get("name") or item["source"],
        domain=new.get("domain", "other"),
        geometry_type=new["geometry_type"],
        crs=source_crs,  # new layers keep the file's CRS: no conversion
        schema=schema,
        style=styles.default_style(),
        order=top + 1,
        source=Layer.Source.UPLOAD,
        created_by=job.created_by,
    )


def _fix(geojson: dict[str, Any], raw: Any) -> dict[str, Any] | None:
    """GEOS MakeValid, keeping only the parts of the layer's family."""
    fixed = raw.MakeValid()
    if fixed is None or fixed.IsEmpty():
        return None
    return gdal_io.to_geojson(fixed)


def import_layer(
    job: DataJob, path: str, item: dict[str, Any], done: int, total: int
) -> dict[str, Any]:
    source_crs = _system(item["crs"])
    layer = _target_layer(item, job, source_crs)
    report = Report(item["source"], layer)
    convert = layer.crs.pk != source_crs.pk
    field_map = {f["source"]: f["target"] for f in item.get("fields", []) if f.get("target")}
    if not item.get("target_layer"):
        # New layers get sanitised names; map sources to what was created.
        created = [f["name"] for f in layer.schema]
        field_map = dict(zip(field_map, created, strict=False))
    known = {f["name"] for f in layer.schema}
    unknown_targets = sorted(set(field_map.values()) - known)
    if unknown_targets:
        raise ValidationError(f"Target fields {unknown_targets} aren't fields of {layer.name}.")
    invalid_policy = item.get("invalid_geometry", "skip")
    duplicate_policy = item.get("duplicates", "keep")
    bad_values = item.get("bad_values", "blank")
    cad_layers = set(item.get("cad_layers") or [])
    seen: set[str] = set()
    accepted = geo.ACCEPTED_GEOJSON_TYPES[layer.geometry_type]

    for row, geojson, attrs, raw in gdal_io.iter_features(
        path, job.file_format, item["source"], encoding=item.get("encoding")
    ):
        done += 1
        if done % PROGRESS_EVERY == 0:
            set_progress(job, done, total, f"Importing {item['source']}")
        if cad_layers and str(attrs.get("Layer")) not in cad_layers:
            continue
        if raw is not None and raw.Is3D():
            report.data["z_dropped"] += 1
        if geojson is not None:
            if geojson["type"] not in accepted:
                report.data["skipped"] += 1
                report.problem(
                    row, f"{geojson['type']} doesn't belong in a {layer.geometry_type} layer"
                )
                continue
            digest = hashlib.sha256(json.dumps(geojson, sort_keys=True).encode()).hexdigest()
            if digest in seen:
                report.data["duplicates"] += 1
                if duplicate_policy == "skip":
                    report.data["skipped"] += 1
                    report.problem(row, "duplicate geometry (skipped)")
                    continue
            seen.add(digest)
            if convert:
                geojson, op = transform_geojson(geojson, source_crs, layer.crs)
                report.data["operation"] = {"name": op.name, "accuracy_m": op.accuracy_m}
            try:
                geo.check_geometry(geojson, layer)
            except ValidationError as exc:
                reason = "; ".join(exc.messages)
                if invalid_policy == "abort":
                    raise ImportAborted(f"Row {row}: {reason}") from exc
                if invalid_policy == "fix" and raw is not None and "invalid" in reason:
                    fixed = _fix(geojson, raw)
                    if fixed is not None and fixed["type"] in accepted:
                        if convert:
                            fixed, _ = transform_geojson(fixed, source_crs, layer.crs)
                        geojson = fixed
                        report.data["fixed_geometries"] += 1
                    else:
                        report.data["skipped"] += 1
                        report.problem(row, f"{reason} (couldn't be fixed)")
                        continue
                else:
                    report.data["skipped"] += 1
                    report.problem(row, reason)
                    continue
        properties: dict[str, Any] = {}
        for source_name, target_name in field_map.items():
            properties[target_name] = attrs.get(source_name)
        try:
            properties = schema_rules.validate_properties(layer.schema, properties)
        except ValidationError as exc:
            errors = exc.message_dict
            if bad_values == "skip_feature":
                report.data["skipped"] += 1
                report.problem(row, f"values don't fit: {errors}")
                continue
            for name in errors:
                if name in properties:
                    properties[name] = None
                    report.data["blanked_values"] += 1
            report.problem(row, f"values left empty: {errors}")
            try:
                properties = schema_rules.validate_properties(layer.schema, properties)
            except ValidationError as again:  # e.g. a required field now empty
                report.data["skipped"] += 1
                report.problem(row, f"skipped: {again.message_dict}")
                continue
        feature = Feature.objects.create(
            district_id=job.district_id,
            layer=layer,
            properties=properties,
            origin=Feature.Origin.IMPORT,
            created_by=job.created_by,
            updated_by=job.created_by,
        )
        geo.write_geometry(feature, geojson)
        report.data["imported"] += 1
    return report.data


def run_import(job: DataJob, file: Path) -> dict[str, Any]:
    path, _ = gdal_io.prepare(file, job.file_format)
    items = job.plan.get("layers", [])
    if not items:
        raise ValidationError("Choose at least one layer to import.")
    total = sum(
        next(
            (
                layer["feature_count"]
                for layer in job.inspection["layers"]
                if layer["name"] == item["source"]
            ),
            0,
        )
        for item in items
    )
    reports = []
    done = 0
    with transaction.atomic():
        for item in items:
            report = import_layer(job, path, item, done, total)
            done += report["imported"] + report["skipped"]
            reports.append(report)
    set_progress(job, total, total, "Done")
    return {"layers": reports}

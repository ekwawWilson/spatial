"""What goes inside a .spp file, and how a project is rebuilt from it.

The package is a zip (never visible as such: container.py encrypts it):

    manifest.json    package version, app version, source, checksums
    project.json     project, coordinate systems, layers (schema, style),
                     checklist, basemap configuration (no API keys)
    data.gpkg        one table per layer: geometry in the layer's own CRS,
                     attributes, version, origin, verified flag, dates
    history.jsonl    earlier versions of every feature (from the audit log)
    attachments/     checklist documents

Coordinates travel as written (17 significant figures through OGR, the path
Phase 5 proved exact) and are never reprojected. Opening creates a new
project in the current district with new ids; nothing existing is changed.
"""

import hashlib
import json
import shutil
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone
from osgeo import ogr, osr
from pyproj import CRS
from pyproj.exceptions import CRSError

from basemaps.models import BasemapSource
from core.models import AuditLog, District, Membership, User
from crs.models import CoordinateSystem
from crs.services import register_custom
from projects import geometry as geo
from projects.models import Feature, Layer, PlanProject
from readiness.models import Attachment, Item
from transfer import gdal_io
from transfer.safety import check_zip

from .container import NewerVersion, SppError

PACKAGE_VERSION = 1
BATCH = 2000
ITEM_FIELDS = (
    "group",
    "key",
    "title",
    "description",
    "kind",
    "domain",
    "geometry_type",
    "rules",
    "order",
    "status",
    "notes",
)
BASEMAP_FIELDS = (
    "name",
    "kind",
    "preset",
    "url",
    "layers",
    "attribution",
    "min_zoom",
    "max_zoom",
    "requires_key",
    "notes",
    "order",
)

# Upgrades for packages written by older versions: UPGRADES[n] turns an
# unpacked version-n package (a directory) into version n + 1, in place.
UPGRADES: dict[int, Callable[[Path], None]] = {}


class BadPackage(SppError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"The file's contents can't be used: {detail}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _srs(system: CoordinateSystem) -> osr.SpatialReference:
    ref = osr.SpatialReference()
    if system.code.startswith("EPSG:"):
        ref.ImportFromEPSG(int(system.code.split(":")[1]))
    else:
        ref.ImportFromWkt(system.wkt)
    ref.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return ref


# --- Saving ----------------------------------------------------------------------------

GPKG_FIELDS = (
    ("uuid", ogr.OFTString),
    ("version", ogr.OFTInteger64),
    ("origin", ogr.OFTString),
    ("verified", ogr.OFTInteger),
    ("properties", ogr.OFTString),
    ("created_at", ogr.OFTString),
    ("updated_at", ogr.OFTString),
)


def _write_layer(dataset: Any, table: str, layer: Layer) -> tuple[int, dict[int, str]]:
    """Writes one layer's features; returns their count and {feature id: uuid}."""
    out = dataset.CreateLayer(table, _srs(layer.crs), ogr.wkbUnknown)
    for name, kind in GPKG_FIELDS:
        out.CreateField(ogr.FieldDefn(name, kind))
    definition = out.GetLayerDefn()
    uuids: dict[int, str] = {}
    out.StartTransaction()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, uuid, ST_AsGeoJSON(geom_native, 17), properties, version, origin,"
            " verified, created_at, updated_at FROM projects_feature"
            " WHERE layer_id = %s ORDER BY id",
            [layer.pk],
        )
        for fid, uuid, geometry, props, version, origin, verified, created, updated in cursor:
            feature = ogr.Feature(definition)
            feature.SetField("uuid", str(uuid))
            feature.SetField("version", version)
            feature.SetField("origin", origin)
            feature.SetField("verified", 1 if verified else 0)
            properties = props if isinstance(props, dict) else json.loads(props)
            feature.SetField("properties", json.dumps(properties))
            feature.SetField("created_at", created.isoformat())
            feature.SetField("updated_at", updated.isoformat())
            if geometry:
                feature.SetGeometry(gdal_io.from_geojson(json.loads(geometry)))
            if out.CreateFeature(feature) != 0:
                raise ValidationError(f"Couldn't write a feature of {layer.name} to the file.")
            uuids[fid] = str(uuid)
    out.CommitTransaction()
    return len(uuids), uuids


def _write_history(path: Path, uuids: dict[int, str]) -> int:
    """Earlier versions of the features, oldest first, keyed by feature UUID."""
    count = 0
    ids = [str(fid) for fid in uuids]
    with open(path, "w", encoding="utf-8") as out:
        for start in range(0, len(ids), BATCH):
            entries = AuditLog.objects.filter(
                table_name="projects_feature", row_id__in=ids[start : start + BATCH]
            ).order_by("id")
            for entry in entries.iterator():
                out.write(
                    json.dumps(
                        {
                            "feature": uuids[int(entry.row_id)],
                            "action": entry.action,
                            "before": entry.before,
                            "after": entry.after,
                            "at": entry.occurred_at.isoformat(),
                        }
                    )
                    + "\n"
                )
                count += 1
    return count


def _basemaps() -> list[dict[str, Any]]:
    """The basemap sources this district can use, without their API keys."""
    return [
        {name: getattr(source, name) for name in BASEMAP_FIELDS}
        for source in BasemapSource.objects.filter(is_active=True).order_by("order", "id")
    ]


def build(project: PlanProject, user: User, workdir: Path) -> tuple[Path, dict[str, Any]]:
    """Writes the project's package into `workdir`; returns its path and a summary."""
    root = workdir / "package"
    (root / "attachments").mkdir(parents=True)
    layers = list(project.layers.select_related("crs").order_by("id"))

    dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(root / "data.gpkg"))
    layer_rows = []
    all_uuids: dict[int, str] = {}
    feature_total = 0
    for index, layer in enumerate(layers, start=1):
        table = f"layer_{index}"
        count, uuids = _write_layer(dataset, table, layer)
        feature_total += count
        all_uuids.update(uuids)
        layer_rows.append(
            {
                "ref": layer.pk,
                "table": table,
                "name": layer.name,
                "domain": layer.domain,
                "geometry_type": layer.geometry_type,
                "crs": layer.crs.code,
                "schema": layer.schema,
                "style": layer.style,
                "order": layer.order,
                "visible": layer.visible,
                "opacity": layer.opacity,
                "source": layer.source,
                "features": count,
            }
        )
    dataset.FlushCache()
    dataset = None  # close the file before it's read for the zip

    history_count = _write_history(root / "history.jsonl", all_uuids)

    systems = {layer.crs.code: layer.crs for layer in layers}
    systems[project.crs.code] = project.crs
    item_rows = []
    attachment_count = 0
    items = project.checklist_items.select_related("owner").prefetch_related("attachments")
    for item in items.order_by("group", "order", "id"):
        files = []
        for attachment in item.attachments.all():
            source = Path(settings.MEDIA_ROOT) / attachment.path
            if not attachment.path or not source.is_file():
                continue
            attachment_count += 1
            member = f"attachments/{attachment_count}"
            shutil.copyfile(source, root / member)
            files.append({"file": member, "name": attachment.name, "size": attachment.size})
        item_rows.append(
            {
                **{name: getattr(item, name) for name in ITEM_FIELDS},
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "owner_email": item.owner.email if item.owner else None,
                "linked_layer": item.linked_layer_id,
                "attachments": files,
            }
        )

    boundary_uuid = None
    if project.boundary_feature_id:
        boundary_uuid = all_uuids.get(project.boundary_feature_id)
    content = {
        "project": {
            "name": project.name,
            "community": project.community,
            "description": project.description,
            "crs": project.crs.code,
            "status": project.status,
            "boundary_status": project.boundary_status,
            "boundary_feature": boundary_uuid,
        },
        "coordinate_systems": [
            {"code": s.code, "name": s.name, "wkt": s.wkt, "notes": s.notes}
            for s in systems.values()
        ],
        "layers": layer_rows,
        "checklist": item_rows,
        "basemaps": _basemaps(),
    }
    (root / "project.json").write_text(json.dumps(content), encoding="utf-8")

    district = District.objects.get(pk=project.district_id)
    members = sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    )
    summary = {
        "layers": len(layers),
        "features": feature_total,
        "history_entries": history_count,
        "checklist_items": len(item_rows),
        "attachments": attachment_count,
    }
    manifest = {
        "package_version": PACKAGE_VERSION,
        "app_version": settings.SPECTACULAR_SETTINGS.get("VERSION", ""),
        "saved_at": timezone.now().isoformat(),
        "saved_by": user.email,
        "district": {"name": district.name, "code": district.code},
        "project": project.name,
        "crs": project.crs.code,
        "contents": summary,
        "checksums": {name: _sha256(root / name) for name in members},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    package = workdir / "package.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ["manifest.json", *members]:
            archive.write(root / name, name)
    shutil.rmtree(root)
    return package, summary


# --- Opening ---------------------------------------------------------------------------


def unpack(package: Path, workdir: Path) -> tuple[Path, dict[str, Any]]:
    """Unpacks and checks a package; upgrades it if an older version wrote it.
    Returns the directory and the manifest."""
    try:
        names = check_zip(package)
    except ValidationError as exc:
        raise BadPackage("; ".join(exc.messages)) from exc
    root = workdir / "package"
    root.mkdir()
    with zipfile.ZipFile(package) as archive:
        for name in names:
            archive.extract(name, root)
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        version = int(manifest["package_version"])
        checksums = dict(manifest["checksums"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BadPackage("the manifest is missing or unreadable.") from exc
    for name, expected in checksums.items():
        path = root / name
        if ".." in Path(name).parts or not path.is_file() or _sha256(path) != expected:
            raise BadPackage(f"{name} is missing or doesn't match its checksum.")
    if version > PACKAGE_VERSION:
        raise NewerVersion()
    while version < PACKAGE_VERSION:
        upgrade = UPGRADES.get(version)
        if upgrade is None:
            raise BadPackage(f"package version {version} is no longer supported.")
        upgrade(root)
        version += 1
    return root, manifest


def _same_custom_system(wkt: str) -> CoordinateSystem | None:
    """A custom system visible here with the same definition. Compared as
    coordinate systems, not as text: registering rewrites the WKT slightly."""
    try:
        wanted = CRS.from_wkt(wkt)
    except CRSError as exc:
        raise BadPackage("one of its coordinate systems can't be read.") from exc
    for system in CoordinateSystem.objects.filter(is_active=True, is_builtin=False):
        try:
            if system.wkt == wkt or CRS.from_wkt(system.wkt) == wanted:
                return system
        except CRSError:
            continue
    return None


def _coordinate_systems(
    rows: list[dict[str, Any]], district_id: int, user: User, report: dict[str, Any]
) -> dict[str, CoordinateSystem]:
    """Maps the file's CRS codes to this server's systems. EPSG systems must be
    enabled here; custom ones are matched by definition or added to the district."""
    result: dict[str, CoordinateSystem] = {}
    for row in rows:
        code = row["code"]
        if code.startswith("EPSG:"):
            system = CoordinateSystem.objects.filter(code=code, is_active=True).first()
            if system is None:
                raise BadPackage(
                    f"the project uses {code} ({row['name']}), which isn't enabled on this"
                    " server. Ask a system administrator to add it, then open the file again."
                )
        else:
            system = _same_custom_system(row["wkt"])
            if system is None:
                try:
                    system = register_custom(
                        name=row["name"],
                        definition=row["wkt"],
                        district=District.objects.get(pk=district_id),
                        user=user,
                        notes=row.get("notes", ""),
                    )
                except ValidationError as exc:
                    raise BadPackage(
                        f"its coordinate system {row['name']} couldn't be added: "
                        + "; ".join(exc.messages)
                    ) from exc
                report["crs_added"].append(f"{system.code} {system.name}")
        result[code] = system
    return result


def _free_name(district_id: int, name: str) -> str:
    taken = set(
        PlanProject.objects.filter(district_id=district_id, name__startswith=name).values_list(
            "name", flat=True
        )
    )
    if name not in taken:
        return name
    n = 2
    while f"{name} ({n})" in taken:
        n += 1
    return f"{name} ({n})"


def _taken_uuids(uuids: list[str]) -> set[str]:
    taken: set[str] = set()
    with connection.cursor() as cursor:
        for start in range(0, len(uuids), BATCH):
            cursor.execute(
                "SELECT app_taken_feature_uuids(%s::uuid[])", [uuids[start : start + BATCH]]
            )
            taken.update(str(row[0]) for row in cursor.fetchall())
    return taken


def _read_table(path: Path, table: str) -> list[dict[str, Any]]:
    dataset = ogr.Open(str(path))
    source = dataset.GetLayerByName(table) if dataset is not None else None
    if source is None:
        raise BadPackage(f"the data for {table} is missing.")
    rows = []
    for feature in source:
        geometry = feature.GetGeometryRef()
        rows.append(
            {
                "uuid": feature.GetField("uuid"),
                "version": feature.GetField("version"),
                "origin": feature.GetField("origin"),
                "verified": bool(feature.GetField("verified")),
                "properties": json.loads(feature.GetField("properties")),
                "created_at": feature.GetField("created_at"),
                "updated_at": feature.GetField("updated_at"),
                "geometry": gdal_io.to_geojson(geometry) if geometry is not None else None,
            }
        )
    source = None
    dataset = None
    return rows


def _resrid(hexwkb: str, srid: int) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT encode(ST_AsEWKB(ST_SetSRID(%s::geometry, %s)), 'hex')", [hexwkb, srid]
        )
        value: str = cursor.fetchone()[0]
    return value


def _import_history(
    path: Path,
    targets: dict[str, tuple[int, str, Layer]],
    district_id: int,
    source_srids: dict[int, int],
) -> int:
    """Writes the features' earlier versions to the audit log under their new
    ids. `targets`: original uuid -> (new id, new uuid, new layer)."""
    if not path.is_file():
        return 0

    def remap(row: dict[str, Any] | None, target: tuple[int, str, Layer]) -> str | None:
        if row is None:
            return None
        new_id, new_uuid, layer = target
        row = {**row, "id": new_id, "uuid": new_uuid, "layer_id": layer.pk}
        row["district_id"] = district_id
        row["created_by_id"] = row["updated_by_id"] = None
        # A custom CRS can get another SRID on this server.
        if row.get("geom_native") and source_srids.get(layer.pk) != layer.crs.srid:
            row["geom_native"] = _resrid(row["geom_native"], layer.crs.srid)
        return json.dumps(row)

    count = 0
    batch: list[list[Any]] = []

    def flush() -> None:
        if batch:
            with connection.cursor() as cursor:
                cursor.executemany(
                    "SELECT app_import_feature_history(%s, %s, %s::jsonb, %s::jsonb, %s)", batch
                )
            batch.clear()

    with open(path, encoding="utf-8") as lines:
        for line in lines:
            entry = json.loads(line)
            target = targets.get(entry["feature"])
            if target is None:
                continue
            batch.append(
                [
                    target[0],
                    entry["action"],
                    remap(entry["before"], target),
                    remap(entry["after"], target),
                    entry["at"],
                ]
            )
            count += 1
            if len(batch) >= BATCH:
                flush()
    flush()
    return count


def _basemaps_in(
    rows: list[dict[str, Any]], district_id: int, user: User, may_add: bool, report: dict[str, Any]
) -> None:
    """Adds the file's basemaps that this district doesn't have yet (without
    keys: those never leave a server)."""
    have = {
        (b.kind, b.preset, b.url, b.layers)
        for b in BasemapSource.objects.all()  # global and this district's (row-level security)
    }
    for row in rows:
        identity = (row["kind"], row["preset"], row["url"], row["layers"])
        if identity in have:
            continue
        if not may_add:
            report["basemaps_skipped"].append(row["name"])
            continue
        BasemapSource.objects.create(
            district_id=district_id,
            created_by=user,
            **{name: row[name] for name in BASEMAP_FIELDS},
        )
        have.add(identity)
        note = " (needs its API key)" if row["requires_key"] else ""
        report["basemaps_added"].append(row["name"] + note)


def restore(
    root: Path, manifest: dict[str, Any], district_id: int, user: User, *, may_add_basemaps: bool
) -> tuple[PlanProject, dict[str, Any]]:
    """Creates a new project in the district from an unpacked package. Runs in
    the caller's transaction: a failure leaves nothing behind."""
    try:
        content = json.loads((root / "project.json").read_text(encoding="utf-8"))
        source = content["project"]
    except (OSError, ValueError, KeyError) as exc:
        raise BadPackage("the project description is missing or unreadable.") from exc
    report: dict[str, Any] = {
        "saved_at": manifest.get("saved_at"),
        "saved_by": manifest.get("saved_by"),
        "from_district": (manifest.get("district") or {}).get("name"),
        "crs_added": [],
        "basemaps_added": [],
        "basemaps_skipped": [],
    }
    systems = _coordinate_systems(content["coordinate_systems"], district_id, user, report)

    name = _free_name(district_id, source["name"])
    report["renamed_from"] = source["name"] if name != source["name"] else None
    project = PlanProject(
        district_id=district_id,
        name=name,
        community=source.get("community", ""),
        description=source.get("description", ""),
        crs=systems[source["crs"]],
        status=source.get("status", PlanProject.Status.DRAFT),
        boundary_status=source.get("boundary_status", PlanProject.BoundaryStatus.DRAFT),
        created_by=user,
    )
    project.skip_default_checklist = True  # type: ignore[attr-defined]
    project.save()

    layers: dict[int, Layer] = {}  # the file's layer ref -> new layer
    source_srids: dict[int, int] = {}  # new layer id -> SRID the file's history uses
    tables: list[tuple[Layer, list[dict[str, Any]]]] = []
    for row in content["layers"]:
        layer = Layer.objects.create(
            district_id=district_id,
            project=project,
            name=row["name"],
            domain=row["domain"],
            geometry_type=row["geometry_type"],
            crs=systems[row["crs"]],
            schema=row["schema"],
            style=row["style"],
            order=row["order"],
            visible=row["visible"],
            opacity=row["opacity"],
            source=row["source"],
            created_by=user,
        )
        layers[row["ref"]] = layer
        tables.append((layer, _read_table(root / "data.gpkg", row["table"])))

    # Feature UUIDs are kept when free on this server, and replaced when taken
    # (e.g. the file is opened where the original project still exists).
    every = [r["uuid"] for _, rows in tables for r in rows]
    taken = _taken_uuids(every)
    ids = geo.reserve_feature_ids(len(every))
    targets: dict[str, tuple[int, str, Layer]] = {}
    position = 0
    for layer, rows in tables:
        for row in rows:
            original = row["uuid"]
            row["id"] = ids[position]
            position += 1
            if original in taken:
                row["uuid"] = str(uuid4())
            targets[original] = (row["id"], row["uuid"], layer)
    report["new_feature_ids"] = sum(1 for original, t in targets.items() if t[1] != original)

    # History first (its ids are reserved but unused), then the features.
    for layer in layers.values():
        source_srids[layer.pk] = layer.crs.srid
    for row in content["layers"]:
        layer = layers[row["ref"]]
        if not row["crs"].startswith("EPSG:") and row["crs"] != layer.crs.code:
            source_srids[layer.pk] = int(row["crs"].split(":")[1])
    report["history_entries"] = _import_history(
        root / "history.jsonl", targets, district_id, source_srids
    )
    for layer, rows in tables:
        for start in range(0, len(rows), BATCH):
            geo.insert_features(layer, rows[start : start + BATCH], user.pk)
    report["layers"] = len(layers)
    report["features"] = len(every)

    boundary = targets.get(source.get("boundary_feature") or "")
    if boundary is not None:
        project.boundary_feature = Feature.objects.get(pk=boundary[0])
        project.save(update_fields=["boundary_feature"])

    members = {
        m.user.email: m.user
        for m in Membership.objects.filter(district_id=district_id, is_active=True).select_related(
            "user"
        )
    }
    attachments = 0
    for row in content.get("checklist", []):
        linked = layers.get(row.get("linked_layer") or 0)
        item = Item.objects.create(
            district_id=district_id,
            project=project,
            owner=members.get(row.get("owner_email") or ""),
            due_date=date.fromisoformat(row["due_date"]) if row.get("due_date") else None,
            linked_layer=linked,
            **{name: row[name] for name in ITEM_FIELDS},
        )
        for file in row.get("attachments", []):
            member = root / file["file"]
            if not member.is_file():
                continue
            name = Path(file["name"]).name or "document"
            attachment = Attachment.objects.create(
                district_id=district_id,
                item=item,
                name=name,
                path="",
                size=member.stat().st_size,
                uploaded_by=user,
            )
            relative = Path("readiness") / str(district_id) / f"{attachment.pk}-{name}"
            target = Path(settings.MEDIA_ROOT) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(member, target)
            attachment.path = str(relative)
            attachment.save(update_fields=["path"])
            attachments += 1
    report["checklist_items"] = len(content.get("checklist", []))
    report["attachments"] = attachments

    _basemaps_in(content.get("basemaps", []), district_id, user, may_add_basemaps, report)
    report["project"] = project.pk
    report["name"] = project.name
    return project, report

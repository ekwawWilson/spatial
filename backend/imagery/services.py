"""Processing uploads, making contours, and the checklist's imagery measure."""

import shutil
import traceback
import uuid as uuid_module
from pathlib import Path
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date

from basemaps.models import BasemapSource
from core.models import User
from core.tenancy import tenant_context
from crs.models import CoordinateSystem
from crs.services import transform_geojson
from projects import geometry as geo
from projects import styles
from projects.models import Feature, Layer, PlanProject

from . import raster
from .models import Imagery

CONTOUR_LAYER = "Topography (contours)"
MAX_CONTOURS = 20_000


def folder(imagery: Imagery) -> Path:
    return Path(settings.MEDIA_ROOT) / "imagery" / str(imagery.district_id) / str(imagery.uuid)


def source_path(imagery: Imagery) -> Path:
    return folder(imagery) / "source.tif"


def cog_path(imagery: Imagery) -> Path:
    return folder(imagery) / "image.tif"


def tile_url(imagery: Imagery) -> str:
    return f"/api/imagery/{imagery.pk}/tiles/{{z}}/{{x}}/{{y}}.png"


def process(imagery: Imagery) -> None:
    """Validates the upload, converts it, records what it is, and (for an
    orthophoto) makes it available as a basemap that may be stored offline:
    it is the district's own data."""
    info = raster.inspect(source_path(imagery), imagery.assigned_crs)
    is_dem = imagery.kind == Imagery.Kind.DEM
    if is_dem and info["bands"] != 1:
        raise ValidationError("An elevation model has one band; this file has several.")
    raster.to_cog(source_path(imagery), cog_path(imagery), info["srs"], is_dem=is_dem)
    source_path(imagery).unlink(missing_ok=True)

    if imagery.capture_date is None and info["capture_date"]:
        imagery.capture_date = parse_date(info["capture_date"][:10])
    if not imagery.source and info["source"]:
        imagery.source = info["source"][:200]
    imagery.crs = info["crs"][:200]
    imagery.width, imagery.height, imagery.bands = info["width"], info["height"], info["bands"]
    imagery.resolution_m = info["resolution_m"]
    imagery.bounds = info["bounds"]
    imagery.min_zoom, imagery.max_zoom = info["min_zoom"], info["max_zoom"]
    imagery.size_bytes = cog_path(imagery).stat().st_size
    imagery.value_range = raster.value_range(cog_path(imagery)) if is_dem else None
    imagery.status = Imagery.Status.READY
    imagery.error = ""
    if not is_dem and imagery.basemap_id is None:
        imagery.basemap = BasemapSource.objects.create(
            district_id=imagery.district_id,
            name=f"{imagery.name} (imagery)"[:120],
            kind=BasemapSource.Kind.XYZ,
            url=tile_url(imagery),
            attribution=imagery.source[:300],
            min_zoom=imagery.min_zoom,
            max_zoom=imagery.max_zoom,
            offline_cache_allowed=True,
            notes="The district's own imagery: it may be stored on devices for offline use.",
            created_by=imagery.created_by,
        )
    imagery.save()


@shared_task  # type: ignore[misc]
def process_imagery(imagery_id: int, district_id: int, user_id: int | None) -> None:
    try:
        with tenant_context(district_id, user_id=user_id):
            imagery = Imagery.objects.get(pk=imagery_id)
            imagery.status = Imagery.Status.PROCESSING
            imagery.save(update_fields=["status"])
        with tenant_context(district_id, user_id=user_id):
            process(Imagery.objects.get(pk=imagery_id))
    except ValidationError as exc:
        _fail(imagery_id, district_id, user_id, "; ".join(exc.messages))
    except Exception as exc:  # noqa: BLE001 - record any failure on the row
        _fail(
            imagery_id,
            district_id,
            user_id,
            f"Unexpected error: {exc}\n{traceback.format_exc(limit=3)}",
        )


def _fail(imagery_id: int, district_id: int, user_id: int | None, message: str) -> None:
    with tenant_context(district_id, user_id=user_id):
        imagery = Imagery.objects.filter(pk=imagery_id).first()
        if imagery is None:
            return
        imagery.status = Imagery.Status.FAILED
        imagery.error = message
        imagery.save(update_fields=["status", "error"])
        shutil.rmtree(folder(imagery), ignore_errors=True)


def remove(imagery: Imagery) -> None:
    """Deletes the imagery and its files, and switches its basemap off
    (basemaps are deactivated, not deleted: only system admins remove them)."""
    directory = folder(imagery)
    basemap = imagery.basemap
    imagery.delete()
    if basemap is not None:
        basemap.is_active = False
        basemap.save(update_fields=["is_active"])
    shutil.rmtree(directory, ignore_errors=True)


def make_contours(imagery: Imagery, interval: float, user: User) -> dict[str, Any]:
    """Contour lines from an elevation model, as a line layer in the project's
    CRS. Running it again replaces the lines made before."""
    if imagery.kind != Imagery.Kind.DEM or imagery.status != Imagery.Status.READY:
        raise ValidationError(
            "Contours are made from an elevation model that has finished processing."
        )
    if not interval > 0:
        raise ValidationError({"interval": ["must be greater than 0"]})
    lines, _ = raster.contours(cog_path(imagery), interval, MAX_CONTOURS)
    code = imagery.crs.split(" ", 1)[0]
    source = CoordinateSystem.objects.filter(code=code, is_active=True).first()
    if source is None:
        raise ValidationError(
            f"The elevation model is in {imagery.crs}, which isn't enabled on this server."
            " Ask a system administrator to add it, then make the contours again."
        )
    project: PlanProject = imagery.project
    layer = project.layers.select_related("crs").filter(name=CONTOUR_LAYER).first()
    if layer is None:
        top = max((existing.order for existing in project.layers.all()), default=0)
        layer = Layer.objects.create(
            district_id=project.district_id,
            project=project,
            name=CONTOUR_LAYER,
            domain="F",
            geometry_type="line",
            crs=project.crs,
            schema=[
                {"name": "elevation", "label": "Elevation", "type": "decimal", "required": False}
            ],
            style={**styles.default_style(), "stroke": "#8a6d3b", "stroke_width": 1},
            order=top + 1,
            source=Layer.Source.DERIVED,
            created_by=user,
        )
    elif layer.geometry_type != "line":
        raise ValidationError(f"A layer called {CONTOUR_LAYER} exists and isn't a line layer.")
    removed, _ = Feature.objects.filter(layer=layer, origin=Feature.Origin.DERIVED).delete()

    now = timezone.now().isoformat()
    ids = geo.reserve_feature_ids(len(lines))
    rows = []
    for feature_id, (elevation, geometry) in zip(ids, lines, strict=True):
        converted, operation = transform_geojson(geometry, source, layer.crs)
        rows.append(
            {
                "id": feature_id,
                "uuid": uuid_module.uuid4(),
                "geometry": converted,
                "properties": {"elevation": elevation},
                "version": 1,
                "origin": Feature.Origin.DERIVED,
                "verified": False,
                "created_at": now,
                "updated_at": now,
            }
        )
    for start in range(0, len(rows), 1000):
        geo.insert_features(layer, rows[start : start + 1000], user.pk)
    return {
        "layer": layer.pk,
        "layer_name": layer.name,
        "contours": len(rows),
        "replaced": removed,
        "interval": interval,
        "converted_from": source.code if source.pk != layer.crs.pk else None,
    }


def checklist_metrics(project: PlanProject) -> dict[str, Any]:
    """The newest orthophoto of a project, for the readiness checklist."""
    ready = Imagery.objects.filter(
        project=project, kind=Imagery.Kind.ORTHO, status=Imagery.Status.READY
    )
    images = list(ready)
    dates = [image.capture_date for image in images if image.capture_date is not None]
    newest = max(dates, default=None)
    return {
        "imagery_count": len(images),
        "undated": len(images) - len(dates),
        "newest_capture": newest.isoformat() if newest else None,
        "age_days": (timezone.localdate() - newest).days if newest else None,
        "best_resolution_m": min(
            (image.resolution_m for image in images if image.resolution_m), default=None
        ),
    }

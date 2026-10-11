"""Cases, notices and their dates; and finding new development from images."""

from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction

from core.models import User
from crs.models import CoordinateSystem
from crs.services import transform_geojson
from imagery import services as imagery_services
from imagery.models import Imagery
from permits.models import Counter
from projects import geometry as geo
from projects import styles
from projects.models import Feature, Layer, PlanProject
from relations.models import LayerRole

from . import change, registry
from .models import Case, DetectionRun, Notice

OPEN = (Case.Status.OPEN, Case.Status.NOTICE)
DETECTIONS_LAYER = "Changes found between images"
DETECTIONS_SCHEMA: list[dict[str, Any]] = [
    {"name": "kind", "label": "What it looks like", "type": "text", "required": False},
    {"name": "area_m2", "label": "Area changed (m²)", "type": "decimal", "required": False},
    {"name": "change", "label": "Strength of change", "type": "decimal", "required": False},
    {"name": "between", "label": "Between", "type": "text", "required": False},
    {"name": "case_no", "label": "Enforcement case", "type": "text", "required": False},
]
KINDS = {
    "permitted": "Where a permit has been granted",
    "existing": "At a building already on the map",
    "new": "New: no permit and no building on the map",
}


def next_number(district_id: int, district_code: str, year: int) -> str:
    with transaction.atomic():
        counter, _ = Counter.objects.select_for_update().get_or_create(
            district_id=district_id, kind="case", year=year
        )
        counter.last += 1
        counter.save(update_fields=["last"])
    return f"{district_code}/EN/{year}/{counter.last:04d}"


# --- Dates ---------------------------------------------------------------------------------------


def notice_dates(notice: Notice, today: date | None = None) -> dict[str, Any]:
    """What follows from a notice, by the Regulations' days."""
    today = today or date.today()
    out: dict[str, Any] = {}
    if notice.kind == "rectification" and notice.comply_by and not notice.complied_on:
        # r.57(2): not rectified in time, an enforcement notice within 14 days.
        due = notice.comply_by + timedelta(days=registry.ENFORCEMENT_AFTER_DAYS)
        followed = notice.case.notices.filter(
            kind="enforcement", issued_on__gte=notice.issued_on
        ).exists()
        if today > notice.comply_by and not followed:
            out["enforcement_notice_due_on"] = due.isoformat()
            out["overdue"] = today > due
    if notice.kind == "enforcement" and notice.served_on and not notice.complied_on:
        # r.57(4): 14 days after service, the Assembly may rectify and recover the cost.
        out["assembly_may_act_from"] = (
            notice.served_on + timedelta(days=registry.ACT_AFTER_DAYS)
        ).isoformat()
    if notice.kind == "entry" and notice.served_on:
        # r.58: at least three days' notice before entering.
        out["entry_not_before"] = (
            notice.served_on + timedelta(days=registry.ENTRY_NOTICE_DAYS)
        ).isoformat()
    if notice.kind == "revocation" and notice.served_on:
        # Form 48B: 21 days to show cause.
        out["show_cause_by"] = (
            notice.served_on + timedelta(days=registry.SHOW_CAUSE_DAYS)
        ).isoformat()
    if notice.comply_by and not notice.complied_on and notice.case.status in OPEN:
        out["past_comply_by"] = today > notice.comply_by
    return out


def next_action(case: Case, today: date | None = None) -> dict[str, Any] | None:
    """The most pressing thing in an open case."""
    if case.status not in OPEN:
        return None
    today = today or date.today()
    notices = list(case.notices.all())
    if not notices:
        return {"label": "Serve a notice", "due_on": None, "overdue": False}
    for notice in notices:
        dates = notice_dates(notice, today)
        if "enforcement_notice_due_on" in dates:
            return {
                "label": "Serve an enforcement notice (r.57(2))",
                "due_on": dates["enforcement_notice_due_on"],
                "overdue": dates["overdue"],
            }
    unserved = next((n for n in notices if n.served_on is None), None)
    if unserved is not None:
        return {
            "label": f"Serve the {registry.NOTICE_BY_CODE[unserved.kind].label.lower()}",
            "due_on": None,
            "overdue": False,
        }
    waiting = [n for n in notices if n.comply_by and not n.complied_on]
    if waiting:
        last = waiting[-1]
        late = today > last.comply_by if last.comply_by else False
        return {
            "label": "Check whether the notice has been complied with"
            if late
            else "Wait for compliance",
            "due_on": last.comply_by.isoformat() if last.comply_by else None,
            "overdue": False,
        }
    return {"label": "Close the case", "due_on": None, "overdue": False}


# --- Notices -------------------------------------------------------------------------------------


def issue_notice(
    case: Case, kind: str, grounds: str, required: str, comply_by: date | None, on: date, user: User
) -> Notice:
    if case.status not in OPEN:
        raise ValidationError("This case is closed.")
    spec = registry.NOTICE_BY_CODE.get(kind)
    if spec is None:
        raise ValidationError({"kind": ["Not a kind of notice."]})
    if on > date.today() or on < case.opened_on:
        raise ValidationError({"on": ["Between the day the case was opened and today."]})
    if kind == "revocation" and case.permit_id is None:
        raise ValidationError({"kind": ["Link the case to the permit to be revoked first."]})
    if spec.dated and kind not in ("entry", "revocation") and comply_by is None:
        raise ValidationError({"comply_by": ["Give the date to comply by."]})
    if comply_by is not None and comply_by < on:
        raise ValidationError({"comply_by": ["Before the notice is issued."]})
    if not spec.dated:
        comply_by = None  # a stop notice takes effect at once
    return Notice.objects.create(
        district_id=case.district_id,
        case=case,
        kind=kind,
        grounds=grounds,
        required=required,
        issued_on=on,
        comply_by=comply_by,
        issued_by=user,
    )


def serve(notice: Notice, on: date, method: str, note: str) -> None:
    """r.56: records how and when the notice was served."""
    if method not in registry.SERVICE_BY_CODE:
        raise ValidationError({"method": ["Not one of the ways a notice may be served (r.56)."]})
    if on > date.today() or on < notice.issued_on:
        raise ValidationError({"on": ["Between the day the notice was issued and today."]})
    notice.served_on, notice.served_by, notice.served_note = on, method, note
    notice.save(update_fields=["served_on", "served_by", "served_note"])
    case = notice.case
    if case.status == Case.Status.OPEN:
        case.status = Case.Status.NOTICE
        case.save(update_fields=["status", "updated_at"])


def close(case: Case, status: str, outcome: str, cost: Any, recovered: Any, on: date) -> None:
    if case.status not in OPEN:
        raise ValidationError("This case is already closed.")
    if status not in (Case.Status.RECTIFIED, Case.Status.ENFORCED, Case.Status.DROPPED):
        raise ValidationError({"status": ["Rectified, enforced or dropped."]})
    if on > date.today() or on < case.opened_on:
        raise ValidationError({"on": ["Between the day the case was opened and today."]})
    if status == Case.Status.ENFORCED:
        # r.57(4): only 14 days after an enforcement notice was served.
        served = [n.served_on for n in case.notices.filter(kind="enforcement") if n.served_on]
        if not served:
            raise ValidationError(
                "The Assembly rectifies only after an enforcement notice has been served (r.57(4))."
            )
        earliest = min(served) + timedelta(days=registry.ACT_AFTER_DAYS)
        if on < earliest:
            raise ValidationError(
                f"Not before {earliest.isoformat()}: 14 days after the enforcement notice was"
                " served (r.57(4))."
            )
    case.status, case.outcome, case.closed_on = status, outcome, on
    case.cost = cost if status == Case.Status.ENFORCED else None
    case.cost_recovered = recovered if status == Case.Status.ENFORCED else None
    case.save(
        update_fields=["status", "outcome", "closed_on", "cost", "cost_recovered", "updated_at"]
    )
    if status == Case.Status.RECTIFIED:
        case.notices.filter(complied_on__isnull=True).update(complied_on=on)


# --- Finding changes between two images ----------------------------------------------------------


def detections_layer(project: PlanProject, user: User | None) -> Layer:
    existing = project.layers.filter(name=DETECTIONS_LAYER).first()
    if existing is not None:
        return existing
    top = max((layer.order for layer in project.layers.all()), default=0)
    return Layer.objects.create(
        district_id=project.district_id,
        project=project,
        name=DETECTIONS_LAYER,
        domain="G",
        geometry_type="polygon",
        crs=project.crs,
        schema=DETECTIONS_SCHEMA,
        style={
            "kind": "categorized",
            "field": "kind",
            "categories": [
                {
                    **styles.DEFAULT_SYMBOL,
                    "value": KINDS["new"],
                    "fill": "#d7263d",
                    "stroke": "#7a0f1c",
                    "fill_opacity": 0.45,
                },
                {
                    **styles.DEFAULT_SYMBOL,
                    "value": KINDS["existing"],
                    "fill": "#f4a259",
                    "stroke": "#8a5a1c",
                    "fill_opacity": 0.4,
                },
                {
                    **styles.DEFAULT_SYMBOL,
                    "value": KINDS["permitted"],
                    "fill": "#5b8e7d",
                    "stroke": "#2c4a40",
                    "fill_opacity": 0.3,
                },
            ],
            "default": dict(styles.DEFAULT_SYMBOL),
            "label_field": None,
        },
        order=top + 1,
        created_by=user,
    )


def _classify(feature_ids: list[int], project: PlanProject) -> dict[int, str]:
    """Each changed place: where a permit was granted, at a building already
    on the map, or new."""
    kinds = dict.fromkeys(feature_ids, "new")
    roles = {r.role: r for r in LayerRole.objects.filter(project=project)}
    with connection.cursor() as cursor:
        if "properties" in roles:
            cursor.execute(
                "SELECT DISTINCT d.id FROM projects_feature d JOIN projects_feature b"
                " ON ST_Intersects(d.geom_4326, b.geom_4326)"
                " WHERE d.id = ANY(%s) AND b.layer_id = %s",
                [feature_ids, roles["properties"].layer_id],
            )
            for (fid,) in cursor.fetchall():
                kinds[fid] = "existing"
        cursor.execute(
            "SELECT DISTINCT d.id FROM projects_feature d"
            " JOIN permits_application a ON a.project_id = %s AND a.status IN ('granted', 'issued')"
            " JOIN projects_feature s ON s.id = a.site_id"
            " WHERE d.id = ANY(%s) AND ST_Intersects(d.geom_4326, s.geom_4326)",
            [project.pk, feature_ids],
        )
        for (fid,) in cursor.fetchall():
            kinds[fid] = "permitted"
    return kinds


def detect(project: PlanProject, before: Imagery, after: Imagery, user: User) -> DetectionRun:
    """Compares two of the project's orthophotos and puts each changed place
    on the map, classed by whether a permit or a known building explains it."""
    for image in (before, after):
        if image.project_id != project.pk or image.kind != Imagery.Kind.ORTHO:
            raise ValidationError("Pick two orthophotos of this project.")
        if image.status != Imagery.Status.READY:
            raise ValidationError(f'"{image.name}" isn\'t ready yet.')
    if before.pk == after.pk:
        raise ValidationError("Pick two different images.")
    if before.capture_date and after.capture_date and before.capture_date > after.capture_date:
        before, after = after, before  # earlier first, whatever order they were given in
    shapes = change.detect(imagery_services.cog_path(before), imagery_services.cog_path(after))
    layer = detections_layer(project, user)
    wgs84 = CoordinateSystem.objects.get(code="EPSG:4326")
    between = f"{before.capture_date or before.name} and {after.capture_date or after.name}"
    made: list[Feature] = []
    for shape in shapes:
        geometry = shape["geometry"]
        if layer.crs_id != wgs84.pk:
            geometry, _ = transform_geojson(geometry, wgs84, layer.crs)
        feature = Feature.objects.create(
            district_id=layer.district_id,
            layer=layer,
            properties={"area_m2": shape["area_m2"], "change": shape["change"], "between": between},
            origin=Feature.Origin.DERIVED,
            created_by=user,
            updated_by=user,
        )
        geo.write_geometry(feature, geometry)
        made.append(feature)
    kinds = _classify([f.pk for f in made], project) if made else {}
    summary = dict.fromkeys(KINDS, 0)
    for feature in made:
        kind = kinds[feature.pk]
        summary[kind] += 1
        feature.properties = {**feature.properties, "kind": KINDS[kind]}
        feature.save(update_fields=["properties"])
    return DetectionRun.objects.create(
        district_id=project.district_id,
        project=project,
        before=before,
        after=after,
        layer=layer,
        found=len(made),
        summary=summary,
        started_by=user,
    )

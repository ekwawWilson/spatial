"""Checklist instances, automatic metrics and the readiness score.

Metrics are computed from the data each time they're asked for, so the score
follows imports, edits and field verification without a separate refresh.

Coverage is measured on a grid of about 100 cells laid over the planning
area: the share of the area (by cell area, clipped to the boundary) whose
cells hold at least one of the layer's features. That works the same for
points, lines and polygons (buildings never cover 90% of the ground, but a
building survey can reach 90% of the cells). The grid is laid out in Web
Mercator; it is a measure of spread, not a survey quantity.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from core.models import User
from projects import boundary as boundaries
from projects.models import Layer, PlanProject

from .models import Item, Template, TemplateItem

COPIED_FIELDS = (
    "group",
    "key",
    "title",
    "description",
    "kind",
    "domain",
    "geometry_type",
    "rules",
    "order",
)
GRID_CELLS = 100
DONE = (Item.Status.READY, Item.Status.VERIFIED)


def template_for(district_id: int) -> Template | None:
    """The district's own template, else the platform default."""
    return (
        Template.objects.filter(district_id=district_id).first()
        or Template.objects.filter(district__isnull=True).order_by("id").first()
    )


def ensure_items(project: PlanProject) -> None:
    """Gives a project its checklist (a copy of the template) the first time."""
    if project.checklist_items.exists():
        return
    template = template_for(project.district_id)
    if template is None:
        return
    Item.objects.bulk_create(
        [
            Item(
                district_id=project.district_id,
                project=project,
                **{name: getattr(source, name) for name in COPIED_FIELDS},
            )
            for source in template.items.all()
        ]
    )


def add_missing_items(project: PlanProject) -> int:
    """Adds template items the project doesn't have yet (e.g. added to the
    template later). Existing items are never changed."""
    template = template_for(project.district_id)
    if template is None:
        return 0
    have = set(project.checklist_items.values_list("key", flat=True))
    new = [
        Item(
            district_id=project.district_id,
            project=project,
            **{n: getattr(s, n) for n in COPIED_FIELDS},
        )
        for s in template.items.all()
        if s.key not in have
    ]
    Item.objects.bulk_create(new)
    return len(new)


@transaction.atomic
def customise_template(district_id: int) -> Template:
    """The district's own template, created as a copy of the default if needed."""
    own = Template.objects.filter(district_id=district_id).first()
    if own:
        return own
    default = Template.objects.filter(district__isnull=True).order_by("id").first()
    own = Template.objects.create(district_id=district_id, name="District checklist")
    if default:
        TemplateItem.objects.bulk_create(
            [
                TemplateItem(template=own, **{n: getattr(s, n) for n in COPIED_FIELDS})
                for s in default.items.all()
            ]
        )
    return own


# --- Metrics ---------------------------------------------------------------------------


def auto_link(item: Item, layers: list[Layer]) -> None:
    """Links an unlinked layer item to the project layer named like it (the
    import and draw actions create the layer under the item's title)."""
    if item.kind != "layer" or item.linked_layer_id:
        return
    match = [layer for layer in layers if layer.name.strip().lower() == item.title.strip().lower()]
    if len(match) == 1:
        item.linked_layer = match[0]
        item.save(update_fields=["linked_layer", "updated_at"])


def required_fields(layer: Layer) -> list[str]:
    """Fields counted for attribute completeness: the required ones, or all of
    them if none is marked required."""
    fields = [f for f in layer.schema if isinstance(f, dict) and f.get("name")]
    required = [f["name"] for f in fields if f.get("required")]
    return required or [f["name"] for f in fields]


def layer_metrics(layer: Layer, boundary_feature_id: int | None) -> dict[str, Any]:
    names = required_fields(layer)
    filled_sql = (
        " + ".join("count(*) FILTER (WHERE coalesce(properties ->> %s, '') <> '')" for _ in names)
        or "0"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT count(*), count(*) FILTER (WHERE verified), max(updated_at), {filled_sql}"  # noqa: S608 - placeholders only
            " FROM projects_feature WHERE layer_id = %s",
            [*names, layer.pk],
        )
        count, verified, newest, filled = cursor.fetchone()
        coverage = None
        if boundary_feature_id is not None and count:
            cursor.execute(
                """
                WITH b AS (
                    SELECT ST_Transform(geom_4326, 3857) AS g FROM projects_feature
                    WHERE id = %s AND geom_4326 IS NOT NULL AND ST_Area(geom_4326) > 0
                ),
                cells AS (
                    SELECT ST_Intersection(c.geom, b.g) AS part
                    FROM b, ST_SquareGrid(sqrt(ST_Area(b.g) / %s), b.g) AS c
                    WHERE ST_Intersects(c.geom, b.g)
                )
                SELECT sum(ST_Area(part)),
                       sum(ST_Area(part)) FILTER (WHERE EXISTS (
                           SELECT 1 FROM projects_feature f
                           WHERE f.layer_id = %s
                             AND ST_Intersects(f.geom_4326, ST_Transform(part, 4326))))
                FROM cells
                """,
                [boundary_feature_id, GRID_CELLS, layer.pk],
            )
            total, covered = cursor.fetchone()
            if total:
                coverage = 100.0 * (covered or 0) / total
    return {
        "layer": layer.pk,
        "layer_name": layer.name,
        "feature_count": count,
        "coverage": coverage,
        "attributes": 100.0 * filled / (count * len(names)) if count and names else None,
        "attribute_fields": names,
        "newest": newest.isoformat() if newest else None,
        "age_days": (timezone.now() - newest).days if newest else None,
        "verified": 100.0 * verified / count if count else None,
    }


@dataclass
class Evaluation:
    metrics: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rules_met(self) -> bool:
        return all(check["ok"] for check in self.checks)

    def check(self, ok: bool, label: str, problem: str) -> None:
        self.checks.append({"ok": ok, "label": label, "problem": None if ok else problem})


def _pct(value: float | None) -> str:
    return "none" if value is None else f"{value:.0f}%"


def evaluate(
    item: Item, boundary_report: dict[str, Any], boundary_feature_id: int | None
) -> Evaluation:
    """Metrics and completion-rule checks for one item."""
    rules = item.rules or {}
    result = Evaluation()
    if item.kind == "boundary":
        result.metrics = {
            "exists": boundary_report.get("exists", False),
            "status": boundary_report.get("status"),
            "valid": boundary_report.get("valid"),
            "area_ha": boundary_report.get("area_ha"),
            "overlaps": sum(
                1 for n in boundary_report.get("neighbours", []) if n["kind"] == "overlap"
            ),
        }
        result.check(
            bool(boundary_report.get("exists")), "Boundary drawn", "No planning-area boundary yet."
        )
        if boundary_report.get("exists"):
            result.check(
                bool(boundary_report.get("valid")),
                "Valid shape",
                f"The boundary is invalid: {boundary_report.get('invalid_reason')}.",
            )
        wanted = rules.get("boundary_status")
        if wanted:
            order = ["draft", "agreed", "approved"]
            status = boundary_report.get("status") or "draft"
            result.check(
                order.index(status) >= order.index(wanted),
                f"Boundary {wanted}",
                f"The boundary is {status}; it must be {wanted}.",
            )
        if rules.get("no_overlaps"):
            result.check(
                result.metrics["overlaps"] == 0,
                "No overlaps",
                "The boundary overlaps a neighbouring planning area.",
            )
        return result

    if item.kind != "layer":
        return result
    if item.linked_layer is None:
        result.check(False, "Layer linked", "No layer linked yet: import, draw or pick one.")
        return result
    m = layer_metrics(item.linked_layer, boundary_feature_id)
    result.metrics = m
    if "min_features" in rules:
        result.check(
            m["feature_count"] >= rules["min_features"],
            f"At least {rules['min_features']} feature(s)",
            f"{m['feature_count']} feature(s); needs {rules['min_features']}.",
        )
    if "min_coverage" in rules:
        if boundary_feature_id is None:
            result.check(
                False,
                f"Coverage ≥ {rules['min_coverage']}%",
                "Coverage needs the planning-area boundary.",
            )
        else:
            result.check(
                (m["coverage"] or 0) >= rules["min_coverage"],
                f"Coverage ≥ {rules['min_coverage']}%",
                f"Covers {_pct(m['coverage'])} of the planning area;"
                f" needs {rules['min_coverage']}%.",
            )
    if "min_attributes" in rules and m["attribute_fields"]:
        result.check(
            (m["attributes"] or 0) >= rules["min_attributes"],
            f"Attributes ≥ {rules['min_attributes']}%",
            f"Attributes {_pct(m['attributes'])} filled; needs {rules['min_attributes']}%.",
        )
    if "max_age_days" in rules:
        age = m["age_days"]
        result.check(
            age is not None and age <= rules["max_age_days"],
            f"Updated within {rules['max_age_days']} days",
            "No data yet."
            if age is None
            else f"Newest data is {age} days old; limit {rules['max_age_days']}.",
        )
    if "min_verified" in rules:
        result.check(
            (m["verified"] or 0) >= rules["min_verified"],
            f"Verified in the field ≥ {rules['min_verified']}%",
            f"{_pct(m['verified'])} verified in the field; needs {rules['min_verified']}%.",
        )
    return result


def item_json(item: Item, evaluation: Evaluation, today: date) -> dict[str, Any]:
    complete = item.status in DONE and evaluation.rules_met
    problems = [c["problem"] for c in evaluation.checks if not c["ok"]]
    blockers = []
    if item.status in DONE and problems:
        blockers.append(
            "Marked " + item.get_status_display().lower() + ", but: " + " ".join(problems)
        )
    if not complete and item.due_date and item.due_date < today:
        blockers.append(f"Overdue since {item.due_date.isoformat()}.")
    if not complete and item.kind == "boundary":
        blockers.append("The planning area is needed before most other items can be measured.")
    return {
        "id": item.pk,
        "group": item.group,
        "key": item.key,
        "title": item.title,
        "description": item.description,
        "kind": item.kind,
        "domain": item.domain,
        "geometry_type": item.geometry_type,
        "rules": item.rules,
        "status": item.status,
        "owner": item.owner_id,
        "owner_name": item.owner.get_full_name() or item.owner.email if item.owner else None,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "notes": item.notes,
        "linked_layer": item.linked_layer_id,
        "attachments": [
            {"id": a.pk, "name": a.name, "size": a.size, "uploaded_at": a.uploaded_at.isoformat()}
            for a in item.attachments.all()
        ],
        "metrics": evaluation.metrics,
        "checks": evaluation.checks,
        "rules_met": evaluation.rules_met,
        "complete": complete,
        "blockers": blockers,
    }


def checklist(project: PlanProject) -> dict[str, Any]:
    """The project's checklist with metrics, score, per-group progress and blockers."""
    ensure_items(project)
    items = list(
        project.checklist_items.select_related("owner", "linked_layer", "linked_layer__crs")
        .prefetch_related("attachments")
        .order_by("group", "order", "id")
    )
    layers = list(project.layers.all())
    for item in items:
        auto_link(item, layers)
    report = boundaries.report(project)
    boundary_feature_id = project.boundary_feature_id if report.get("exists") else None
    today = timezone.localdate()
    rows = [item_json(item, evaluate(item, report, boundary_feature_id), today) for item in items]
    groups = []
    for value, label in Item._meta.get_field("group").choices or []:
        in_group = [r for r in rows if r["group"] == value]
        if in_group:
            groups.append(
                {
                    "group": value,
                    "label": label,
                    "total": len(in_group),
                    "complete": sum(r["complete"] for r in in_group),
                }
            )
    complete = sum(r["complete"] for r in rows)
    return {
        "project": project.pk,
        "project_name": project.name,
        "score": round(100 * complete / len(rows)) if rows else 0,
        "complete": complete,
        "total": len(rows),
        "groups": groups,
        "items": rows,
        "blockers": [
            {"item": r["id"], "title": r["title"], "problem": problem}
            for r in rows
            for problem in r["blockers"]
        ],
    }


def status_problems(item: Item, target: str, user_can_verify: bool) -> list[str]:
    """Why an item can't move to `target` (empty if it can)."""
    if target == Item.Status.VERIFIED and not user_can_verify:
        return ["Only a district administrator can mark an item verified."]
    if item.status == Item.Status.VERIFIED and not user_can_verify:
        return ["Only a district administrator can change a verified item."]
    if target in DONE:
        project = item.project
        report = boundaries.report(project)
        boundary_feature_id = project.boundary_feature_id if report.get("exists") else None
        evaluation = evaluate(item, report, boundary_feature_id)
        return [c["problem"] for c in evaluation.checks if not c["ok"]]
    return []


def create_layer_for(item: Item, user: User) -> Layer:
    """A new layer for a layer item, named after it, in its domain; linked to it."""
    from projects import styles

    project = item.project
    name = item.title
    taken = set(project.layers.values_list("name", flat=True))
    n = 2
    while name in taken:
        name = f"{item.title} ({n})"
        n += 1
    top = max((layer.order for layer in project.layers.all()), default=0)
    layer = Layer.objects.create(
        district_id=project.district_id,
        project=project,
        name=name,
        domain=item.domain or "other",
        geometry_type=item.geometry_type or "polygon",
        crs=project.crs,
        schema=[{"name": "name", "label": "Name", "type": "text", "required": False}],
        style=styles.default_style(),
        order=top + 1,
        created_by=user,
    )
    item.linked_layer = layer
    item.save(update_fields=["linked_layer", "updated_at"])
    return layer

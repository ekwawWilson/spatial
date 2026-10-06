"""Running the procedures, keeping what people decided, and summarising."""

import traceback
from collections import Counter
from functools import partial
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from core.models import User
from projects.models import Feature, Layer, PlanProject

from . import procedures
from .models import LayerRole, Relationship, Run
from .registry import LINK_TYPES, PROCEDURES, ROLE_BY_CODE, ROLES, TYPE_BY_CODE


def roles_of(project: PlanProject) -> procedures.Roles:
    return {r.role: r for r in LayerRole.objects.filter(project=project).select_related("layer")}


def suggest_roles(project: PlanProject) -> dict[str, int | None]:
    """A likely layer for each role, from layer names, domains and geometry.
    A layer is suggested for one role at most."""
    layers = list(project.layers.all())
    taken: set[int] = set()
    result: dict[str, int | None] = {}
    for role in ROLES:
        match = None
        for layer in layers:
            if layer.pk in taken or layer.geometry_type not in role.geometry:
                continue
            name = layer.name.lower()
            if any(hint in name for hint in role.hints):
                match = layer
                break
        result[role.code] = match.pk if match else None
        if match:
            taken.add(match.pk)
    return result


# --- Reconciling ---------------------------------------------------------------------------------


def reconcile(
    project: PlanProject,
    link_type: str,
    candidates: list[procedures.Candidate],
    scope: procedures.Scope,
    *,
    scoped_by_subject: bool = True,
) -> dict[str, int]:
    """Makes the stored links of one type match the candidates, changing as
    little as possible, and never touching a link a person has decided on
    (confirmed or rejected). Returns counts."""
    existing = Relationship.objects.filter(project=project, type=link_type)
    if scope is not None and scoped_by_subject:
        existing = existing.filter(subject_id__in=scope)
    decided: set[tuple[str, int, int | None, str]] = set()
    machine: dict[tuple[str, int, int | None, str], Relationship] = {}
    for link in existing:
        key = (link.type, link.subject_id, link.object_id, link.rule)
        if link.decided_at is not None:
            decided.add(key)
        else:
            machine[key] = link
    now = timezone.now()
    counts = {"found": len(candidates), "added": 0, "updated": 0, "removed": 0, "kept": 0}
    new: list[Relationship] = []
    seen: set[tuple[str, int, int | None, str]] = set()
    for candidate in candidates:
        key = candidate.key
        if key in seen:
            continue
        seen.add(key)
        if key in decided:
            counts["kept"] += 1
            continue
        stored = machine.get(key)
        if stored is None:
            new.append(
                Relationship(
                    district_id=project.district_id,
                    project=project,
                    type=candidate.type,
                    subject_id=candidate.subject,
                    object_id=candidate.object,
                    rule=candidate.rule,
                    method=candidate.method,
                    confidence=candidate.confidence,
                    details=candidate.details,
                    checked_at=now,
                )
            )
        elif (stored.method, round(stored.confidence, 3), stored.details) != (
            candidate.method,
            round(candidate.confidence, 3),
            candidate.details,
        ):
            stored.method, stored.confidence, stored.details = (
                candidate.method,
                candidate.confidence,
                candidate.details,
            )
            stored.checked_at = now
            stored.save(update_fields=["method", "confidence", "details", "checked_at"])
            counts["updated"] += 1
    Relationship.objects.bulk_create(new, batch_size=1000)
    counts["added"] = len(new)
    gone = [link.pk for key, link in machine.items() if key not in seen]
    if gone:
        Relationship.objects.filter(pk__in=gone).delete()
    counts["removed"] = len(gone)
    return counts


# --- Running -------------------------------------------------------------------------------------


def _run_procedure(
    name: str, project: PlanProject, roles: procedures.Roles, scope: procedures.Scope
) -> dict[str, list[procedures.Candidate]]:
    if name == "rules":
        return procedures.rules(roles, scope, project.district_id, project.pk)
    function = getattr(procedures, name)
    result: dict[str, list[procedures.Candidate]] = function(roles, scope)
    return result


def run_project(
    project: PlanProject,
    trigger: str,
    user: User | None = None,
    *,
    scope: procedures.Scope = None,
) -> Run:
    """Runs every procedure in order, then the totals. `scope` limits the
    property-based links to those properties (after an edit). All or nothing:
    if a procedure fails, no links change and the run records why."""
    run = Run.objects.create(
        district_id=project.district_id, project=project, trigger=trigger, started_by=user
    )
    report: dict[str, Any] = {}
    try:
        with transaction.atomic():
            run.summary = _run_all(project, scope, report)
        run.status = Run.Status.DONE
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then raised
        run.status = Run.Status.FAILED
        run.error = f"{exc}\n{traceback.format_exc(limit=3)}"
        run.report = report
        run.finished_at = timezone.now()
        run.save()
        raise
    run.report = report
    run.finished_at = timezone.now()
    run.save()
    return run


def _run_all(
    project: PlanProject, scope: procedures.Scope, report: dict[str, Any]
) -> dict[str, Any]:
    roles = roles_of(project)
    for name, _ in PROCEDURES:
        if name == "aggregation":
            continue
        missing = [ROLE_BY_CODE[r].label for r in procedures.REQUIRES[name] if r not in roles]
        if missing:
            report[name] = {"skipped": "Not set: " + ", ".join(missing) + "."}
            continue
        results = _run_procedure(name, project, roles, scope)
        report[name] = {}
        for link_type, candidates in results.items():
            # Links that don't start from a property are always worked out in full.
            by_subject = TYPE_BY_CODE[link_type].subject == "properties"
            report[name][link_type] = reconcile(
                project, link_type, candidates, scope if by_subject else None
            )
    # Link types whose layers are no longer mapped: remove what machines made.
    for link in LINK_TYPES:
        needed = {link.subject, link.object} - {""}
        if link.code == "violates":
            needed = {"properties", "parcels"}
        if not needed <= set(roles):
            removed, _ = Relationship.objects.filter(
                project=project, type=link.code, decided_at__isnull=True
            ).delete()
            if removed:
                report.setdefault("unmapped", {})[link.code] = removed
    return aggregate(project, roles)


def label_of(feature_id: int, properties: dict[str, Any] | None, config: dict[str, Any]) -> str:
    """A short name for a feature: its configured name or id field, else a
    field that looks like a name or an id, else its first text value, else
    its number."""
    properties = properties or {}
    for key in ("name_field", "id_field"):
        value = properties.get(config.get(key, ""))
        if value not in (None, ""):
            return str(value)
    names = sorted(properties)
    likely = (
        [k for k in names if k.lower() == "name"]
        + [
            k
            for k in names
            if k.lower().endswith(("_id", "_no", "_code")) or k.lower() in ("id", "code")
        ]
        + [k for k in names if "name" in k.lower()]
    )
    for key in likely:
        if properties[key] not in (None, ""):
            return str(properties[key])
    for key in names:
        if isinstance(properties[key], str) and properties[key].strip():
            return str(properties[key])
    return f"#{feature_id}"


def aggregate(project: PlanProject, roles: procedures.Roles) -> dict[str, Any]:
    """Totals for the project and for each community: the baseline a plan
    starts from."""
    links = Relationship.objects.filter(project=project, status=Relationship.Status.ACTIVE)
    properties = roles.get("properties")
    total = Feature.objects.filter(layer_id=properties.layer_id).count() if properties else 0

    def subjects(link_type: str) -> set[int]:
        return set(links.filter(type=link_type).values_list("subject_id", flat=True))

    in_flood, on_road, drained, permitted = (
        subjects("affected_by"),
        subjects("served_by"),
        subjects("connected_to"),
        subjects("has_permit"),
    )
    breaches = list(links.filter(type="violates").values_list("subject_id", "rule"))
    violators = {s for s, _ in breaches}
    community_of = dict(links.filter(type="belongs_to").values_list("subject_id", "object_id"))
    mapped = set(roles)

    def block(members: set[int] | None) -> dict[str, Any]:
        def count(group: set[int]) -> int:
            return len(group if members is None else group & members)

        size = total if members is None else len(members)
        data: dict[str, Any] = {"properties": size}
        if "flood_risk" in mapped:
            data["in_flood_area"] = count(in_flood)
        if "streets" in mapped:
            data["without_road_access"] = size - count(on_road)
        if "drains" in mapped:
            data["without_drain"] = size - count(drained)
        if "permits" in mapped:
            data["with_permit"] = count(permitted)
        if "parcels" in mapped:
            data["with_violations"] = count(violators)
            data["violations"] = dict(
                Counter(rule for s, rule in breaches if members is None or s in members)
            )
        return data

    summary: dict[str, Any] = {"project": block(None), "communities": []}
    if "communities" in roles:
        layer = roles["communities"]
        facilities = Counter(
            links.filter(type="contains_infrastructure").values_list("subject_id", flat=True)
        )
        for cid, props in Feature.objects.filter(layer_id=layer.layer_id).values_list(
            "id", "properties"
        ):
            members = {s for s, c in community_of.items() if c == cid}
            summary["communities"].append(
                {
                    "feature": cid,
                    "name": label_of(cid, props, layer.config),
                    **block(members),
                    **({"facilities": facilities.get(cid, 0)} if "facilities" in mapped else {}),
                }
            )
        summary["communities"].sort(key=lambda row: row["name"])
        summary["project"]["in_no_community"] = total - len(community_of)
    if "facilities" in roles and "population" in roles:
        served: dict[int, float] = {}
        for unit, details in links.filter(type="serves").values_list("object_id", "details"):
            value = (details or {}).get("population")
            if unit is not None and isinstance(value, int | float):
                served[unit] = float(value)
        summary["project"]["population_served"] = round(sum(served.values()))
    if "projects" in roles and "needs" in roles:
        needs_layer = roles["needs"].layer_id
        addressed = set(links.filter(type="addresses").values_list("object_id", flat=True))
        summary["project"]["needs"] = Feature.objects.filter(layer_id=needs_layer).count()
        summary["project"]["needs_addressed"] = len(addressed)
    return summary


def latest_summary(project: PlanProject) -> dict[str, Any] | None:
    run = Run.objects.filter(project=project, status=Run.Status.DONE).first()
    if run is None:
        return None
    return {"at": run.finished_at.isoformat() if run.finished_at else None, **run.summary}


# --- After an edit ---------------------------------------------------------------------------

PENDING_SECONDS = 20


def roles_of_layer(layer_id: int) -> list[tuple[int, str]]:
    """(project, role) pairs a layer plays; cached briefly, because this is
    asked on every feature save."""
    key = f"relations.layer-roles.{layer_id}"
    cached: list[tuple[int, str]] | None = cache.get(key)
    if cached is None:
        cached = list(LayerRole.objects.filter(layer_id=layer_id).values_list("project_id", "role"))
        cache.set(key, cached, 60)
    return cached


def forget_layer_roles(layer_id: int) -> None:
    cache.delete(f"relations.layer-roles.{layer_id}")


def feature_changed(feature: Feature) -> None:
    """Queues a refresh after a feature is saved or deleted. A property is
    refreshed on its own; a change to anything else (a street, a flood area)
    can move many links, so the whole project is refreshed. Bursts of edits
    (an import) collapse into one refresh."""
    from .tasks import refresh_project

    for project_id, role in roles_of_layer(feature.layer_id):
        single = role == "properties" and feature.pk is not None
        marker = f"relations.pending.{project_id}.{feature.pk if single else 'all'}"
        if not cache.add(marker, 1, PENDING_SECONDS):
            continue  # one is already on its way
        district_id, feature_id = feature.district_id, feature.pk if single else None
        transaction.on_commit(
            partial(
                refresh_project.apply_async,
                args=[project_id, district_id, feature_id],
                countdown=PENDING_SECONDS,
            )
        )


def layer_of_role(project: PlanProject, role: str) -> Layer | None:
    row = LayerRole.objects.filter(project=project, role=role).select_related("layer").first()
    return row.layer if row else None

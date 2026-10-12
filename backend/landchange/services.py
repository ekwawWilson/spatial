"""Land applications: their numbers, the steps and their dates, the owners
of abutting land, and writing an approved re-zoning to the map."""

import json
from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction

from core.models import User
from permits.models import Counter
from projects.models import Feature, PlanProject
from relations import procedures, zoning
from relations import services as relations

from . import registry
from .models import Application, Comment

Status = Application.Status
OPEN = (Status.RECEIVED, Status.DEFERRED)
# Parcels this close are abutting: drawn boundaries seldom meet exactly.
ABUT_M = 0.5
ZONE_FIELD = "land_use"


def next_number(district_id: int, district_code: str, kind: str, year: int) -> str:
    spec = registry.KIND_BY_CODE[kind]
    with transaction.atomic():
        counter, _ = Counter.objects.select_for_update().get_or_create(
            district_id=district_id, kind=f"land_{spec.prefix.lower()}", year=year
        )
        counter.last += 1
        counter.save(update_fields=["last"])
    return f"{district_code}/{spec.prefix}/{year}/{counter.last:04d}"


# --- The parcels ---------------------------------------------------------------------------------


def _label(feature_id: int, properties: dict[str, Any], id_field: str) -> str:
    return str(properties.get(id_field) or f"#{feature_id}")


def parcel_fields(project: PlanProject) -> dict[str, str]:
    """The names of the parcel layer's id, owner and zone fields."""
    role = relations.roles_of(project).get("parcels")
    config = role.config if role else {}
    return {
        "id": str(config.get("id_field", "parcel_id")),
        "owner": str(config.get("owner_field", "owner")),
        "zone": str(config.get("zone_field", ZONE_FIELD)),
    }


def check_parcels(project: PlanProject, ids: list[int]) -> list[int]:
    """The ids, where each is an area feature of this project."""
    found = set(
        Feature.objects.filter(pk__in=ids, layer__project=project).values_list("pk", flat=True)
    )
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValidationError(
            {"parcels": [f"Not on this project's map: {', '.join(map(str, missing))}."]}
        )
    return list(dict.fromkeys(ids))


def parcels(application: Application) -> list[dict[str, Any]]:
    """The application's parcels as they are on the map now."""
    ids = [int(i) for i in application.parcels]
    if not ids:
        return []
    fields = parcel_fields(application.project)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, properties, ST_Area(geom_4326::geography) FROM projects_feature"
            " WHERE id = ANY(%s) ORDER BY id",
            [ids],
        )
        rows = cursor.fetchall()
    return [
        {
            "id": pk,
            "label": _label(pk, procedures._obj(props), fields["id"]),
            "zone": str(procedures._obj(props).get(fields["zone"]) or ""),
            "area_m2": round(float(area or 0), 1),
        }
        for pk, props, area in rows
    ]


def abutting(application: Application) -> list[dict[str, Any]]:
    """The parcels that touch the application's land (r.33(8)): their owners
    are the ones to be given notice. Looked for in the layer each parcel is in."""
    ids = [int(i) for i in application.parcels]
    if not ids:
        return []
    fields = parcel_fields(application.project)
    sql = (
        "SELECT DISTINCT o.id, o.properties, ST_Area(o.geom_4326::geography)"
        " FROM projects_feature s JOIN projects_feature o"
        " ON o.layer_id = s.layer_id AND o.id <> ALL(%s)"
        " AND o.geom_4326 && ST_Expand(s.geom_4326, %s)"
        " AND ST_DWithin(s.geom_4326::geography, o.geom_4326::geography, %s)"
        " WHERE s.id = ANY(%s) ORDER BY o.id LIMIT 500"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, [ids, procedures._degrees(ABUT_M), ABUT_M, ids])
        rows = cursor.fetchall()
    out = []
    for pk, raw, area in rows:
        props = procedures._obj(raw)
        out.append(
            {
                "id": pk,
                "label": _label(pk, props, fields["id"]),
                "owner": str(props.get(fields["owner"]) or ""),
                "area_m2": round(float(area or 0), 1),
            }
        )
    return out


# --- Steps and their dates -----------------------------------------------------------------------


def step_date(application: Application, code: str) -> date | None:
    entry = application.steps.get(code)
    return date.fromisoformat(entry["on"]) if entry else None


def comments_close(application: Application) -> date | None:
    """The last day for the public's comments (r.33(7), r.54(4))."""
    spec = registry.KIND_BY_CODE[application.kind]
    if not spec.comment_from:
        return None
    start = step_date(application, spec.comment_from)
    return start + timedelta(days=spec.comment_days) if start else None


def _applies(application: Application, when: str, kinds: set[str]) -> bool:
    if when == "comments":
        return bool(kinds)
    if when == "objection":
        return "objection" in kinds
    if when == "approved":
        return application.status == Status.APPROVED
    return True


def _anchor(application: Application, name: str) -> date | None:
    if name == "received":
        return application.received_on
    if name == "comments_close":
        return comments_close(application)
    if name == "decided":
        return application.decided_on
    return step_date(application, name)


def _decision_due(application: Application, kinds: set[str]) -> tuple[date | None, str]:
    spec = registry.KIND_BY_CODE[application.kind]
    if application.deferred_on:
        return (
            application.deferred_on + timedelta(days=registry.DEFERRED_DECISION_DAYS),
            "r.33(17)",
        )
    after = spec.decide_after
    if after == "response" and "objection" not in kinds:
        after = "comments_close"
    start = _anchor(application, after)
    return (start + timedelta(days=spec.decide_days) if start else None), spec.decide_rule


def clocks(application: Application, today: date | None = None) -> list[dict[str, Any]]:
    """Each step that applies: when it is due (where the Regulations set a
    time and it has started to run), when it was done, and whether it is late."""
    today = today or date.today()
    spec = registry.KIND_BY_CODE[application.kind]
    kinds = set(application.comments.values_list("kind", flat=True))
    live = application.status != Status.WITHDRAWN
    out: list[dict[str, Any]] = []

    def add(
        code: str, label: str, rule: str, days: int | None, due: date | None, done: Any
    ) -> None:
        note = application.steps.get(code, {}).get("note", "") if code != "decide" else ""
        out.append(
            {
                "code": code,
                "label": label,
                "rule": rule,
                "days": days,
                "due_on": due.isoformat() if due else None,
                "done_on": done.isoformat() if done else None,
                "note": note,
                "late": bool(done and due and done > due),
                "overdue": bool(live and done is None and due and today > due),
            }
        )

    decided = application.status in (Status.APPROVED, Status.REFUSED)
    for step in spec.steps:
        if step.when == "approved":
            continue
        if not _applies(application, step.when, kinds):
            continue
        start = _anchor(application, step.after) if step.days is not None else None
        due = start + timedelta(days=step.days) if start and step.days is not None else None
        add(step.code, step.label, step.rule, step.days, due, step_date(application, step.code))
    due, rule = _decision_due(application, kinds)
    add("decide", "Decision", rule, None, due, application.decided_on if decided else None)
    for step in spec.steps:
        if step.when != "approved" or application.status != Status.APPROVED:
            continue
        start = _anchor(application, step.after) if step.days is not None else None
        due = start + timedelta(days=step.days) if start and step.days is not None else None
        add(step.code, step.label, step.rule, step.days, due, step_date(application, step.code))
    return out


def next_due(application: Application, today: date | None = None) -> dict[str, Any] | None:
    """The first step not done: one already past its date before any other."""
    if application.status in (Status.REFUSED, Status.WITHDRAWN):
        return None
    waiting = [c for c in clocks(application, today) if c["done_on"] is None]
    return next((c for c in waiting if c["overdue"]), waiting[0] if waiting else None)


def record_step(application: Application, code: str, on: date, note: str = "") -> None:
    spec = registry.KIND_BY_CODE[application.kind]
    step = next((s for s in spec.steps if s.code == code), None)
    if step is None:
        raise ValidationError({"step": [f"Not a step of {spec.label.lower()}."]})
    if application.status == Status.WITHDRAWN:
        raise ValidationError("The application was withdrawn.")
    if step.when == "approved" and application.status != Status.APPROVED:
        raise ValidationError({"step": ["Only once the application is approved."]})
    if on > date.today():
        raise ValidationError({"on": ["That date is in the future."]})
    if on < application.received_on:
        raise ValidationError({"on": ["That is before the application was received."]})
    application.steps = {**application.steps, code: {"on": on.isoformat(), "note": note}}
    application.save(update_fields=["steps", "updated_at"])


# --- Comments ------------------------------------------------------------------------------------


def add_comment(
    application: Application,
    *,
    kind: str,
    name: str,
    contact: str,
    text: str,
    on: date,
    user: User | None,
) -> Comment:
    if kind not in registry.COMMENT_KIND_BY_CODE:
        raise ValidationError({"kind": ["Not a kind of comment."]})
    if on > date.today():
        raise ValidationError({"on": ["That date is in the future."]})
    return Comment.objects.create(
        district_id=application.district_id,
        application=application,
        kind=kind,
        name=name,
        contact=contact,
        text=text,
        received_on=on,
        recorded_by=user,
    )


# --- Change of use: the tests of r.34 ------------------------------------------------------------


def zone_of(application: Application) -> dict[str, Any]:
    """The zone the land is in now, and the uses the district prohibits there."""
    on_map = parcels(application)
    value = application.current_zone or next((p["zone"] for p in on_map if p["zone"]), "")
    national = zoning.match(value) if value else None
    standard = procedures.standard_for(application.district_id, value or None)
    return {
        "value": value,
        "national": national.code if national else None,
        "name": national.name if national else None,
        "prohibited_uses": list(standard.get("prohibited_uses") or []),
    }


def assess(application: Application, answers: dict[str, Any]) -> None:
    """Records the officer's answer to each test: {code: {"met": bool, "note": text}}."""
    if application.kind != "change_of_use":
        raise ValidationError("Only a change of use is assessed against r.34.")
    merged = dict(application.assessment)
    for code, answer in answers.items():
        if code not in registry.USE_TEST_CODES:
            raise ValidationError({"assessment": [f"Not a test of r.34: {code}."]})
        if not isinstance(answer, dict) or not isinstance(answer.get("met"), bool):
            raise ValidationError({"assessment": [f"Say whether {code} is met."]})
        merged[code] = {"met": answer["met"], "note": str(answer.get("note") or "")}
    application.assessment = merged
    application.save(update_fields=["assessment", "updated_at"])


# --- Decisions -----------------------------------------------------------------------------------


def defer(application: Application, on: date, reason: str) -> None:
    """r.33(16): the decision is deferred, and the applicant told why."""
    if application.status != Status.RECEIVED:
        raise ValidationError("Only an application being considered can be deferred.")
    if not reason.strip():
        raise ValidationError({"reason": ["Give the reason: the applicant must be told it."]})
    application.status = Status.DEFERRED
    application.deferred_on = on
    application.defer_reason = reason
    application.save(update_fields=["status", "deferred_on", "defer_reason", "updated_at"])


def decide(
    application: Application, *, approve: bool, on: date, conditions: str, reasons: str
) -> None:
    if application.status not in OPEN:
        raise ValidationError("The application has already been decided or withdrawn.")
    if on > date.today() or on < application.received_on:
        raise ValidationError({"on": ["Not a date the decision could have been made."]})
    if not approve and not reasons.strip():
        raise ValidationError({"reasons": ["A refusal needs its reasons."]})
    if application.kind == "change_of_use":
        missing = [c for c in registry.USE_TEST_CODES if c not in application.assessment]
        if missing:
            raise ValidationError(
                {"assessment": ["Assess every test of r.34 first: " + ", ".join(missing) + "."]}
            )
        failed = [c for c in registry.USE_TEST_CODES if not application.assessment[c]["met"]]
        if approve and failed:
            raise ValidationError(
                {
                    "assessment": [
                        "r.34 allows a change of use only where every test is met. Not met: "
                        + ", ".join(failed)
                        + "."
                    ]
                }
            )
    close = comments_close(application)
    spec = registry.KIND_BY_CODE[application.kind]
    if approve and spec.comment_from and close is None:
        raise ValidationError(
            "The public has not been invited to comment yet: record that step first"
            f" ({spec.comment_rule})."
        )
    if approve and close is not None and on <= close:
        raise ValidationError(
            {"on": [f"The public may comment until {close.isoformat()}: decide after that."]}
        )
    application.status = Status.APPROVED if approve else Status.REFUSED
    application.decided_on = on
    application.conditions = conditions
    application.reasons = reasons
    application.save(update_fields=["status", "decided_on", "conditions", "reasons", "updated_at"])


def withdraw(application: Application) -> None:
    if application.status not in OPEN:
        raise ValidationError("The application has already been decided or withdrawn.")
    application.status = Status.WITHDRAWN
    application.save(update_fields=["status", "updated_at"])


def apply_zone(application: Application, user: User, on: date | None = None) -> dict[str, Any]:
    """Writes an approved re-zoning to the map: the new zone on each parcel
    (one audited change each)."""
    if application.kind != "rezoning" or application.status != Status.APPROVED:
        raise ValidationError("Only an approved re-zoning is written to the map.")
    if not application.proposed_zone:
        raise ValidationError({"proposed_zone": ["The application names no new zone."]})
    ids = [int(i) for i in application.parcels]
    field = parcel_fields(application.project)["zone"]
    values = json.dumps({field: application.proposed_zone})
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE projects_feature f SET properties = f.properties || %s::jsonb,"
            " version = f.version + 1, updated_at = now(), updated_by_id = %s"
            " FROM projects_layer l WHERE l.id = f.layer_id AND l.project_id = %s"
            " AND f.id = ANY(%s) AND NOT f.properties @> %s::jsonb",
            [values, user.pk, application.project_id, ids, values],
        )
        changed = cursor.rowcount
        application.applied_on = on or date.today()
        application.save(update_fields=["applied_on", "updated_at"])
    roles = relations.roles_of(application.project)
    return {
        "parcels_changed": changed,
        "field": field,
        # Where zones are drawn as their own layer, that drawing needs changing too.
        "zoning_layer": "zoning" in roles,
    }

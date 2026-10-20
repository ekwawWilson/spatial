"""What happens to an application, step by step, and the dates the
Regulations set for each step (registry.CLOCKS)."""

import secrets
from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import User
from crs.services import transform_geojson
from projects import geometry as geo
from projects import styles
from projects.models import Feature, Layer, PlanProject
from relations.models import LayerRole

from . import registry
from .models import Application, Challenge, Counter, Event, Inspection

Status = Application.Status
OPEN = (Status.RECEIVED, Status.REVIEW, Status.REPORTED, Status.DEFERRED, Status.GRANTED)
PERMITS_LAYER = "Permit applications"
PERMITS_SCHEMA: list[dict[str, Any]] = [
    {"name": "application_no", "label": "Application number", "type": "text", "required": False},
    {"name": "kind", "label": "Permit", "type": "text", "required": False},
    {"name": "category", "label": "For", "type": "text", "required": False},
    {"name": "proposed_use", "label": "Proposed use", "type": "text", "required": False},
    {"name": "status", "label": "Status", "type": "text", "required": False},
    {"name": "property_id", "label": "Property id", "type": "text", "required": False},
]
PREFIX = {Application.Kind.PLANNING: "PP", Application.Kind.DEVELOPMENT: "DP"}


def event(application: Application, kind: str, on: date, user: User | None, note: str = "") -> None:
    Event.objects.create(
        district_id=application.district_id,
        application=application,
        kind=kind,
        on=on,
        by=user,
        note=note,
    )


# --- Numbering -----------------------------------------------------------------------------------


def next_number(district_id: int, district_code: str, kind: str, year: int) -> str:
    """The next application number: <district>/<DP or PP>/<year>/<0001>. One
    series per district, kind and year (r.44(7)(b))."""
    with transaction.atomic():
        counter, _ = Counter.objects.select_for_update().get_or_create(
            district_id=district_id, kind=kind, year=year
        )
        counter.last += 1
        counter.save(update_fields=["last"])
    return f"{district_code}/{PREFIX[Application.Kind(kind)]}/{year}/{counter.last:04d}"


# --- The site on the map -------------------------------------------------------------------------


def permits_layer(project: PlanProject, user: User | None) -> Layer:
    """The project's layer for application sites: the one in the "permits"
    role, or a new one made for it."""
    role = LayerRole.objects.filter(project=project, role="permits").select_related("layer").first()
    if role is not None:
        return role.layer
    top = max((layer.order for layer in project.layers.all()), default=0)
    name, n = PERMITS_LAYER, 2
    taken = set(project.layers.values_list("name", flat=True))
    while name in taken:
        name, n = f"{PERMITS_LAYER} ({n})", n + 1
    layer = Layer.objects.create(
        district_id=project.district_id,
        project=project,
        name=name,
        domain="G",
        geometry_type="polygon",
        crs=project.crs,
        schema=PERMITS_SCHEMA,
        style={
            **styles.default_style(),
            "fill": "#e4572e",
            "stroke": "#8a2a12",
            "fill_opacity": 0.25,
        },
        order=top + 1,
        created_by=user,
    )
    LayerRole.objects.create(
        district_id=project.district_id,
        project=project,
        role="permits",
        layer=layer,
        config={"property_field": "property_id", "status_field": "status"},
    )
    return layer


def _site_properties(application: Application, layer: Layer) -> dict[str, Any]:
    values = {
        "application_no": application.number,
        "kind": application.get_kind_display(),
        "category": registry.CATEGORY_BY_CODE[application.category].label,
        "proposed_use": application.proposed_use,
        "status": application.get_status_display(),
    }
    names = {f["name"] for f in layer.schema}
    return {k: v for k, v in values.items() if k in names}


def set_site(application: Application, geometry: dict[str, Any], user: User | None) -> Feature:
    """Puts the site (GeoJSON in the permits layer's CRS) on the map: a new
    feature the first time, the same feature moved after that."""
    layer = permits_layer(application.project, user)
    geo.check_geometry(geometry, layer)
    feature = application.site
    if feature is None or feature.layer_id != layer.pk:
        feature = Feature.objects.create(
            district_id=layer.district_id,
            layer=layer,
            properties=_site_properties(application, layer),
            created_by=user,
            updated_by=user,
        )
        application.site = feature
        application.save(update_fields=["site", "updated_at"])
    else:
        feature.version += 1
        feature.updated_by = user
        feature.save(update_fields=["version", "updated_by", "updated_at"])
    geo.write_geometry(feature, geometry)
    return feature


def site_from_feature(application: Application, source: Feature, user: User | None) -> Feature:
    """Uses another feature's shape (a parcel, a building) as the site."""
    native = geo.read_geometries([source.pk], native=True)[source.pk]
    if native is None:
        raise ValidationError({"site_feature": ["That feature has no shape."]})
    layer = permits_layer(application.project, user)
    if source.layer.crs_id != layer.crs_id:
        native, _ = transform_geojson(native, source.layer.crs, layer.crs)
    return set_site(application, native, user)


def sync_site(application: Application, user: User | None) -> None:
    """Keeps the site's attributes on the map in step with the application."""
    feature = application.site
    if feature is None:
        return
    wanted = {**feature.properties, **_site_properties(application, feature.layer)}
    if wanted != feature.properties:
        feature.properties = wanted
        feature.version += 1
        feature.updated_by = user
        feature.save(update_fields=["properties", "version", "updated_by", "updated_at"])


# --- Deadlines -----------------------------------------------------------------------------------


def clocks(application: Application, today: date | None = None) -> list[dict[str, Any]]:
    """Each statutory step: when it is due, when it was done, and whether it is late."""
    today = today or date.today()
    closed = application.status in (Status.WITHDRAWN,)
    out = []
    for clock in registry.CLOCKS:
        due = application.received_on + timedelta(days=clock.days)
        done: date | None = getattr(application, clock.done)
        if clock.code == "issue" and application.status in (Status.GRANTED, Status.ISSUED):
            done = application.issued_on  # granted: the certificate itself is due
        out.append(
            {
                "code": clock.code,
                "label": clock.label,
                "rule": clock.rule,
                "days": clock.days,
                "due_on": due.isoformat(),
                "done_on": done.isoformat() if done else None,
                "late": bool(done and done > due),
                "overdue": not closed and done is None and today > due,
            }
        )
    return out


def next_due(application: Application, today: date | None = None) -> dict[str, Any] | None:
    """The first step not done yet."""
    if application.status not in OPEN:
        return None
    return next((c for c in clocks(application, today) if c["done_on"] is None), None)


def required_documents(application: Application) -> list[dict[str, Any]]:
    """The documents this application must carry, and whether each is there."""
    have: dict[str, int] = {}
    for doc in application.documents.all():
        have[doc.requirement] = have.get(doc.requirement, 0) + 1
    codes = registry.required_documents(
        application.kind, application.category, application.proposed_floors
    )
    codes += [c for c in application.extra_requirements if c not in codes]
    return [
        {
            "code": code,
            "label": registry.REQUIREMENT_BY_CODE[code].label,
            "rule": registry.REQUIREMENT_BY_CODE[code].rule,
            "asked_for": code in application.extra_requirements,
            "submitted": have.get(code, 0),
        }
        for code in codes
        if code in registry.REQUIREMENT_BY_CODE
    ]


# --- Steps ---------------------------------------------------------------------------------------


def _need(application: Application, *allowed: str, doing: str) -> None:
    if application.status not in allowed:
        raise ValidationError(
            f"{doing} isn't possible while the application is "
            f'"{application.get_status_display()}".'
        )


def _not_before(day: date, earlier: date | None, what: str) -> None:
    if earlier is not None and day < earlier:
        raise ValidationError(f"That date is before {what} ({earlier.isoformat()}).")
    if day > date.today():
        raise ValidationError("That date is in the future.")


def acknowledge(application: Application, on: date, user: User) -> None:
    """r.44(6): receipt acknowledged in writing; the application goes to the
    Technical Sub-Committee."""
    _need(application, Status.RECEIVED, doing="Acknowledging")
    _not_before(on, application.received_on, "the application was received")
    application.acknowledged_on = on
    application.status = Status.REVIEW
    application.save(update_fields=["acknowledged_on", "status", "updated_at"])
    event(application, "acknowledged", on, user)
    sync_site(application, user)


def inspect(
    application: Application,
    on: date,
    findings: dict[str, str],
    summary: str,
    user: User,
    purpose: str = Inspection.Purpose.APPLICATION,
) -> Inspection:
    """r.44(7)(f): the site inspection. A completion inspection (r.45(15)) is
    recorded the same way once the permit is issued."""
    if purpose == Inspection.Purpose.COMPLETION:
        _need(application, Status.ISSUED, doing="A completion inspection")
        _not_before(on, application.issued_on, "the permit was issued")
    else:
        _need(application, Status.REVIEW, Status.DEFERRED, doing="A site inspection")
        _not_before(on, application.received_on, "the application was received")
    known = {code for code, _ in registry.INSPECTION_POINTS}
    unknown = sorted(set(findings) - known)
    if unknown:
        raise ValidationError({"findings": [f"Unknown inspection point: {', '.join(unknown)}."]})
    inspection = Inspection.objects.create(
        district_id=application.district_id,
        application=application,
        purpose=purpose,
        inspected_on=on,
        findings={k: str(v) for k, v in findings.items() if str(v).strip()},
        summary=summary,
        inspected_by=user,
    )
    if purpose == Inspection.Purpose.APPLICATION:
        application.inspected_on = on
        application.save(update_fields=["inspected_on", "updated_at"])
    done = "inspected" if purpose == Inspection.Purpose.APPLICATION else "completion"
    event(application, done, on, user, summary)
    return inspection


def submit_report(
    application: Application, recommendation: str, report: str, on: date, user: User
) -> None:
    """r.44(8): the Technical Sub-Committee's findings and recommendation go to
    the Spatial Planning Committee."""
    _need(application, Status.REVIEW, Status.DEFERRED, doing="Sending the report")
    if application.inspected_on is None:
        raise ValidationError("Record the site inspection first (r.44(7)).")
    _not_before(on, application.inspected_on, "the site inspection")
    application.recommendation = recommendation
    application.report = report
    application.reported_on = on
    application.status = Status.REPORTED
    application.save(
        update_fields=["recommendation", "report", "reported_on", "status", "updated_at"]
    )
    event(application, "reported", on, user, f"Recommendation: {recommendation}.")
    sync_site(application, user)


def decide(
    application: Application, decision: str, reasons: str, conditions: str, on: date, user: User
) -> None:
    """r.44(9): the Spatial Planning Committee grants, refuses or defers.
    r.44(13): a refusal or deferral carries its reasons."""
    _need(application, Status.REPORTED, doing="A decision")
    _not_before(on, application.reported_on, "the report went to the committee")
    if decision in ("refuse", "defer") and not reasons.strip():
        raise ValidationError(
            {"reasons": ["Give the reasons: they are written to the applicant (r.44(13))."]}
        )
    application.status = {
        "grant": Status.GRANTED,
        "refuse": Status.REFUSED,
        "defer": Status.DEFERRED,
    }[decision]
    application.reasons = reasons
    application.conditions = conditions if decision == "grant" else ""
    application.decided_on = on
    application.save(update_fields=["status", "reasons", "conditions", "decided_on", "updated_at"])
    event(
        application,
        {"grant": "granted", "refuse": "refused", "defer": "deferred"}[decision],
        on,
        user,
        reasons,
    )
    sync_site(application, user)


def issue(application: Application, on: date, user: User) -> None:
    """r.44(10)-(11), r.45(13): once the permit fee is paid, the certificate is
    issued. Valid for five years."""
    _need(application, Status.GRANTED, doing="Issuing the permit")
    if application.permit_paid_on is None:
        raise ValidationError("Record the permit fee's receipt first (r.44(11)).")
    _not_before(on, application.decided_on, "the decision")
    application.issued_on = on
    try:
        application.expires_on = on.replace(year=on.year + registry.PERMIT_VALID_YEARS)
    except ValueError:  # 29 February
        application.expires_on = on.replace(year=on.year + registry.PERMIT_VALID_YEARS, day=28)
    application.status = Status.ISSUED
    application.token = application.token or secrets.token_urlsafe(24)
    application.save(update_fields=["issued_on", "expires_on", "status", "token", "updated_at"])
    event(application, "issued", on, user)
    sync_site(application, user)


def completion(application: Application, today: date | None = None) -> dict[str, Any] | None:
    """r.45(18): the Certificate of Habitation is issued within 14 days after
    the inspection of the completed development. None until that inspection."""
    inspected = (
        application.inspections.filter(purpose=Inspection.Purpose.COMPLETION)
        .order_by("-inspected_on", "-id")
        .first()
    )
    if inspected is None:
        return None
    today = today or date.today()
    due = inspected.inspected_on + timedelta(days=registry.HABITATION_DAYS)
    issued = application.habitation_on
    return {
        "inspected_on": inspected.inspected_on.isoformat(),
        "due_on": due.isoformat(),
        "issued_on": issued.isoformat() if issued else None,
        "late": bool(issued and issued > due),
        "overdue": issued is None and today > due,
    }


def certify_habitation(application: Application, on: date, user: User) -> None:
    """r.45(15)-(18): the development is complete, inspected, and meets the
    permit's conditions: the Certificate of Habitation is issued."""
    _need(application, Status.ISSUED, doing="A Certificate of Habitation")
    if application.kind != Application.Kind.DEVELOPMENT:
        raise ValidationError("Only a development permit leads to a Certificate of Habitation.")
    if application.habitation_on is not None:
        raise ValidationError("The Certificate of Habitation has already been issued.")
    done = completion(application)
    if done is None:
        raise ValidationError(
            "Record the inspection of the completed development first (r.45(18))."
        )
    _not_before(on, date.fromisoformat(done["inspected_on"]), "the completion inspection")
    application.habitation_on = on
    application.save(update_fields=["habitation_on", "updated_at"])
    event(application, "habitation", on, user)


def withdraw(application: Application, note: str, user: User) -> None:
    _need(application, *OPEN, doing="Withdrawing")
    application.status = Status.WITHDRAWN
    application.save(update_fields=["status", "updated_at"])
    event(application, "withdrawn", date.today(), user, note)
    sync_site(application, user)


# --- Reviews, appeals and renewals ---------------------------------------------------------------

DECIDED = (Status.GRANTED, Status.ISSUED, Status.REFUSED)


def challenge_clock(challenge: Challenge, today: date | None = None) -> dict[str, Any]:
    """When the decision on a review or appeal is due (r.62(3), r.63(8)), and
    whether it was lodged within the Act's time (s.172(2))."""
    today = today or date.today()
    due = challenge.lodged_on + timedelta(days=registry.APPEAL_DECISION_DAYS)
    decided = challenge.application.decided_on
    lodge_by = decided + timedelta(days=registry.APPEAL_WITHIN_DAYS) if decided else None
    return {
        "decide_by": due.isoformat(),
        "overdue": challenge.decided_on is None and today > due,
        "late": bool(challenge.decided_on and challenge.decided_on > due),
        "lodge_by": lodge_by.isoformat() if lodge_by else None,
        "lodged_late": bool(lodge_by and challenge.lodged_on > lodge_by),
    }


def lodge(
    application: Application, kind: str, body: str, on: date, grounds: str, user: User
) -> Challenge:
    if application.status not in DECIDED or application.decided_on is None:
        raise ValidationError("Only a decision can be reviewed or appealed.")
    bodies = dict(registry.CHALLENGE_BODIES.get(kind, ()))
    if body not in bodies:
        raise ValidationError({"body": [f"One of: {', '.join(bodies) or 'review, appeal'}."]})
    if kind == "appeal" and not application.challenges.filter(kind="review").exists():
        raise ValidationError(
            "An appeal follows a review: record the request for review to the Assembly first."
        )
    _not_before(on, application.decided_on, "the decision")
    challenge = Challenge.objects.create(
        district_id=application.district_id,
        application=application,
        kind=kind,
        body=body,
        lodged_on=on,
        grounds=grounds,
        recorded_by=user,
    )
    form, rule = registry.CHALLENGE_FORMS[kind]
    event(application, kind, on, user, f"Form {form} ({rule}) to {bodies[body]}")
    return challenge


def decide_challenge(
    challenge: Challenge, on: date, outcome: str, decision: str, user: User
) -> None:
    if challenge.decided_on is not None:
        raise ValidationError("It has already been decided.")
    if outcome not in Challenge.Outcome.values:
        raise ValidationError({"outcome": ["Not an outcome."]})
    _not_before(on, challenge.lodged_on, "its lodging")
    challenge.decided_on = on
    challenge.outcome = outcome
    challenge.decision = decision
    challenge.save(update_fields=["decided_on", "outcome", "decision"])
    event(
        challenge.application,
        f"{challenge.kind}_decided",
        on,
        user,
        Challenge.Outcome(outcome).label,
    )


def renew(application: Application, on: date, user: User, note: str = "") -> None:
    """A permit not completed in time is renewed by the Spatial Planning
    Committee (Schedule, the development permit's note 2): valid for another
    five years from its expiry, or from the renewal if it had already lapsed."""
    _need(application, Status.ISSUED, doing="Renewing the permit")
    assert application.expires_on is not None
    start = max(application.expires_on, on)
    try:
        application.expires_on = start.replace(year=start.year + registry.PERMIT_VALID_YEARS)
    except ValueError:  # 29 February
        application.expires_on = start.replace(
            year=start.year + registry.PERMIT_VALID_YEARS, day=28
        )
    application.save(update_fields=["expires_on", "updated_at"])
    event(
        application,
        "renewed",
        on,
        user,
        note or f"Valid until {application.expires_on.isoformat()}",
    )

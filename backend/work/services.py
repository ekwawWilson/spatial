"""The everyday view of the district's work (Phase 23): one list of what
needs doing next across every module, who is handling each record, a quick
search by number or name, and what a new district still has to set up.

Nothing here is stored: it is read from the modules' own records and their
statutory clocks each time, so it can never disagree with them."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from basemaps.models import BasemapSource
from committees import registry as committee_registry
from committees import services as committees
from committees.models import Committee, Meeting
from core.models import Membership, Role, User
from crs.models import DistrictCrsSettings
from dataroom.models import DataRoom, InformationRequest
from dataroom.public import due_on as request_due_on
from enforcement import registry as enforcement_registry
from enforcement import services as enforcement
from enforcement.models import Case
from landchange import registry as land_registry
from landchange import services as land
from landchange.models import Application as LandApplication
from permits import registry as permit_registry
from permits import services as permits
from permits.models import Application, Challenge, Fee
from projects.models import PlanProject
from relations.models import StreetName, ZoningScheme
from relations.views import ZoningSchemeSerializer
from revenue.models import Property, RateBand

from .people import officer_json

Can = Callable[[str], bool]
SOON_DAYS = 7  # "this week": due within this many days
MEETING_DAYS = 14  # meetings shown this far ahead
MAX_ITEMS = 300
PER_KIND = 8  # search results of each kind
# Who can be handed a record to deal with.
OFFICER_ROLES = (Role.DISTRICT_ADMIN, Role.PLANNER, Role.FIELD_OFFICER)
# Assigning a record needs the right to work on it.
ASSIGN_PERMISSION = {
    "permit": "permit.process",
    "land": "permit.process",
    "case": "enforcement.act",
}


def officers(district_id: int) -> list[dict[str, Any]]:
    members = Membership.objects.filter(
        district_id=district_id, is_active=True, role__in=OFFICER_ROLES, user__is_active=True
    ).select_related("user")
    out = [{**(officer_json(m.user) or {}), "role": m.role} for m in members]
    return sorted(out, key=lambda o: str(o["name"]).lower())


def _days(due: str | None, today: date) -> int | None:
    return (date.fromisoformat(due) - today).days if due else None


def _item(
    kind: str,
    label: str,
    pk: int,
    number: str,
    title: str,
    step: str,
    due: str | None,
    overdue: bool,
    today: date,
    link: str,
    *,
    project: int | None = None,
    rule: str = "",
    who: str | None = None,
    officer: User | None = None,
    assignable: bool = False,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "kind_label": label,
        "id": pk,
        "project": project,
        "number": number,
        "title": title,
        "who": who,
        "step": step,
        "rule": rule,
        "due_on": due,
        "days": _days(due, today),
        "overdue": overdue,
        "officer": officer_json(officer),
        "assignable": assignable,
        "link": link,
    }


def items(
    district_id: int, can: Can, personal: bool, today: date | None = None
) -> list[dict[str, Any]]:
    """Everything with a next step, the most pressing first: past its date
    (longest late first), then by date, then the steps with no date."""
    today = today or date.today()
    out: list[dict[str, Any]] = []

    if can("permit.view"):
        for a in Application.objects.filter(
            district_id=district_id, status__in=permits.OPEN
        ).select_related("officer"):
            due = permits.next_due(a, today)
            if due is None:
                continue
            out.append(
                _item(
                    "permit",
                    "Permit application",
                    a.pk,
                    a.number,
                    permit_registry.CATEGORY_BY_CODE[a.category].label
                    if a.category in permit_registry.CATEGORY_BY_CODE
                    else a.category,
                    due["label"],
                    due["due_on"],
                    bool(due["overdue"]),
                    today,
                    f"/projects/{a.project_id}/permits/{a.pk}",
                    project=a.project_id,
                    rule=str(due.get("rule") or ""),
                    who=a.applicant_name if personal else None,
                    officer=a.officer,
                    assignable=True,
                )
            )
        for c in Challenge.objects.filter(
            district_id=district_id, decided_on__isnull=True
        ).select_related("application", "application__officer"):
            clock = permits.challenge_clock(c, today)
            out.append(
                _item(
                    "challenge",
                    "Review or appeal",
                    c.application_id,
                    c.application.number,
                    c.get_kind_display(),
                    "Decide the " + c.get_kind_display().lower(),
                    clock["decide_by"],
                    bool(clock["overdue"]),
                    today,
                    f"/projects/{c.application.project_id}/permits/{c.application_id}",
                    project=c.application.project_id,
                    rule="r.62(3)" if c.kind == "review" else "r.63(8)",
                    officer=c.application.officer,
                )
            )

    if can("permit.view"):
        for la in (
            LandApplication.objects.filter(district_id=district_id)
            .exclude(status__in=(LandApplication.Status.REFUSED, LandApplication.Status.WITHDRAWN))
            .select_related("officer")
            .prefetch_related("comments")
        ):
            due = land.next_due(la, today)
            if due is None:
                continue
            spec = land_registry.KIND_BY_CODE.get(la.kind)
            out.append(
                _item(
                    "land",
                    "Land application",
                    la.pk,
                    la.number,
                    spec.label if spec else la.kind,
                    due["label"],
                    due.get("due_on"),
                    bool(due.get("overdue")),
                    today,
                    f"/projects/{la.project_id}/land/{la.pk}",
                    project=la.project_id,
                    rule=str(due.get("rule") or ""),
                    who=la.applicant_name if personal else None,
                    officer=la.officer,
                    assignable=True,
                )
            )

    if can("enforcement.view"):
        for case in (
            Case.objects.filter(district_id=district_id, status__in=enforcement.OPEN)
            .select_related("officer")
            .prefetch_related("notices")
        ):
            step = enforcement.next_action(case, today)
            if step is None:
                continue
            what = enforcement_registry.CONTRAVENTION_BY_CODE.get(case.contravention)
            out.append(
                _item(
                    "case",
                    "Enforcement case",
                    case.pk,
                    case.number,
                    what[0] if what else case.contravention,
                    step["label"],
                    step["due_on"],
                    bool(step["overdue"]),
                    today,
                    f"/projects/{case.project_id}/enforcement/{case.pk}",
                    project=case.project_id,
                    who=case.owner_name if personal and case.owner_name else None,
                    officer=case.officer,
                    assignable=True,
                )
            )

    if can("dataroom.view"):
        for r in InformationRequest.objects.filter(
            district_id=district_id, status=InformationRequest.Status.OPEN
        ):
            due_day = request_due_on(r.received_on)
            out.append(
                _item(
                    "request",
                    "Request for information",
                    r.pk,
                    r.reference,
                    r.subject,
                    "Answer the request",
                    due_day.isoformat(),
                    today > due_day,
                    today,
                    "/data-room",
                    rule="r.64(7)",
                    who=r.name if personal else None,
                )
            )

    if can("permit.view"):
        ahead = today + timedelta(days=MEETING_DAYS)
        for m in Meeting.objects.filter(
            district_id=district_id, held_on__gte=today, held_on__lte=ahead
        ).select_related("committee"):
            clock = committees.notice_clock(m)
            name = committee_registry.COMMITTEES.get(m.committee.kind, m.committee.kind)
            if m.notice_served_on is None:
                step = "Serve the notice of meeting (Form 5)"
                due, overdue = str(clock["serve_by"]), bool(clock["overdue"])
            else:
                step, due, overdue = "Meeting", m.held_on.isoformat(), False
            out.append(
                _item(
                    "meeting",
                    "Committee meeting",
                    m.pk,
                    m.held_on.strftime("%d %b %Y"),
                    name,
                    step,
                    due,
                    overdue,
                    today,
                    f"/committees/{m.pk}",
                    rule="r.6(2)" if m.notice_served_on is None else "",
                )
            )

    if can("project.view"):
        for scheme in ZoningScheme.objects.filter(district_id=district_id):
            for code, deadline in ZoningSchemeSerializer().get_deadlines(scheme).items():
                if deadline["overdue"]:
                    out.append(
                        _item(
                            "zoning",
                            "Zoning scheme",
                            scheme.pk,
                            scheme.name,
                            scheme.name,
                            {
                                "prepare": "Prepare the zoning scheme",
                                "send_to_luspa": "Send a copy to LUSPA",
                                "update": "Update the zoning scheme",
                            }.get(code, code),
                            deadline["due_on"],
                            True,
                            today,
                            f"/projects/{scheme.project_id}/zoning",
                            project=scheme.project_id,
                            rule=str(deadline.get("rule") or ""),
                        )
                    )

    def order(item: dict[str, Any]) -> tuple[int, int]:
        if item["overdue"]:
            return (0, item["days"] if item["days"] is not None else 0)
        if item["days"] is not None:
            return (1, item["days"])
        return (2, 0)

    return sorted(out, key=order)[:MAX_ITEMS]


def summary(rows: list[dict[str, Any]], user: User) -> dict[str, int]:
    return {
        "overdue": sum(1 for r in rows if r["overdue"]),
        "this_week": sum(
            1 for r in rows if not r["overdue"] and r["days"] is not None and r["days"] <= SOON_DAYS
        ),
        "mine": sum(1 for r in rows if r["officer"] and r["officer"]["id"] == user.pk),
        "unassigned": sum(1 for r in rows if r["assignable"] and r["officer"] is None),
        "all": len(rows),
    }


def assign(district_id: int, kind: str, pk: int, officer_id: int | None) -> Any:
    """Hands a record to an officer of the district (or takes it back)."""
    model: Any = {"permit": Application, "land": LandApplication, "case": Case}.get(kind)
    if model is None:
        raise ValidationError({"kind": ["One of: permit, land, case."]})
    record = model.objects.filter(district_id=district_id, pk=pk).first()
    if record is None:
        raise ValidationError({"id": ["No such record in this district."]})
    officer = None
    if officer_id is not None:
        member = (
            Membership.objects.filter(
                district_id=district_id,
                user_id=officer_id,
                is_active=True,
                role__in=OFFICER_ROLES,
            )
            .select_related("user")
            .first()
        )
        if member is None:
            raise ValidationError({"officer": ["Not an officer of this district."]})
        officer = member.user
    record.officer = officer
    record.save(update_fields=["officer", "updated_at"])
    return record


# --- Quick search --------------------------------------------------------------------------------


def search(district_id: int, q: str, can: Can, personal: bool) -> list[dict[str, Any]]:
    """Records whose number or name holds the words typed."""
    q = q.strip()
    if len(q) < 2:
        return []
    out: list[dict[str, Any]] = []

    def add(kind: str, label: str, pk: int, title: str, detail: str, link: str) -> None:
        out.append(
            {
                "kind": kind,
                "kind_label": label,
                "id": pk,
                "title": title,
                "detail": detail,
                "link": link,
            }
        )

    def named(field: str) -> Q:
        return Q(**{f"{field}__icontains": q}) if personal else Q(pk__in=[])

    if can("project.view"):
        for p in PlanProject.objects.filter(district_id=district_id).filter(
            Q(name__icontains=q) | Q(community__icontains=q)
        )[:PER_KIND]:
            add("project", "Project", p.pk, p.name, p.community, f"/projects/{p.pk}")
    if can("permit.view"):
        for a in Application.objects.filter(district_id=district_id).filter(
            Q(number__icontains=q) | Q(proposed_use__icontains=q) | named("applicant_name")
        )[:PER_KIND]:
            add(
                "permit",
                "Permit application",
                a.pk,
                a.number,
                " · ".join(
                    x for x in (a.applicant_name if personal else "", a.get_status_display()) if x
                ),
                f"/projects/{a.project_id}/permits/{a.pk}",
            )
        for la in LandApplication.objects.filter(district_id=district_id).filter(
            Q(number__icontains=q) | named("applicant_name")
        )[:PER_KIND]:
            spec = land_registry.KIND_BY_CODE.get(la.kind)
            add(
                "land",
                "Land application",
                la.pk,
                la.number,
                " · ".join(
                    x
                    for x in (
                        spec.label if spec else la.kind,
                        la.applicant_name if personal else "",
                        la.get_status_display(),
                    )
                    if x
                ),
                f"/projects/{la.project_id}/land/{la.pk}",
            )
    if can("enforcement.view"):
        for case in Case.objects.filter(district_id=district_id).filter(
            Q(number__icontains=q) | Q(description__icontains=q) | named("owner_name")
        )[:PER_KIND]:
            add(
                "case",
                "Enforcement case",
                case.pk,
                case.number,
                case.get_status_display(),
                f"/projects/{case.project_id}/enforcement/{case.pk}",
            )
    if can("dataroom.view"):
        for r in InformationRequest.objects.filter(district_id=district_id).filter(
            Q(reference__icontains=q) | Q(subject__icontains=q) | named("name")
        )[:PER_KIND]:
            add("request", "Request for information", r.pk, r.reference, r.subject, "/data-room")
    if can("revenue.view"):
        for prop in Property.objects.filter(district_id=district_id).filter(
            Q(number__icontains=q)
            | Q(address__icontains=q)
            | Q(valuation_ref__icontains=q)
            | named("owner_name")
        )[:PER_KIND]:
            add(
                "property",
                "Rateable property",
                prop.pk,
                prop.number,
                prop.address,
                f"/projects/{prop.project_id}/rates",
            )
    if can("project.view"):
        for s in StreetName.objects.filter(district_id=district_id, name__icontains=q)[:PER_KIND]:
            add(
                "street",
                "Street name",
                s.pk,
                s.name,
                s.get_status_display(),
                f"/projects/{s.project_id}/addressing",
            )
    return out


# --- Setting up a district -----------------------------------------------------------------------


def setup(district_id: int) -> list[dict[str, Any]]:
    """What a district needs before its staff can work in it, in the order
    to do it, each with where to do it."""
    first = PlanProject.objects.filter(district_id=district_id).order_by("id").first()

    def in_project(page: str) -> str:
        return f"/projects/{first.pk}/{page}" if first else "/projects"

    staff = Membership.objects.filter(district_id=district_id, is_active=True)
    kinds = {
        c.kind
        for c in Committee.objects.filter(district_id=district_id)
        if isinstance(c.members, list) and c.members
    }
    room = DataRoom.objects.filter(district_id=district_id).first()
    steps = [
        (
            "crs",
            "Choose the district's coordinate system",
            DistrictCrsSettings.objects.filter(district_id=district_id).exists(),
            "/crs",
            "New projects start in it; Ghana National Grid unless you choose otherwise.",
        ),
        (
            "staff",
            "Add the planning staff",
            staff.filter(role__in=(Role.PLANNER, Role.FIELD_OFFICER)).exists(),
            "/members",
            "Planners and field officers, each with their role.",
        ),
        (
            "project",
            "Create the first plan project",
            first is not None,
            "/projects",
            "A community or planning area: its map, layers and records.",
        ),
        (
            "basemap",
            "Add a background map",
            BasemapSource.objects.filter(Q(district_id=district_id) | Q(district__isnull=True))
            .filter(is_active=True)
            .exists(),
            "/basemaps",
            "Satellite imagery or a street map under your layers.",
        ),
        (
            "committees",
            "Name the committees' members",
            {"dspc", "tsc"} <= kinds,
            "/committees",
            "The Spatial Planning Committee and its Technical Sub-Committee (r.6-7).",
        ),
        (
            "fees",
            "Set the permit fees",
            Fee.objects.filter(district_id=district_id).exists(),
            in_project("permits"),
            "The processing and permit fees the Assembly charges.",
        ),
        (
            "rates",
            "Set the property rate bands",
            RateBand.objects.filter(district_id=district_id).exists(),
            in_project("rates"),
            "The rate impost per use, for the year's bills.",
        ),
        (
            "dataroom",
            "Open the Public Data Room",
            bool(room and room.is_open),
            "/data-room",
            "Where residents see approved plans and ask for information (r.64).",
        ),
    ]
    return [
        {"code": code, "label": label, "done": bool(done), "link": link, "hint": hint}
        for code, label, done, link, hint in steps
    ]

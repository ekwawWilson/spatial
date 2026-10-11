"""The district's statutory duties in one place: what is open, what is past
its date, and how often the Regulations' time limits are being met. Counted
from the records each time, for the district the request is scoped to."""

from datetime import date, timedelta
from typing import Any

from django.db.models import Q

from dataroom.models import DataRoom, InformationRequest, Publication, RoomDocument
from dataroom.public import ANSWER_WITHIN_DAYS, due_on
from enforcement import services as enforcement
from enforcement.models import Case
from permits import registry as permit_registry
from permits import services as permits
from permits.models import Application
from relations.models import ZoningScheme
from relations.views import ZoningSchemeSerializer

DECISION_DAYS = next(c.days for c in permit_registry.CLOCKS if c.code == "issue")
DUTIES = {
    "prepare": "Prepare the zoning scheme",
    "send_to_luspa": "Send a copy to LUSPA",
    "update": "Update the zoning scheme",
}


def _pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 1) if whole else None


def compliance(district_id: int, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    year_start = date(today.year, 1, 1)

    # --- Permits (r.44) --------------------------------------------------------------------------
    applications = list(
        Application.objects.filter(district_id=district_id).select_related("project")
    )
    open_apps = [a for a in applications if a.status in permits.OPEN]
    by_step = {clock.code: 0 for clock in permit_registry.CLOCKS}
    late: list[dict[str, Any]] = []
    for application in open_apps:
        due = permits.next_due(application, today)
        if due and due["overdue"]:
            by_step[due["code"]] += 1
            late.append(
                {
                    "id": application.pk,
                    "project": application.project_id,
                    "number": application.number,
                    "step": due["label"],
                    "rule": due["rule"],
                    "due_on": due["due_on"],
                    "days_late": (today - date.fromisoformat(due["due_on"])).days,
                }
            )
    decided = [a for a in applications if a.decided_on and a.decided_on >= year_start]
    took = [(a.decided_on - a.received_on).days for a in decided if a.decided_on]
    permits_out: dict[str, Any] = {
        "open": len(open_apps),
        "overdue": len(late),
        "overdue_by_step": by_step,
        "received_this_year": sum(1 for a in applications if a.received_on >= year_start),
        "decided_this_year": len(decided),
        "decided_within_limit_pct": _pct(sum(1 for d in took if d <= DECISION_DAYS), len(took)),
        "average_days_to_decision": round(sum(took) / len(took), 1) if took else None,
        "limit_days": DECISION_DAYS,
        "late": sorted(late, key=lambda row: -row["days_late"])[:50],
    }

    # --- Requests for information (r.64(7)) ------------------------------------------------------
    requests = list(InformationRequest.objects.filter(district_id=district_id))
    open_requests = [r for r in requests if r.status == InformationRequest.Status.OPEN]
    answered = [r for r in requests if r.answered_on and r.answered_on >= year_start]
    requests_out: dict[str, Any] = {
        "open": len(open_requests),
        "overdue": sum(1 for r in open_requests if today > due_on(r.received_on)),
        "answered_this_year": len(answered),
        "answered_within_limit_pct": _pct(
            sum(1 for r in answered if r.answered_on and r.answered_on <= due_on(r.received_on)),
            len(answered),
        ),
        "limit_days": ANSWER_WITHIN_DAYS,
    }

    # --- Enforcement (r.57) ----------------------------------------------------------------------
    cases = list(
        Case.objects.filter(district_id=district_id, status__in=enforcement.OPEN).prefetch_related(
            "notices"
        )
    )
    steps = [(case, enforcement.next_action(case, today)) for case in cases]
    enforcement_out: dict[str, Any] = {
        "open": len(cases),
        "overdue": sum(1 for _case, step in steps if step and step["overdue"]),
        "late": [
            {
                "id": case.pk,
                "project": case.project_id,
                "number": case.number,
                "step": step["label"],
                "due_on": step["due_on"],
            }
            for case, step in steps
            if step and step["overdue"]
        ][:50],
    }

    # --- Zoning schemes (r.29) -------------------------------------------------------------------
    schemes = list(ZoningScheme.objects.filter(district_id=district_id).select_related("project"))
    duties: list[dict[str, Any]] = []
    for scheme in schemes:
        for code, deadline in ZoningSchemeSerializer().get_deadlines(scheme).items():
            if deadline["overdue"]:
                duties.append(
                    {
                        "project": scheme.project_id,
                        "scheme": scheme.name,
                        "duty": DUTIES[code],
                        "rule": deadline["rule"],
                        "due_on": deadline["due_on"],
                    }
                )
    zoning_out: dict[str, Any] = {"schemes": len(schemes), "overdue": len(duties), "late": duties}

    # --- The Public Data Room (r.64) -------------------------------------------------------------
    room = DataRoom.objects.filter(district_id=district_id).first()
    dataroom_out: dict[str, Any] = {
        "is_open": bool(room and room.is_open),
        "published_projects": Publication.objects.filter(district_id=district_id).count(),
        "documents_on_display": RoomDocument.objects.filter(
            district_id=district_id, display_from__lte=today
        )
        .filter(Q(display_until__isnull=True) | Q(display_until__gte=today))
        .count(),
    }

    overdue = (
        len(late) + int(requests_out["overdue"]) + int(enforcement_out["overdue"]) + len(duties)
    )
    return {
        "as_of": today.isoformat(),
        "overdue": overdue,
        "permits": permits_out,
        "requests": requests_out,
        "enforcement": enforcement_out,
        "zoning": zoning_out,
        "dataroom": dataroom_out,
        "week_ahead": _week_ahead(open_apps, today),
    }


def _week_ahead(open_apps: list[Application], today: date) -> list[dict[str, Any]]:
    """Permit steps falling due in the next seven days: what to do this week."""
    soon = today + timedelta(days=7)
    rows = []
    for application in open_apps:
        due = permits.next_due(application, today)
        if due and not due["overdue"] and date.fromisoformat(due["due_on"]) <= soon:
            rows.append(
                {
                    "id": application.pk,
                    "project": application.project_id,
                    "number": application.number,
                    "step": due["label"],
                    "due_on": due["due_on"],
                }
            )
    return sorted(rows, key=lambda row: row["due_on"])[:50]

# ruff: noqa: E501 - the measures read better unbroken
"""The district's periodic return: what its planning authority did in a
quarter or a year, counted from the records, for the Land Use and Spatial
Planning Authority, the Regional Coordinating Council and the Assembly. No
names: numbers, and the statutory time limits met."""

import csv
import io
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Sum

from dataroom.models import InformationRequest
from dataroom.public import due_on
from enforcement import registry as enforcement_registry
from enforcement.models import Case, Notice
from landchange import registry as land_registry
from landchange.models import Application as LandApplication
from permits import registry as permit_registry
from permits.models import Application
from planmaking.models import Consultation, PlanComment, PlanProcess
from revenue.models import BettermentScheme, Bill

DECISION_DAYS = next(c.days for c in permit_registry.CLOCKS if c.code == "issue")
GRANTED = (Application.Status.GRANTED, Application.Status.ISSUED)


def period(
    text: str | None, start: str | None = None, end: str | None = None
) -> tuple[date, date, str]:
    """ "2026-Q3", "2026", or two dates: (first day, last day, label)."""
    if start and end:
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as exc:
            raise ValidationError("Dates are YYYY-MM-DD.") from exc
        if last < first:
            raise ValidationError("The period ends before it starts.")
        return first, last, f"{first.isoformat()} to {last.isoformat()}"
    text = (text or "").strip().upper()
    try:
        if "-Q" in text:
            year_text, quarter_text = text.split("-Q")
            year, quarter = int(year_text), int(quarter_text)
            if not 1 <= quarter <= 4:
                raise ValueError
            first = date(year, 3 * quarter - 2, 1)
            following = date(year + 1, 1, 1) if quarter == 4 else date(year, 3 * quarter + 1, 1)
            return first, following - timedelta(days=1), f"Quarter {quarter} of {year}"
        year = int(text)
        return date(year, 1, 1), date(year, 12, 31), f"The year {year}"
    except ValueError as exc:
        raise ValidationError(
            "Give a period: a year (2026), a quarter (2026-Q3), or from and to dates."
        ) from exc


def _pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 1) if whole else None


def _money(value: Decimal | None) -> str:
    return f"{value or Decimal(0):.2f}"


def build(district_id: int, first: date, last: date, label: str) -> dict[str, Any]:
    within = {"gte": first, "lte": last}

    def between(field: str) -> dict[str, date]:
        return {f"{field}__{k}": v for k, v in within.items()}

    # --- Permits (r.43-46) --------------------------------------------------------------------
    apps = Application.objects.filter(district_id=district_id)
    received = list(apps.filter(**between("received_on")))
    decided = list(apps.filter(**between("decided_on")))
    granted = [a for a in decided if a.status in GRANTED]
    refused = [a for a in decided if a.status == Application.Status.REFUSED]
    took = [(a.decided_on - a.received_on).days for a in decided if a.decided_on]
    by_category = Counter(a.category for a in received)
    permits = {
        "received": len(received),
        "received_by_kind": {
            "development": sum(1 for a in received if a.kind == Application.Kind.DEVELOPMENT),
            "planning": sum(1 for a in received if a.kind == Application.Kind.PLANNING),
        },
        "received_by_category": [
            {
                "category": permit_registry.CATEGORY_BY_CODE[c].label
                if c in permit_registry.CATEGORY_BY_CODE
                else c,
                "count": n,
            }
            for c, n in by_category.most_common()
        ],
        "decided": len(decided),
        "granted": len(granted),
        "refused": len(refused),
        "issued": apps.filter(**between("issued_on")).count(),
        "decided_within_limit_pct": _pct(sum(1 for d in took if d <= DECISION_DAYS), len(took)),
        "average_days_to_decision": round(sum(took) / len(took), 1) if took else None,
        "limit_days": DECISION_DAYS,
    }

    # --- Re-zoning, change of use, subdivision (r.33, r.34, r.54) ----------------------------
    land = LandApplication.objects.filter(district_id=district_id)
    land_received = list(land.filter(**between("received_on")))
    land_decided = list(land.filter(**between("decided_on")))
    land_out = [
        {
            "kind": kind.label,
            "received": sum(1 for a in land_received if a.kind == kind.code),
            "approved": sum(
                1
                for a in land_decided
                if a.kind == kind.code and a.status == LandApplication.Status.APPROVED
            ),
            "refused": sum(
                1
                for a in land_decided
                if a.kind == kind.code and a.status == LandApplication.Status.REFUSED
            ),
        }
        for kind in land_registry.KINDS
    ]

    # --- Enforcement (r.55-58) ----------------------------------------------------------------
    cases = Case.objects.filter(district_id=district_id)
    opened = list(cases.filter(**between("opened_on")))
    closed = list(cases.filter(**between("closed_on")))
    served = list(Notice.objects.filter(district_id=district_id, **between("served_on")))
    enforcement = {
        "cases_opened": len(opened),
        "opened_by_contravention": [
            {"contravention": enforcement_registry.CONTRAVENTION_BY_CODE[c][0], "count": n}
            for c, n in Counter(x.contravention for x in opened).most_common()
            if c in enforcement_registry.CONTRAVENTION_BY_CODE
        ],
        "notices_served": len(served),
        "notices_by_kind": [
            {
                "notice": enforcement_registry.NOTICE_BY_CODE[k].label,
                "form": enforcement_registry.NOTICE_BY_CODE[k].form,
                "count": n,
            }
            for k, n in Counter(x.kind for x in served).most_common()
            if k in enforcement_registry.NOTICE_BY_CODE
        ],
        "cases_closed": len(closed),
        "closed_by_outcome": {
            status: sum(1 for c in closed if c.status == status)
            for status in ("rectified", "enforced", "dropped")
        },
        "cost_recovered": _money(sum((c.cost_recovered or Decimal(0) for c in closed), Decimal(0))),
    }

    # --- Plans and consultation (r.23-27, r.65) -----------------------------------------------
    processes = list(PlanProcess.objects.filter(district_id=district_id).select_related("project"))

    def stepped(process: PlanProcess, code: str) -> bool:
        entry = process.steps.get(code)
        return bool(entry) and first <= date.fromisoformat(entry["on"]) <= last

    plans = {
        "commenced": [p.project.name for p in processes if stepped(p, "commence")],
        "drafts_on_display": [p.project.name for p in processes if stepped(p, "notice")],
        "approved": [p.project.name for p in processes if stepped(p, "approve")],
        "consultations_held": Consultation.objects.filter(
            district_id=district_id, **between("held_on")
        ).count(),
        "comments_received": PlanComment.objects.filter(
            district_id=district_id, **between("received_on")
        ).count(),
    }

    # --- The Public Data Room (r.64) ----------------------------------------------------------
    requests = list(
        InformationRequest.objects.filter(district_id=district_id, **between("received_on"))
    )
    answered = [r for r in requests if r.answered_on]
    data_room = {
        "requests_received": len(requests),
        "answered": len(answered),
        "answered_within_limit_pct": _pct(
            sum(1 for r in answered if r.answered_on and r.answered_on <= due_on(r.received_on)),
            len(answered),
        ),
    }

    # --- Rates and betterment -----------------------------------------------------------------
    bills = Bill.objects.filter(district_id=district_id)
    issued = bills.filter(**between("issued_on"))
    paid_in = bills.filter(**between("last_paid_on"))
    schemes = BettermentScheme.objects.filter(district_id=district_id, **between("completed_on"))
    revenue = {
        "bills_issued": issued.count(),
        "billed": _money(issued.aggregate(t=Sum("amount"))["t"]),
        "paid_on_bills_with_payments": _money(paid_in.aggregate(t=Sum("paid"))["t"]),
        "betterment_schemes_completed": schemes.count(),
    }

    return {
        "period": {"label": label, "from": first.isoformat(), "to": last.isoformat()},
        "permits": permits,
        "land": land_out,
        "enforcement": enforcement,
        "plans": plans,
        "data_room": data_room,
        "revenue": revenue,
    }


def rows(data: dict[str, Any]) -> list[tuple[str, str, str]]:
    """The return as (section, measure, value) lines, for a CSV or a table."""
    p, e, d, r, pl = (
        data["permits"],
        data["enforcement"],
        data["data_room"],
        data["revenue"],
        data["plans"],
    )
    out: list[tuple[str, str, str]] = [
        ("Permits", "Applications received", str(p["received"])),
        ("Permits", "of which development permits", str(p["received_by_kind"]["development"])),
        ("Permits", "of which planning permits", str(p["received_by_kind"]["planning"])),
        ("Permits", "Decided", str(p["decided"])),
        ("Permits", "Granted", str(p["granted"])),
        ("Permits", "Refused", str(p["refused"])),
        ("Permits", "Certificates issued", str(p["issued"])),
        (
            "Permits",
            f"Decided within {p['limit_days']} days (%)",
            "" if p["decided_within_limit_pct"] is None else f"{p['decided_within_limit_pct']:g}",
        ),
        (
            "Permits",
            "Average days to decision",
            "" if p["average_days_to_decision"] is None else f"{p['average_days_to_decision']:g}",
        ),
    ]
    out += [
        ("Permits by category", c["category"], str(c["count"])) for c in p["received_by_category"]
    ]
    for kind in data["land"]:
        out.append(
            (
                kind["kind"],
                "Received / approved / refused",
                f"{kind['received']} / {kind['approved']} / {kind['refused']}",
            )
        )
    out += [
        ("Enforcement", "Cases opened", str(e["cases_opened"])),
        ("Enforcement", "Notices served", str(e["notices_served"])),
        ("Enforcement", "Cases closed", str(e["cases_closed"])),
        (
            "Enforcement",
            "Rectified by the owner / by the Assembly / no contravention",
            f"{e['closed_by_outcome']['rectified']} / {e['closed_by_outcome']['enforced']} / {e['closed_by_outcome']['dropped']}",
        ),
        ("Enforcement", "Cost recovered (GHS)", e["cost_recovered"]),
    ]
    for n in e["notices_by_kind"]:
        form = f" (Form {n['form']})" if n["form"] else ""
        out.append(("Enforcement notices served", f"{n['notice']}{form}", str(n["count"])))
    out += [
        ("Local plans", "Commenced", "; ".join(pl["commenced"]) or "0"),
        ("Local plans", "Draft on display", "; ".join(pl["drafts_on_display"]) or "0"),
        ("Local plans", "Approved", "; ".join(pl["approved"]) or "0"),
        ("Local plans", "Consultations held", str(pl["consultations_held"])),
        ("Local plans", "Comments received on drafts", str(pl["comments_received"])),
        ("Public Data Room", "Requests for information received", str(d["requests_received"])),
        ("Public Data Room", "Answered", str(d["answered"])),
        (
            "Public Data Room",
            "Answered within 5 days (%)",
            "" if d["answered_within_limit_pct"] is None else f"{d['answered_within_limit_pct']:g}",
        ),
        ("Rates", "Bills issued", str(r["bills_issued"])),
        ("Rates", "Billed (GHS)", r["billed"]),
        ("Betterment", "Schemes completed", str(r["betterment_schemes_completed"])),
    ]
    return out


def to_csv(data: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["section", "measure", "value"])
    writer.writerows(rows(data))
    return "﻿" + out.getvalue()

# ruff: noqa: E501 - comments and messages read better unbroken
"""Agendas built from what is waiting for each committee; the quorum of
r.7; the three days' notice of r.6."""

import math
from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError

from landchange import registry as land_registry
from landchange.models import Application as LandApplication
from permits import registry as permit_registry
from permits.models import Application
from planmaking.models import PlanProcess

from . import registry
from .models import Committee, Meeting


def committee(district_id: int, kind: str) -> Committee:
    if kind not in registry.COMMITTEES:
        raise ValidationError({"kind": [f"One of: {', '.join(registry.COMMITTEES)}."]})
    found, _ = Committee.objects.get_or_create(district_id=district_id, kind=kind)
    return found


def check_members(members: Any) -> list[dict[str, str]]:
    if not isinstance(members, list):
        raise ValidationError({"members": ["A list of members."]})
    out, seen = [], set()
    for member in members:
        if not isinstance(member, dict) or not str(member.get("name") or "").strip():
            raise ValidationError({"members": ["Each member has a name."]})
        name = str(member["name"]).strip()
        office = str(member.get("office") or "other")
        if office not in registry.OFFICE_LABELS:
            raise ValidationError({"members": [f"{name}: not an office."]})
        if name.lower() in seen:
            raise ValidationError({"members": [f"{name} is listed twice."]})
        seen.add(name.lower())
        out.append({"name": name, "office": office})
    return out


def _permit_title(a: Application) -> str:
    category = permit_registry.CATEGORY_BY_CODE.get(a.category)
    what = category.label if category else a.category
    return f"{a.number}: {what}, {a.proposed_use or 'use not stated'} ({a.project.community or a.project.name})"


def waiting(meeting_committee: Committee) -> list[dict[str, Any]]:
    """What is waiting for this committee now."""
    items: list[dict[str, Any]] = []
    apps = (
        Application.objects.filter(district_id=meeting_committee.district_id)
        .select_related("project")
        .order_by("received_on", "id")
    )
    lands = (
        LandApplication.objects.filter(
            district_id=meeting_committee.district_id,
            status__in=(LandApplication.Status.RECEIVED, LandApplication.Status.DEFERRED),
        )
        .select_related("project")
        .order_by("received_on", "id")
    )
    if meeting_committee.kind == "tsc":
        # r.44(7)-(8): the Technical Sub-Committee checks, inspects and reports.
        for a in apps.filter(
            status__in=(
                Application.Status.RECEIVED,
                Application.Status.REVIEW,
                Application.Status.DEFERRED,
            )
        ):
            items.append({"type": "permit", "ref": a.pk, "title": _permit_title(a)})
    else:
        # The Spatial Planning Committee decides what the Sub-Committee has reported.
        for a in apps.filter(status=Application.Status.REPORTED):
            items.append({"type": "permit", "ref": a.pk, "title": _permit_title(a)})
        for process in PlanProcess.objects.filter(
            district_id=meeting_committee.district_id
        ).select_related("project"):
            if "notice" in process.steps and "approve" not in process.steps:
                items.append(
                    {
                        "type": "plan",
                        "ref": process.project_id,
                        "title": f"Local plan: {process.project.name}",
                    }
                )
    for land in lands:
        kind = land_registry.KIND_BY_CODE[land.kind].label
        items.append(
            {
                "type": "land",
                "ref": land.pk,
                "title": f"{land.number}: {kind} ({land.project.community or land.project.name})",
            }
        )
    return items


def build_agenda(meeting: Meeting) -> int:
    """Adds what is waiting and not on the agenda yet; returns how many were added."""
    have = {(i["type"], i.get("ref")) for i in meeting.agenda}
    added = [
        {**item, "outcome": "", "minute": ""}
        for item in waiting(meeting.committee)
        if (item["type"], item["ref"]) not in have
    ]
    meeting.agenda = [*meeting.agenda, *added]
    return len(added)


def check_agenda(agenda: Any, current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The agenda as edited: outcomes and minutes on its items, items added by hand."""
    if not isinstance(agenda, list):
        raise ValidationError({"agenda": ["A list of items."]})
    out = []
    for item in agenda:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            raise ValidationError({"agenda": ["Each item has a title."]})
        outcome = str(item.get("outcome") or "")
        if outcome not in registry.OUTCOMES:
            raise ValidationError({"agenda": [f"Not an outcome: {outcome}."]})
        kind = str(item.get("type") or "other")
        out.append(
            {
                "type": kind if kind in ("permit", "land", "plan") else "other",
                "ref": item.get("ref") if kind in ("permit", "land", "plan") else None,
                "title": str(item["title"]).strip()[:300],
                "outcome": outcome,
                "minute": str(item.get("minute") or "")[:5000],
            }
        )
    return out


def quorum(meeting: Meeting) -> dict[str, Any]:
    """r.7: whether enough members, and the offices that must be, are present."""
    members = meeting.committee.members
    present = [m for m in members if m["name"] in meeting.attendance]
    offices = {m["office"] for m in present}
    if meeting.committee.kind == "dspc":
        required, needed, rule = registry.DSPC_REQUIRED, registry.DSPC_QUORUM, "r.7(1)-(2)"
    else:
        required, needed, rule = (
            registry.TSC_REQUIRED,
            max(1, math.ceil(len(members) / 2)),
            "r.7(3)-(4)",
        )
    missing = [
        " or ".join(registry.OFFICE_LABELS[o] for o in group)
        for group in required
        if not offices.intersection(group)
    ]
    return {
        "present": len(present),
        "needed": needed,
        "missing_offices": missing,
        "met": len(present) >= needed and not missing,
        "rule": rule,
    }


def notice_clock(meeting: Meeting) -> dict[str, Any]:
    """r.6(2): notice served not later than three days before the meeting."""
    serve_by = meeting.held_on - timedelta(days=registry.NOTICE_DAYS)
    served = meeting.notice_served_on
    return {
        "serve_by": serve_by.isoformat(),
        "served_on": served.isoformat() if served else None,
        "late": bool(served and served > serve_by),
        "overdue": served is None and date.today() > serve_by,
        "rule": "r.6(2)",
    }

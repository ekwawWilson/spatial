# ruff: noqa: E501 - long assertions read better on one line
"""The district's statutory deadlines in one place (reports app): counted
from permits, requests for information, enforcement cases and zoning schemes."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import Role
from dataroom.models import InformationRequest

pytestmark = pytest.mark.django_db

TODAY = date.today()
URL = "reports-compliance"


def days(n):
    return str(TODAY + timedelta(days=n))


def receive(world, parcel, **extra):
    site = world.features("parcels", "parcel_id")[parcel]
    body = {
        "project": world.project,
        "kind": "development",
        "category": "building",
        "applicant_name": "Ama Mensah",
        "site_feature": site["id"],
        **extra,
    }
    made = world.client.post(reverse("permit-application-list"), body, format="json")
    assert made.status_code == 201, made.content
    return made.json()


def step(client, name, application, body=None):
    done = client.post(
        reverse(f"permit-application-{name}", args=[application["id"]]), body or {}, format="json"
    )
    assert done.status_code in (200, 201), (name, done.content)
    return done.json()


def test_nothing_yet(planner):
    data = planner.get(reverse(URL)).json()
    assert data["as_of"] == str(TODAY) and data["overdue"] == 0
    assert data["permits"]["open"] == 0 and data["permits"]["decided_within_limit_pct"] is None
    assert data["permits"]["overdue_by_step"] == {
        "acknowledge": 0,
        "inspect": 0,
        "report": 0,
        "issue": 0,
    }
    assert data["dataroom"] == {
        "is_open": False,
        "published_projects": 0,
        "documents_on_display": 0,
    }
    assert APIClient().get(reverse(URL)).status_code == 401


def test_every_statutory_clock_is_counted(
    world, admin, api, members_a, district_a, district_b, make_member
):
    """Gate: each overdue duty is counted once, under its own heading."""
    planner = world.client
    # Permits: one received 40 days ago and never acknowledged; one due this week;
    # one decided in 12 days; one decided after 45.
    late = receive(world, "P-001", received_on=days(-40))
    soon = receive(world, "P-002", received_on=days(-3))
    for parcel, received, took in (("P-003", -20, 12), ("P-004", -50, 45)):
        app = receive(world, parcel, received_on=days(received))
        at = {"on": days(received + 1)}
        step(planner, "acknowledge", app, at)
        step(planner, "inspect", app, {**at, "summary": "Seen."})
        step(planner, "report", app, {**at, "recommendation": "grant"})
        step(admin, "decide", app, {"decision": "grant", "on": days(received + took)})

    # A request for information ten days old (five allowed), and one answered the same day.
    admin.patch(reverse("dataroom-settings"), {"is_open": True}, format="json")
    anyone = APIClient()
    ask = {"name": "Kojo", "phone": "0200000000", "subject": "Plot 14", "body": "Zoned for?"}
    first = anyone.post(reverse("public-requests", args=["DA"]), ask, format="json").json()
    anyone.post(reverse("public-requests", args=["DA"]), ask, format="json")
    InformationRequest.objects.filter(reference=first["reference"]).update(
        received_on=TODAY - timedelta(days=10)
    )
    listed = planner.get(reverse("dataroom-request-list")).json()["results"]
    fresh = next(r for r in listed if r["reference"] != first["reference"])
    planner.post(
        reverse("dataroom-request-answer", args=[fresh["id"]]), {"answer": "Re B."}, format="json"
    )

    # Enforcement: a notice to rectify by 20 days ago, with no enforcement notice since.
    case = planner.post(
        reverse("enforcement-case-list"),
        {
            "project": world.project,
            "contravention": "no_permit",
            "description": "Wall",
            "opened_on": days(-40),
        },
        format="json",
    ).json()
    planner.post(
        reverse("enforcement-case-notices", args=[case["id"]]),
        {"kind": "rectification", "grounds": "No permit", "comply_by": days(-20), "on": days(-30)},
        format="json",
    )

    # A zoning scheme approved 40 days ago and not yet sent to LUSPA (28 allowed).
    planner.post(
        reverse("zoning-scheme-list"),
        {
            "project": world.project,
            "name": "Kasoa scheme",
            "status": "approved",
            "approved_on": days(-40),
        },
        format="json",
    )

    data = planner.get(reverse(URL)).json()
    permits = data["permits"]
    # Open: the late one, the one due soon, and the two granted (their certificates are not issued).
    assert (permits["open"], permits["received_this_year"] >= 2, permits["limit_days"]) == (
        4,
        True,
        30,
    )
    # Past a date: the unacknowledged one, and the two granted whose certificates are over 30 days from receipt?
    # P-003 was received 20 days ago: its certificate isn't due yet. P-004 (50 days ago) is.
    assert permits["overdue"] == 2 and permits["overdue_by_step"] == {
        "acknowledge": 1,
        "inspect": 0,
        "report": 0,
        "issue": 1,
    }
    worst = permits["late"][0]
    assert (worst["step"], worst["rule"]) == (
        "Decision, and the certificate where granted",
        "r.44(10)",
    ) and worst["days_late"] == 20
    assert permits["late"][1]["number"] == late["number"] and permits["late"][1]["days_late"] == 33
    assert permits["decided_this_year"] == 2 and permits["decided_within_limit_pct"] == 50.0
    assert permits["average_days_to_decision"] == 28.5
    assert [row["number"] for row in data["week_ahead"]] == [
        soon["number"]
    ]  # to acknowledge within 4 days

    assert data["requests"] == {
        "open": 1,
        "overdue": 1,
        "answered_this_year": 1,
        "answered_within_limit_pct": 100.0,
        "limit_days": 5,
    }
    assert (data["enforcement"]["open"], data["enforcement"]["overdue"]) == (1, 1)
    assert data["enforcement"]["late"][0]["step"] == "Serve an enforcement notice (r.57(2))"
    assert (data["zoning"]["schemes"], data["zoning"]["overdue"]) == (1, 1)
    assert data["zoning"]["late"][0]["duty"] == "Send a copy to LUSPA" and data["zoning"]["late"][
        0
    ]["due_on"] == days(-12)
    assert data["dataroom"]["is_open"] is True
    assert data["overdue"] == 2 + 1 + 1 + 1

    # Everyone in the district can see it (no personal data in it); the page prints.
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(reverse(URL)).json()["overdue"] == 5 and "Ama" not in str(
        viewer.get(reverse(URL)).json()
    )
    printed = viewer.get(reverse("reports-compliance-pdf"))
    assert printed.status_code == 200 and printed.content.startswith(b"%PDF")
    assert "statutory-deadlines-DA" in printed["Content-Disposition"]
    # Another district sees only its own.
    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(reverse(URL)).json()["overdue"] == 0

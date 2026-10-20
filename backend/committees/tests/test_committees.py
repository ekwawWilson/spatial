# ruff: noqa: E501 - long assertions read better on one line
"""The planning committees' meetings: agendas from what is waiting, the
three days' notice of r.6 and the quorum of r.7, notice and minutes."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from core.models import Role
from core.tenancy import tenant_context
from planmaking.models import PlanProcess
from projects.models import PlanProject

pytestmark = pytest.mark.django_db

TODAY = date.today()
TSC = [
    {"name": "Kofi Boateng", "office": "physical_planning"},
    {"name": "Esi Owusu", "office": "development_planning"},
    {"name": "Yaw Mensah", "office": "works"},
    {"name": "Abena Darko", "office": "lands"},
    {"name": "Kojo Asare", "office": "epa"},
    {"name": "Akua Addo", "office": "roads"},
    {"name": "Nana Badu", "office": "other"},
    {"name": "Efua Ansah", "office": "other"},
]


def receive(world, parcel):
    site = world.features("parcels", "parcel_id")[parcel]
    made = world.client.post(
        reverse("permit-application-list"),
        {
            "project": world.project,
            "kind": "development",
            "category": "building",
            "applicant_name": "Ama",
            "proposed_use": "Residential",
            "site_feature": site["id"],
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    return made.json()


def test_a_technical_sub_committee_meeting(
    world, admin, api, members_a, district_a, district_b, make_member
):
    planner = world.client
    committees = reverse("committees")
    assert (
        planner.put(f"{committees}?kind=tsc", {"members": TSC}, format="json").status_code == 403
    )  # the administrator sets members
    assert (
        admin.put(
            f"{committees}?kind=tsc", {"members": [{"name": "X", "office": "mayor"}]}, format="json"
        ).status_code
        == 400
    )
    assert (
        admin.put(
            f"{committees}?kind=tsc", {"members": [{"name": "X"}, {"name": "x"}]}, format="json"
        ).status_code
        == 400
    )
    assert admin.put(f"{committees}?kind=tsc", {"members": TSC}, format="json").status_code == 200

    first = receive(world, "P-001")
    receive(world, "P-002")
    meetings = reverse("committee-meeting-list")
    made = planner.post(
        meetings,
        {"committee": "tsc", "held_on": str(TODAY + timedelta(days=10)), "venue": "Assembly Hall"},
        format="json",
    )
    assert made.status_code == 201, made.content
    meeting = made.json()
    assert [i["title"].split(":")[0] for i in meeting["agenda"]] == [
        first["number"],
        first["number"].replace("0001", "0002"),
    ]
    assert meeting["notice"] == {
        "serve_by": str(TODAY + timedelta(days=7)),
        "served_on": None,
        "late": False,
        "overdue": False,
        "rule": "r.6(2)",
    }
    detail = reverse("committee-meeting-detail", args=[meeting["id"]])

    # Quorum: half the members (4 of 8), and the six offices of r.7(4).
    q = planner.patch(
        detail,
        {"attendance": ["Kofi Boateng", "Esi Owusu", "Yaw Mensah", "Abena Darko", "Kojo Asare"]},
        format="json",
    ).json()["quorum"]
    assert (q["met"], q["present"], q["needed"], q["missing_offices"]) == (
        False,
        5,
        4,
        ["Head of the Roads Unit or Urban Roads Department"],
    )
    assert planner.patch(detail, {"attendance": ["Someone Else"]}, format="json").status_code == 400
    q = planner.patch(
        detail,
        {"attendance": [m["name"] for m in TSC[:6]], "notice_served_on": str(TODAY)},
        format="json",
    ).json()
    assert (q["quorum"]["met"], q["notice"]["late"]) == (True, False)

    # A new application comes in: refreshing adds it once.
    receive(world, "P-003")
    assert (
        planner.post(
            reverse("committee-meeting-refresh-agenda", args=[meeting["id"]]), {}, format="json"
        ).json()["added"]
        == 1
    )
    assert (
        planner.post(
            reverse("committee-meeting-refresh-agenda", args=[meeting["id"]]), {}, format="json"
        ).json()["added"]
        == 0
    )

    # The minute on each item; an item added by hand.
    agenda = planner.get(detail).json()["agenda"]
    agenda[0] = {
        **agenda[0],
        "outcome": "recommend_grant",
        "minute": "Site inspected; setbacks met.",
    }
    agenda.append(
        {"type": "other", "title": "Any other business", "outcome": "noted", "minute": "None."}
    )
    saved = planner.patch(detail, {"agenda": agenda}, format="json").json()
    assert (saved["agenda"][0]["outcome"], saved["agenda"][-1]["ref"], len(saved["agenda"])) == (
        "recommend_grant",
        None,
        4,
    )
    assert (
        planner.patch(
            detail, {"agenda": [{"title": "X", "outcome": "maybe"}]}, format="json"
        ).status_code
        == 400
    )
    for kind in ("notice", "minutes"):
        paper = planner.get(
            reverse("committee-meeting-paper", args=[meeting["id"]]), {"kind": kind}
        )
        assert paper.status_code == 200 and paper.content.startswith(b"%PDF"), kind
    listed = planner.get(meetings).json()["results"]
    assert [(m["committee_label"], m["items"], m["considered"]) for m in listed] == [
        ("Technical Sub-Committee", 4, 2)
    ]

    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(detail).status_code == 200
    assert (
        viewer.post(
            meetings, {"committee": "tsc", "held_on": str(TODAY)}, format="json"
        ).status_code
        == 403
    )
    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(detail).status_code == 404


def test_the_spatial_planning_committee_needs_nine_and_its_offices(world, admin, district_a):
    members = [
        {"name": "DCE", "office": "dce"},
        {"name": "PP", "office": "physical_planning"},
        {"name": "DP", "office": "development_planning"},
        {"name": "W", "office": "works"},
        {"name": "D", "office": "disaster"},
        {"name": "L", "office": "lands"},
        {"name": "E", "office": "epa"},
        {"name": "R", "office": "roads"},
        {"name": "O1", "office": "other"},
        {"name": "O2", "office": "other"},
    ]
    admin.put(f"{reverse('committees')}?kind=dspc", {"members": members}, format="json")
    with tenant_context(district_a.id):
        project = PlanProject.objects.get(pk=world.project)
        PlanProcess.objects.create(
            district_id=district_a.id,
            project=project,
            steps={"notice": {"on": str(TODAY - timedelta(days=70)), "note": ""}},
        )
    meeting = admin.post(
        reverse("committee-meeting-list"),
        {"committee": "dspc", "held_on": str(TODAY + timedelta(days=2))},
        format="json",
    ).json()
    assert [i["title"] for i in meeting["agenda"]] == ["Local plan: Relations plan"]
    # Notice can no longer be served three days ahead.
    assert meeting["notice"]["overdue"] is True
    detail = reverse("committee-meeting-detail", args=[meeting["id"]])
    eight = [m["name"] for m in members[:8]]
    q = admin.patch(detail, {"attendance": eight}, format="json").json()["quorum"]
    assert (q["met"], q["needed"], q["rule"]) == (False, 9, "r.7(1)-(2)")
    q = admin.patch(detail, {"attendance": [*eight, "O1"]}, format="json").json()["quorum"]
    assert q["met"] is True
    # The Coordinating Director may stand in for the DCE: without either, no quorum.
    q = admin.patch(
        detail, {"attendance": [n for n in [*eight, "O1", "O2"] if n != "DCE"]}, format="json"
    ).json()["quorum"]
    assert (q["met"], q["missing_offices"]) == (
        False,
        ["District Chief Executive or District Coordinating Director"],
    )

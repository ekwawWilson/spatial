# ruff: noqa: E501 - long assertions read better on one line
"""Phase 19: making a local plan (L.I. 2384 r.23-27) and its public
consultation (r.65): every clock, the sixty days for comments, and what the
public sees and may send without signing in."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from planmaking import services
from planmaking.models import PlanComment

pytestmark = pytest.mark.django_db

TODAY = date.today()


def days(n):
    return str(TODAY + timedelta(days=n))


def url(name, world):
    return reverse(name, args=[world.project])


def step(client, world, code, expect=200, **body):
    done = client.post(url("plan-step", world), {"step": code, **body}, format="json")
    assert done.status_code == expect, (code, done.status_code, done.content)
    return done.json()


def clock(plan, code):
    return next(c for c in plan["clocks"] if c["code"] == code)


def test_twelve_months_is_counted_by_the_calendar():
    assert services.add_months(date(2025, 3, 15), 12) == date(2026, 3, 15)
    assert services.add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert services.add_months(date(2025, 11, 30), 3) == date(2026, 2, 28)


def test_a_local_plan_from_direction_to_approval(
    world, admin, api, members_a, district_a, district_b, make_member
):
    """Gate: every clock of r.23 and r.25, and approval waits for the public's sixty days."""
    planner = world.client
    plan = planner.get(url("plan-process", world)).json()
    # Nothing recorded yet: a plan of the Committee's own, with its six steps and no dates.
    assert (plan["origin"], [c["code"] for c in plan["clocks"]]) == (
        "committee",
        ["direct", "commence", "draft", "notice", "approve", "publish_approval"],
    )
    assert all(c["due_on"] is None and c["done_on"] is None for c in plan["clocks"])
    assert (
        len(plan["content"]),
        plan["content_covered"],
        plan["comment_days"],
        plan["comments_open"],
    ) == (17, 0, 60, False)
    assert [p["code"] for p in plan["papers"]] == ["commence", "notice"]

    # r.23(1): the local plan is directed within twelve months of the structure plan coming into force.
    in_force = TODAY - timedelta(days=500)
    plan = planner.patch(
        url("plan-process", world),
        {"structure_plan_on": str(in_force), "origin": "council"},
        format="json",
    )
    assert plan.status_code == 400
    plan = planner.patch(
        url("plan-process", world), {"structure_plan_on": str(in_force)}, format="json"
    ).json()
    due = services.add_months(in_force, 12)
    assert (
        clock(plan, "direct")["due_on"],
        clock(plan, "direct")["overdue"],
        clock(plan, "direct")["limit"],
        clock(plan, "direct")["rule"],
    ) == (str(due), True, "12 months", "r.23(1)")
    assert (plan["next_step"]["code"], plan["next_step"]["overdue"]) == ("direct", True)
    plan = step(planner, world, "direct", on=days(-120), note="Resolution 14")
    assert (clock(plan, "direct")["late"], clock(plan, "direct")["note"]) == (True, "Resolution 14")
    assert (
        clock(plan, "commence")["form"],
        clock(plan, "notice")["form"],
        clock(plan, "publish_approval")["form"],
    ) == ("27", "28", "29")

    # Steps follow one another; none is dated in the future; r.26 is not for the Committee's own plan.
    step(planner, world, "notice", expect=400)  # no draft yet
    step(planner, world, "commence", expect=400, on=days(1))
    step(admin, world, "confirm", expect=400)
    step(planner, world, "nothing", expect=400)
    plan = step(planner, world, "commence", on=days(-110))
    plan = step(planner, world, "draft", on=days(-70))
    step(planner, world, "notice", expect=400, on=days(-71))  # before the draft was complete
    # The draft goes on display 65 days ago: the public's sixty days ended five days ago.
    plan = step(planner, world, "notice", on=days(-65))
    assert (plan["comments_close_on"], plan["comments_open"], plan["comment_rule"]) == (
        days(-5),
        False,
        "r.23(5)",
    )

    # What the plan specifies (r.24).
    assert (
        planner.post(
            url("plan-content", world), {"items": {"z": {"covered": True}}}, format="json"
        ).status_code
        == 400
    )
    assert (
        planner.post(
            url("plan-content", world), {"items": {"a": {"note": "?"}}}, format="json"
        ).status_code
        == 400
    )
    plan = planner.post(
        url("plan-content", world),
        {
            "items": {
                "a": {"covered": True, "note": "Section 3"},
                "m": {"covered": True},
                "n": {"covered": False, "note": "No sewers planned"},
            }
        },
        format="json",
    ).json()
    assert plan["content_covered"] == 2
    assert next(i for i in plan["content"] if i["code"] == "a") == {
        "code": "a",
        "label": "Population size and density for residential neighbourhoods",
        "covered": True,
        "note": "Section 3",
    }

    # The approval is recorded by those who may decide, and never inside the sixty days.
    assert (
        planner.post(url("plan-step", world), {"step": "approve"}, format="json").status_code == 403
    )
    step(admin, world, "approve", expect=400, on=days(-5))
    assert planner.get(url("plan-paper", world), {"kind": "publish_approval"}).status_code == 400
    plan = step(admin, world, "approve", on=days(-2))
    # r.25(5): the notice of approval within seven days. No ninety-day limit on the Committee's own plan (r.25(6)).
    assert (
        clock(plan, "approve")["due_on"],
        clock(plan, "publish_approval")["due_on"],
        clock(plan, "publish_approval")["limit"],
    ) == (None, days(5), "7 days")
    assert plan["next_step"]["code"] == "publish_approval"
    plan = planner.patch(
        url("plan-process", world),
        {"conditions": "Drains before plots are allocated.", "valid_until": days(3650)},
        format="json",
    ).json()
    assert plan["valid_until"] == days(3650) and len(plan["possible_conditions"]) == 5
    for kind in ("commence", "notice", "publish_approval"):
        paper = planner.get(url("plan-paper", world), {"kind": kind})
        assert paper.status_code == 200 and paper.content.startswith(b"%PDF"), kind
    plan = step(planner, world, "publish_approval")
    assert plan["next_step"] is None

    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(url("plan-process", world)).status_code == 200
    assert viewer.post(url("plan-step", world), {"step": "draft"}, format="json").status_code == 403
    assert (
        viewer.patch(url("plan-process", world), {"prepared_by": "X"}, format="json").status_code
        == 403
    )
    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(url("plan-process", world)).status_code == 404
    assert other.post(url("plan-step", world), {"step": "draft"}, format="json").status_code == 404
    assert AuditLog.objects.filter(table_name="planmaking_planprocess", action="UPDATE").exists()


def test_a_plan_prepared_by_someone_else_is_decided_in_ninety_days_and_confirmed(world, admin):
    planner = world.client
    plan = planner.patch(
        url("plan-process", world),
        {"origin": "applicant", "prepared_by": "Kasoa Estates Ltd", "application_on": days(-100)},
        format="json",
    ).json()
    assert [c["code"] for c in plan["clocks"]] == [
        "direct",
        "commence",
        "draft",
        "notice",
        "approve",
        "publish_approval",
        "request_confirmation",
        "confirm",
        "publish_confirmation",
    ]
    # r.25(1): decided within ninety days of the application.
    assert (
        clock(plan, "approve")["due_on"],
        clock(plan, "approve")["overdue"],
        clock(plan, "approve")["limit"],
    ) == (days(-10), True, "90 days")
    step(planner, world, "draft", on=days(-90))
    step(planner, world, "notice", on=days(-80))
    step(planner, world, "request_confirmation", expect=400)  # not approved yet
    plan = step(admin, world, "approve", on=days(-5))
    assert clock(plan, "approve")["late"] is True
    # r.26(4): the Regional Spatial Planning Committee has twenty-eight days from the request.
    assert clock(plan, "confirm")["due_on"] is None
    plan = step(planner, world, "request_confirmation", on=days(-4))
    assert (clock(plan, "confirm")["due_on"], clock(plan, "confirm")["rule"]) == (
        days(24),
        "r.26(4)",
    )
    assert (
        planner.post(url("plan-step", world), {"step": "confirm"}, format="json").status_code == 403
    )
    plan = step(admin, world, "confirm", on=days(-1))
    assert (
        clock(plan, "publish_confirmation")["due_on"],
        clock(plan, "publish_confirmation")["form"],
    ) == (days(6), "31")


def test_consultations_and_comments_in_the_open(world, admin, district_a):
    """r.65: minutes recorded and displayed; r.23(5)-(7): the public comments for sixty days."""
    planner = world.client
    anyone = APIClient()
    plans = reverse("public-plans", args=["DA"])
    send = reverse("public-plan-comment", args=["DA", world.project])
    comment = {
        "name": "Akua Sarpong",
        "contact": "0200000002",
        "topic": "k",
        "text": "The market road needs a walkway.",
    }

    meeting = {
        "stage": "before",
        "held_on": days(-30),
        "venue": "Chief's palace",
        "groups": "Chiefs, land owners, market traders",
        "attendance": 84,
        "issues": "Flooding along the drain.\nNo space for a lorry park.",
        "outcome": "The drain reserve will be kept clear.",
    }
    assert (
        planner.post(
            url("plan-consultations", world), {**meeting, "stage": "after"}, format="json"
        ).status_code
        == 400
    )
    assert (
        planner.post(
            url("plan-consultations", world), {**meeting, "held_on": days(1)}, format="json"
        ).status_code
        == 400
    )
    plan = planner.post(url("plan-consultations", world), meeting, format="json")
    assert plan.status_code == 201, plan.content
    held = plan.json()["consultations"][0]
    assert (held["stage_label"], held["attendance"], held["displayed_on"]) == (
        "Before the preparation of the plan",
        84,
        None,
    )
    minutes = planner.get(reverse("plan-consultation-minutes", args=[held["id"]]))
    assert minutes.status_code == 200 and minutes.content.startswith(b"%PDF")

    # Nothing is public until the room is open, the project published, and a notice given.
    admin.patch(reverse("dataroom-settings"), {"is_open": True}, format="json")
    admin.post(reverse("dataroom-publication-list"), {"project": world.project}, format="json")
    assert anyone.get(plans).json()["results"] == []
    assert anyone.post(send, comment, format="json").status_code == 404
    step(planner, world, "commence", on=days(-40))
    shown = anyone.get(plans).json()
    assert len(shown["topics"]) == 17
    row = shown["results"][0]
    assert (row["name"], row["commenced_on"], row["comments_open"], row["consultations"]) == (
        "Relations plan",
        days(-40),
        False,
        [],
    )
    assert anyone.post(send, comment, format="json").status_code == 400  # the draft is not out yet

    # r.65(3): the minutes go on display.
    plan = planner.post(
        reverse("plan-consultation-display", args=[held["id"]]), {}, format="json"
    ).json()
    assert plan["consultations"][0]["displayed_on"] == str(TODAY)
    seen = anyone.get(plans).json()["results"][0]["consultations"]
    assert seen == [
        {
            "stage": "Before the preparation of the plan",
            "held_on": days(-30),
            "venue": "Chief's palace",
            "attendance": 84,
            "issues": meeting["issues"],
            "outcome": meeting["outcome"],
        }
    ]

    # The draft is out: sixty days for comments, online or at the office.
    step(planner, world, "draft", on=days(-12))
    step(planner, world, "notice", on=days(-10))
    row = anyone.get(plans).json()["results"][0]
    assert (row["draft_on_display_from"], row["comments_close_on"], row["comments_open"]) == (
        days(-10),
        days(50),
        True,
    )
    assert anyone.post(send, {**comment, "topic": "zz"}, format="json").status_code == 400
    sent = anyone.post(send, comment, format="json")
    assert sent.status_code == 201 and sent.json() == {
        "received_on": str(TODAY),
        "comments_close_on": days(50),
    }
    assert "Akua" not in str(anyone.get(plans).json())  # who commented is never public
    plan = planner.post(
        url("plan-comments", world),
        {"name": "Nana Kwame", "text": "Keep the sacred grove.", "on": days(-3)},
        format="json",
    ).json()
    assert [(c["name"], c["online"], c["topic_label"]) for c in plan["comments"]] == [
        (
            "Akua Sarpong",
            True,
            "Road network and circulation, including parking and pedestrian walkways",
        ),
        ("Nana Kwame", False, ""),
    ]
    assert plan["comments_unanswered"] == 2
    first = plan["comments"][0]
    plan = planner.post(
        reverse("plan-comment-reply", args=[first["id"]]),
        {"response": "A 2 m walkway is added on both sides."},
        format="json",
    ).json()
    assert (
        plan["comments"][0]["response"],
        plan["comments"][0]["responded_on"],
        plan["comments_unanswered"],
    ) == ("A 2 m walkway is added on both sides.", str(TODAY), 1)

    # The plan cannot be approved while the public may still comment.
    early = step(admin, world, "approve", expect=400, on=str(TODAY))
    assert days(50) in str(early)
    with tenant_context(district_a.id):
        assert PlanComment.objects.filter(online=True).count() == 1

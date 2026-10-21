# ruff: noqa: E501 - long assertions read better on one line
"""Phase 18: re-zoning (L.I. 2384 r.33), change of use (r.34), and the
subdivision or consolidation of land (r.54). The fixture community: parcels
P-001 to P-003 stand side by side north of Main Street, P-004 to P-006
across it, so the land abutting P-002 is P-001 and P-003 and nothing else."""

import re
from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AuditLog, Role

pytestmark = pytest.mark.django_db

TODAY = date.today()
LIST = "land-application-list"


def days(n):
    return str(TODAY + timedelta(days=n))


def url(name, application):
    return reverse(f"land-application-{name}", args=[application["id"]])


def parcel(world, label):
    return world.features("parcels", "parcel_id")[label]


def receive(world, kind, labels, **extra):
    body = {
        "project": world.project,
        "kind": kind,
        "applicant_name": "Ama Mensah",
        "applicant_phone": "0240000000",
        "parcels": [parcel(world, label)["id"] for label in labels],
        **extra,
    }
    return world.client.post(reverse(LIST), body, format="json")


def do(client, name, application, body=None, expect=(200, 201)):
    done = client.post(url(name, application), body or {}, format="json")
    assert done.status_code in expect, (name, done.status_code, done.content)
    return done.json()


def clock(application, code):
    return next(c for c in application["clocks"] if c["code"] == code)


def codes(application):
    return [c["code"] for c in application["clocks"]]


def test_what_the_regulations_fix(planner):
    data = planner.get(reverse("land-registry")).json()
    kinds = {k["code"]: k for k in data["kinds"]}
    assert list(kinds) == ["rezoning", "change_of_use", "subdivision", "consolidation"]
    assert (
        kinds["rezoning"]["form"],
        kinds["rezoning"]["comment_days"],
        kinds["rezoning"]["decide_days"],
    ) == ("33A and 33B", 28, 60)
    assert (
        kinds["subdivision"]["form"],
        kinds["subdivision"]["comment_days"],
        kinds["subdivision"]["decide_days"],
    ) == ("46", 14, 60)
    assert {s["code"]: s["days"] for s in kinds["rezoning"]["steps"]} == {
        "display": 7,
        "publish_1": 7,
        "direct_notice": 7,
        "publish_2": 28,
        "posted": None,
        "refer_objections": 14,
        "response": None,
        "gazette": 7,
    }
    assert {s["code"]: s["days"] for s in kinds["consolidation"]["steps"]} == {
        "acknowledge": 7,
        "advertise": 21,
        "lands_commission": None,
        "display": None,
        "notify_applicant": None,
        "response": 14,
        "publish_approval": None,
        "notify_lands": 30,
    }
    assert [t["rule"] for t in data["use_tests"]][:3] == ["r.34(1)(a)", "r.34(1)(b)", "r.34(1)(c)"]
    assert len(data["use_tests"]) == 8 and data["deferred_decision_days"] == 30


def test_a_rezoning_through_every_clock(
    world, admin, api, members_a, district_a, district_b, make_member
):
    """Gate: every clock of r.33, and the abutting land is exactly what touches."""
    world.set_roles()
    planner = world.client
    # r.33(2): the application says why.
    assert receive(world, "rezoning", ["P-002"], proposed_zone="Re B").status_code == 400
    assert (
        receive(world, "rezoning", ["P-002"], proposed_zone="Re B", ground="special").status_code
        == 400
    )
    assert receive(world, "rezoning", ["P-002"], ground="structure_plan").status_code == 400
    assert (
        planner.post(
            reverse(LIST),
            {
                "project": world.project,
                "kind": "rezoning",
                "applicant_name": "A",
                "parcels": [999_999_999],
                "proposed_zone": "Re B",
                "ground": "structure_plan",
            },
            format="json",
        ).status_code
        == 400
    )
    made = receive(
        world,
        "rezoning",
        ["P-002"],
        proposed_zone="Re B",
        ground="special",
        circumstance="demographics",
        received_on=days(-40),
    )
    assert made.status_code == 201, made.content
    app = made.json()
    assert re.fullmatch(rf"DA/RZ/{(TODAY - timedelta(days=40)).year}/0001", app["number"])
    assert (app["current_zone"], app["proposed_zone"], app["status"]) == (
        "residential",
        "Re B",
        "received",
    )
    assert app["summary"] == "the re-zoning of P-002 from residential to Re B"
    assert [p["label"] for p in app["parcels"]] == ["P-002"]
    # The owners to be given notice: the parcels that touch, not those across the street.
    assert [a["label"] for a in app["abutting"]] == ["P-001", "P-003"]

    # Forty days in and nothing done: the seven-day steps are past their dates.
    assert codes(app) == ["display", "publish_1", "direct_notice", "publish_2", "posted", "decide"]
    assert (
        clock(app, "display")["due_on"],
        clock(app, "display")["overdue"],
        clock(app, "display")["rule"],
    ) == (days(-33), True, "r.33(5)(a)-(b)")
    assert clock(app, "publish_2")["due_on"] is None  # runs from the first publication
    assert clock(app, "posted")["due_on"] is None and clock(app, "decide")["due_on"] is None
    assert (app["next_step"]["code"], app["next_step"]["overdue"], app["comments_close_on"]) == (
        "display",
        True,
        None,
    )
    listed = planner.get(reverse(LIST), {"project": world.project}).json()
    assert listed["summary"] == {"total": 1, "open": 1, "overdue": 1}

    # Displayed on day 5 (in time): the public may comment for 28 days from then.
    assert do(planner, "step", app, {"step": "nothing"}, expect=(400,))
    assert do(planner, "step", app, {"step": "display", "on": days(1)}, expect=(400,))
    assert do(planner, "step", app, {"step": "display", "on": days(-41)}, expect=(400,))
    assert do(planner, "step", app, {"step": "gazette"}, expect=(400,))  # only once approved
    app = do(
        planner,
        "step",
        app,
        {"step": "display", "on": days(-35), "note": "Notice board and Data Room"},
    )
    assert (
        clock(app, "display")["done_on"],
        clock(app, "display")["late"],
        clock(app, "display")["note"],
    ) == (days(-35), False, "Notice board and Data Room")
    assert app["comments_close_on"] == days(-7)
    # First publication on day 10 (late); the second is due 28 days after it.
    app = do(planner, "step", app, {"step": "publish_1", "on": days(-30), "note": "Daily Graphic"})
    assert clock(app, "publish_1")["late"] is True
    assert (clock(app, "publish_2")["due_on"], clock(app, "publish_2")["overdue"]) == (
        days(-2),
        True,
    )
    # No objection: the sixty days run from the end of the comment period.
    assert (clock(app, "decide")["due_on"], clock(app, "decide")["rule"]) == (days(53), "r.33(15)")

    # An objection: it goes to the applicant within 14 days of the period ending,
    # and the sixty days then run from the applicant's reply.
    assert do(
        planner, "comments", app, {"kind": "petition", "name": "X", "text": "No"}, expect=(400,)
    )
    app = do(
        planner,
        "comments",
        app,
        {
            "kind": "objection",
            "name": "Kojo Antwi",
            "contact": "0200000001",
            "text": "It will bring traffic.",
            "on": days(-10),
        },
    )
    assert codes(app) == [
        "display",
        "publish_1",
        "direct_notice",
        "publish_2",
        "posted",
        "refer_objections",
        "response",
        "decide",
    ]
    assert (clock(app, "refer_objections")["due_on"], clock(app, "refer_objections")["rule"]) == (
        days(7),
        "r.33(14)",
    )
    assert clock(app, "decide")["due_on"] is None
    app = do(planner, "step", app, {"step": "refer_objections", "on": days(-5)})
    app = do(planner, "step", app, {"step": "response", "on": days(-3)})
    assert clock(app, "decide")["due_on"] == days(57)
    comment = app["comments"][0]
    app = do(
        planner,
        "respond",
        app,
        {"comment": comment["id"], "response": "A traffic study is attached."},
    )
    assert (
        app["comments"][0]["response"],
        app["comments"][0]["responded_on"],
        app["comments"][0]["name"],
    ) == ("A traffic study is attached.", str(TODAY), "Kojo Antwi")
    # Those who may not see personal data see what was said, not who said it.
    viewer = api(members_a[Role.VIEWER], district_a)
    seen = viewer.get(url("detail", app)).json()
    assert (seen["comments"][0]["name"], seen["comments"][0]["text"], seen["applicant_phone"]) == (
        "restricted",
        "It will bring traffic.",
        "restricted",
    )
    assert viewer.post(url("step", app), {"step": "posted"}, format="json").status_code == 403

    # The decision is the Assembly's: deferred with a reason, it is due in thirty days.
    assert planner.post(url("decide", app), {"approve": True}, format="json").status_code == 403
    assert do(admin, "defer", app, {"reason": " "}, expect=(400,))
    app = do(admin, "defer", app, {"reason": "The traffic study is awaited.", "on": days(-1)})
    assert (app["status"], clock(app, "decide")["due_on"], clock(app, "decide")["rule"]) == (
        "deferred",
        days(29),
        "r.33(17)",
    )
    assert do(admin, "decide", app, {"approve": False}, expect=(400,))  # a refusal needs reasons
    assert planner.get(url("paper", app), {"kind": "decision"}).status_code == 400
    app = do(admin, "decide", app, {"approve": True, "conditions": "Not more than three storeys."})
    assert (app["status"], app["decided_on"], clock(app, "decide")["done_on"]) == (
        "approved",
        str(TODAY),
        str(TODAY),
    )
    # r.33(19): gazetted and lodged within seven days of the approval.
    assert (codes(app)[-1], clock(app, "gazette")["due_on"]) == ("gazette", days(7))
    assert do(admin, "decide", app, {"approve": True}, expect=(400,))
    app = do(planner, "step", app, {"step": "gazette"})
    assert app["next_step"]["code"] == "direct_notice"  # still not done, and past its date

    # The papers.
    for kind in ("notice", "abutting", "decision"):
        paper = planner.get(url("paper", app), {"kind": kind})
        assert paper.status_code == 200 and paper.content.startswith(b"%PDF"), kind
    assert planner.get(url("paper", app), {"kind": "lands"}).status_code == 400

    # The approved zone goes onto the map, once, as an audited change.
    before = parcel(world, "P-002")
    audits = AuditLog.objects.filter(
        table_name="projects_feature", row_id=str(before["id"]), action="UPDATE"
    )
    audited = audits.count()
    assert planner.post(url("apply", app), {}, format="json").status_code == 403
    applied = do(admin, "apply", app)
    assert applied["written"] == {"parcels_changed": 1, "field": "land_use", "zoning_layer": False}
    assert applied["application"]["applied_on"] == str(TODAY)
    after = parcel(world, "P-002")
    assert (after["properties"]["land_use"], after["meta"]["version"]) == (
        "Re B",
        before["meta"]["version"] + 1,
    )
    assert audits.count() == audited + 1
    assert parcel(world, "P-001")["properties"]["land_use"] == "residential"
    assert do(admin, "apply", app)["written"]["parcels_changed"] == 0

    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(url("detail", app)).status_code == 404
    assert other.get(reverse(LIST)).json()["results"] == []


def test_approval_waits_for_the_public(world, admin):
    world.set_roles()
    app = receive(
        world, "rezoning", ["P-005"], proposed_zone="Co A", ground="structure_plan"
    ).json()
    # Not displayed yet: nobody has been invited to comment.
    assert do(admin, "decide", app, {"approve": True}, expect=(400,))
    app = do(world.client, "step", app, {"step": "display"})
    assert app["comments_close_on"] == days(28)
    refused = do(admin, "decide", app, {"approve": True}, expect=(400,))
    assert days(28) in str(refused)
    # A refusal does not wait; and a withdrawn application takes no more steps.
    other = receive(
        world, "rezoning", ["P-006"], proposed_zone="Co A", ground="structure_plan"
    ).json()
    other = do(world.client, "withdraw", other)
    assert other["status"] == "withdrawn" and other["next_step"] is None
    assert do(world.client, "step", other, {"step": "display"}, expect=(400,))
    app = do(admin, "decide", app, {"approve": False, "reasons": "Contrary to the structure plan."})
    assert app["status"] == "refused" and app["next_step"] is None
    assert do(admin, "apply", app, expect=(400,))


def test_a_change_of_use_is_tested_against_r34(world, admin):
    world.set_roles()
    planner = world.client
    assert receive(world, "change_of_use", ["P-001"]).status_code == 400  # to what use?
    app = receive(
        world,
        "change_of_use",
        ["P-001"],
        current_use="Residential",
        proposed_use="Shop",
        received_on=days(-31),
    ).json()
    assert (
        app["number"].startswith("DA/CU/")
        and app["summary"] == "a change of use of P-001 from Residential to Shop"
    )
    # It needs a planning permit, decided within thirty days.
    assert codes(app) == ["decide"]
    assert (
        clock(app, "decide")["due_on"],
        clock(app, "decide")["overdue"],
        clock(app, "decide")["rule"],
    ) == (days(-1), True, "r.44(10)")
    assert app["zone"]["value"] == "residential" and app["papers"] == []
    # Every test of r.34 is assessed before a decision, and all must be met to approve.
    assert do(admin, "decide", app, {"approve": True}, expect=(400,))
    assert do(planner, "assess", app, {"answers": {"parking": {"met": True}}}, expect=(400,))
    assert do(planner, "assess", app, {"answers": {"traffic": {"note": "?"}}}, expect=(400,))
    tests = ["permissible", "intention", "services", "traffic", "noise", "fire", "image", "privacy"]
    answers = {
        code: {"met": code != "traffic", "note": "Deliveries all day" if code == "traffic" else ""}
        for code in tests
    }
    app = do(planner, "assess", app, {"answers": answers})
    assert app["assessment"]["traffic"] == {"met": False, "note": "Deliveries all day"}
    refused = do(admin, "decide", app, {"approve": True}, expect=(400,))
    assert "traffic" in str(refused)
    app = do(
        planner,
        "assess",
        app,
        {"answers": {"traffic": {"met": True, "note": "Deliveries before 8 am only"}}},
    )
    app = do(admin, "decide", app, {"approve": True, "conditions": "Deliveries before 8 am only."})
    assert (app["status"], clock(app, "decide")["late"], [p["code"] for p in app["papers"]]) == (
        "approved",
        True,
        ["decision"],
    )
    # Only a change of use is assessed, and only a re-zoning is written to the map.
    assert do(admin, "apply", app, expect=(400,))
    other = receive(world, "subdivision", ["P-004"], lots=2).json()
    assert do(planner, "assess", other, {"answers": {"traffic": {"met": True}}}, expect=(400,))


def test_a_subdivision_and_what_the_public_sees(world, admin):
    """Gate: every clock of r.54; and the application is on display in the Public Data Room."""
    world.set_roles()
    planner = world.client
    anyone = APIClient()
    public = reverse("public-land-applications", args=["DA"])
    assert receive(world, "consolidation", ["P-004"]).status_code == 400  # two parcels or more
    assert receive(world, "consolidation", ["P-004", "P-005"]).json()["number"].startswith("DA/CN/")
    app = receive(world, "subdivision", ["P-003"], lots=3, received_on=days(-30)).json()
    assert (
        app["number"].startswith("DA/SD/")
        and app["summary"] == "the subdivision of P-003 into 3 plots"
    )
    assert codes(app) == ["acknowledge", "advertise", "lands_commission", "display", "decide"]
    assert (
        clock(app, "acknowledge")["due_on"],
        clock(app, "advertise")["due_on"],
        clock(app, "advertise")["overdue"],
    ) == (days(-23), days(-9), True)
    # r.54(9): sixty days from receipt, whatever else happens.
    assert (clock(app, "decide")["due_on"], clock(app, "decide")["rule"]) == (days(30), "r.54(9)")
    assert app["next_step"]["code"] == "acknowledge"
    assert do(admin, "decide", app, {"approve": True}, expect=(400,))  # not advertised yet
    # The district's statutory deadlines count it: one open application with a step past its date.
    report = planner.get(reverse("reports-compliance")).json()
    assert (report["land"]["open"], report["land"]["overdue"], report["overdue"]) == (2, 1, 1)
    assert (report["land"]["late"][0]["number"], report["land"]["late"][0]["rule"]) == (
        app["number"],
        "r.54(2)(a)",
    )

    admin.patch(reverse("dataroom-settings"), {"is_open": True}, format="json")
    admin.post(reverse("dataroom-publication-list"), {"project": world.project}, format="json")
    assert anyone.get(public).json() == {"results": []}  # nothing on display yet

    app = do(planner, "step", app, {"step": "acknowledge", "on": days(-28)})
    app = do(planner, "step", app, {"step": "advertise", "on": days(-20), "note": "Ghanaian Times"})
    assert (
        clock(app, "acknowledge")["late"],
        clock(app, "advertise")["late"],
        app["comments_close_on"],
    ) == (False, False, days(-6))
    shown = anyone.get(public).json()["results"]
    assert shown == [
        {
            "number": app["number"],
            "kind": "Subdivision of land",
            "proposal": "the subdivision of P-003 into 3 plots",
            "locality": "Relations plan",
            "received_on": days(-30),
            "comments_close_on": days(-6),
            "status": "Being considered",
            "decided_on": None,
        }
    ]

    # The Lands Commission comments: the applicant is told, and has 14 days to respond.
    app = do(
        planner,
        "comments",
        app,
        {
            "kind": "lands_commission",
            "name": "Lands Commission, Accra",
            "text": "The plots must each front a road.",
            "on": days(-8),
        },
    )
    assert codes(app) == [
        "acknowledge",
        "advertise",
        "lands_commission",
        "display",
        "notify_applicant",
        "response",
        "decide",
    ]
    assert clock(app, "response")["due_on"] is None
    app = do(planner, "step", app, {"step": "notify_applicant", "on": days(-5)})
    assert (clock(app, "response")["due_on"], clock(app, "response")["rule"]) == (
        days(9),
        "r.54(7)",
    )

    app = do(admin, "decide", app, {"approve": True})
    # r.54(10) and (12): the approval is published, and the Lands Commission told within thirty days.
    assert codes(app)[-2:] == ["publish_approval", "notify_lands"]
    assert (clock(app, "notify_lands")["due_on"], clock(app, "notify_lands")["rule"]) == (
        days(30),
        "r.54(12)",
    )
    assert [p["code"] for p in app["papers"]] == ["notice", "decision", "lands"]
    for kind in ("notice", "decision", "lands"):
        assert planner.get(url("paper", app), {"kind": kind}).content.startswith(b"%PDF"), kind
    assert planner.get(url("paper", app), {"kind": "abutting"}).status_code == 400
    assert anyone.get(public).json()["results"][0]["status"] == "Approved"
    assert AuditLog.objects.filter(
        table_name="landchange_application", row_id=str(app["id"]), action="UPDATE"
    ).exists()


def test_an_approved_subdivision_is_drawn_and_a_consolidation_joined(world, admin):
    """P-003 (30 x 30 m) into three plots of equal area; P-004 and P-005 into one."""
    world.set_roles()
    planner = world.client
    app = receive(world, "subdivision", ["P-003"], lots=3, received_on=days(-30)).json()
    assert do(planner, "draw", app, expect=(400,))  # not approved yet
    do(planner, "step", app, {"step": "acknowledge", "on": days(-28)})
    do(planner, "step", app, {"step": "advertise", "on": days(-25)})
    app = do(admin, "decide", app, {"approve": True})
    drawn = do(planner, "draw", app)
    areas = [p["area_m2"] for p in drawn["plots"]]
    assert len(areas) == 3 and sum(areas) == pytest.approx(900, rel=0.01)
    assert max(areas) - min(areas) < 1.0  # equal, within a square metre
    features = world.client.get(reverse("layer-features", args=[drawn["layer"]])).json()["features"]
    assert sorted(f["properties"]["plot_no"] for f in features) == [
        f"{app['number'].split('/')[-1]}-{n}" for n in (1, 2, 3)
    ]
    assert {f["properties"]["parent"] for f in features} == {"P-003"}
    # Drawn again: replaced, not added to.
    assert len(do(planner, "draw", app)["plots"]) == 3
    assert (
        len(world.client.get(reverse("layer-features", args=[drawn["layer"]])).json()["features"])
        == 3
    )
    # The cadastral parcel is untouched.
    assert "P-003" in world.features("parcels", "parcel_id")

    joined = receive(world, "consolidation", ["P-004", "P-005"], received_on=days(-30)).json()
    do(planner, "step", joined, {"step": "acknowledge", "on": days(-28)})
    do(planner, "step", joined, {"step": "advertise", "on": days(-25)})
    joined = do(admin, "decide", joined, {"approve": True})
    one = do(planner, "draw", joined)
    assert len(one["plots"]) == 1 and one["plots"][0]["area_m2"] == pytest.approx(1800, rel=0.01)
    rezoning = receive(
        world, "rezoning", ["P-006"], proposed_zone="Co A", ground="structure_plan"
    ).json()
    assert do(planner, "draw", rezoning, expect=(400,))

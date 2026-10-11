# ruff: noqa: E501 - long assertions read better on one line
"""Phase 14: the national zoning standards (LUSPA, 2025), the rules they add,
and the zoning scheme register. On the fixture community: 30 x 30 m plots
either side of Main Street, each with a 24 x 24 m building 3 m from every
boundary (B-003: 0.5 m from its eastern side). Each plot's front is the edge
facing Main Street, 30 m wide."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from relations import zoning
from relations.models import ZoningScheme
from relations.tests.test_relations import ROLE_OF

pytestmark = pytest.mark.django_db

ALL = ["B-001", "B-002", "B-003", "B-004", "B-005", "B-006"]


def standard(admin, **values):
    created = admin.post(reverse("standard-list"), values, format="json")
    assert created.status_code == 201, created.content
    return created.json()


def breaches(world, rule):
    return [building for building, found in world.pairs("violates") if found == rule]


# --- The national standards as data ---------------------------------------------------------------


def test_the_national_zones_and_their_standards(planner):
    body = planner.get(reverse("relations-zones")).json()
    assert "2025" in body["source"]
    zones = {z["code"]: z for z in body["zones"]}
    assert len(zones) == 36
    # Section 2.6 of the standards, row by row: plot (m2), width (ft), coverage (%), front/side/rear (m).
    printed = {
        "Re A": (930, 70, 40, 6, 3, 5),
        "Re B": (647, 50, 50, 6, 3, 3),
        "Re C": (4047, None, 75, 6, 3, 3),
        "Re D": (182, 40, 60, 3, 1.5, 1.5),
        "Re Z": (1011, 70, 75, 2.5, 2.5, 3),
    }
    for code, (plot, width_ft, cover, front, side, rear) in printed.items():
        s = zones[code]["standard"]
        assert (s["min_plot_m2"], s["max_coverage_pct"]) == (plot, cover), code
        assert (s["front_setback_m"], s["side_setback_m"], s["rear_setback_m"]) == (
            front,
            side,
            rear,
        ), code
        assert s["min_width_m"] == (
            None if width_ft is None else pytest.approx(width_ft * 0.3048, abs=0.05)
        ), code
    assert (zones["Re A"]["standard"]["max_floors"], zones["Re B"]["standard"]["max_floors"]) == (
        2,
        3,
    )
    assert (zones["Re C"]["standard"]["min_floors"], zones["Re D"]["standard"]["max_floors"]) == (
        3,
        3,
    )
    assert zones["Re A"]["colour"] == "#CC7722" and zones["CBD"]["colour"] == "#2E4DA7"
    assert "Block of flats" in zones["Re A"]["prohibited"]
    assert zones["CBD"]["standard"] is None  # no site standards table for it


def test_zone_values_are_recognised_however_they_are_written():
    def code(written):
        zone = zoning.match(written)
        return zone.code if zone else None

    for written in ("Re A", "ReA", "re a", "RE-A", "Residential Zone A", "residential a"):
        assert code(written) == "Re A", written
    assert code("H Po") == "H Po" and code("cbd") == "CBD"
    # Not a national zone: stays the district's own word.
    assert code("residential") is None and code("") is None and code(None) is None


def test_a_district_adopts_the_national_standards(planner, admin):
    url = reverse("standard-adopt-national")
    assert planner.post(url, {}, format="json").status_code == 403  # administrators set standards
    assert (
        admin.post(url, {"zones": ["CBD"]}, format="json").status_code == 400
    )  # no site standards
    assert admin.post(url, {"zones": ["Nowhere"]}, format="json").status_code == 400

    first = admin.post(url, {}, format="json")
    assert first.status_code == 200 and first.json()["added"] == [
        "Re A",
        "Re B",
        "Re C",
        "Re D",
        "Re Z",
    ]
    rows = {s["zone"]: s for s in admin.get(reverse("standard-list")).json()}
    assert rows["Re A"]["front_setback_m"] == 6 and rows["Re A"]["source"] == "luspa-2025"
    assert "cemetery" in rows["Re A"]["prohibited_uses"]

    # The district tightens one: it becomes its own, and adopting again leaves it alone.
    changed = admin.patch(
        reverse("standard-detail", args=[rows["Re B"]["id"]]), {"front_setback_m": 8}, format="json"
    )
    assert changed.status_code == 200 and changed.json()["source"] == ""
    again = admin.post(url, {}, format="json").json()
    assert again == {"added": [], "updated": ["Re A", "Re C", "Re D", "Re Z"], "kept": ["Re B"]}
    replaced = admin.post(url, {"zones": ["ReB"], "replace": True}, format="json").json()
    assert replaced["updated"] == ["Re B"]
    assert (
        admin.get(reverse("standard-detail", args=[rows["Re B"]["id"]])).json()["front_setback_m"]
        == 6
    )

    assert (
        admin.patch(
            reverse("standard-detail", args=[rows["Re A"]["id"]]), {"min_floors": 4}, format="json"
        ).status_code
        == 400
    )
    assert (
        AuditLog.objects.filter(table_name="relations_developmentstandard", action="INSERT").count()
        == 5
    )


# --- The rules they add -----------------------------------------------------------------------------


def test_front_side_and_rear_setbacks_are_measured_from_the_street(world, admin):
    """Gate: each of the three setbacks flags its seeded breach, and only that."""
    world.set_roles()
    row = standard(admin, zone="residential", front_setback_m=3, side_setback_m=3, rear_setback_m=3)
    world.run()
    assert world.pairs("violates") == [("B-003", "setback_side")]
    (link,) = world.links(type="violates")
    assert (
        link["details"]["measured_m"] == pytest.approx(0.5, abs=0.05)
        and link["details"]["required_m"] == 3
    )

    # 6 m at the front: every building stands 3 m from its street side.
    url = reverse("standard-detail", args=[row["id"]])
    admin.patch(url, {"front_setback_m": 6}, format="json")
    world.run()
    assert breaches(world, "setback_front") == ALL and breaches(world, "setback_rear") == []
    front = world.links(type="violates", rule="setback_front")[0]
    assert front["details"]["measured_m"] == pytest.approx(3.0, abs=0.05)

    # 5 m at the back, 3 m at the front again.
    admin.patch(url, {"front_setback_m": 3, "rear_setback_m": 5}, format="json")
    world.run()
    assert breaches(world, "setback_rear") == ALL and breaches(world, "setback_front") == []
    assert breaches(world, "setback_side") == ["B-003"]


def test_without_streets_the_front_is_unknown(world, admin):
    world.set_roles({"buildings": "properties", "parcels": "parcels"})
    standard(admin, zone="residential", front_setback_m=6, side_setback_m=3, rear_setback_m=5)
    world.run()
    # The smallest of the three is asked of every side; nothing is guessed about the front.
    assert world.pairs("violates") == [("B-003", "setback")]
    (link,) = world.links(type="violates")
    assert link["details"]["front_unknown"] is True and link["details"]["required_m"] == 3


def test_plot_width_storeys_and_prohibited_uses(world, admin):
    world.set_roles()
    row = standard(
        admin, zone="residential", min_width_m=35, min_floors=2, prohibited_uses=["Filling Station"]
    )
    world.run()
    assert breaches(world, "plot_width") == ALL  # each plot is 30 m wide at the street
    width = world.links(type="violates", rule="plot_width")[0]
    assert (
        width["details"]["measured_m"] == pytest.approx(30.0, abs=0.3)
        and width["details"]["required_m"] == 35
    )
    assert breaches(world, "too_few_floors") == [
        "B-002",
        "B-004",
        "B-006",
    ]  # the single-storey ones
    assert breaches(world, "prohibited_use") == []

    b2 = world.features("buildings", "property_id")["B-002"]
    edited = world.client.patch(
        reverse("feature-detail", args=[b2["id"]]),
        {"version": b2["meta"]["version"], "properties": {"use": "Fuel filling station"}},
        format="json",
    )
    assert edited.status_code == 200, edited.content
    admin.patch(
        reverse("standard-detail", args=[row["id"]]),
        {"min_width_m": 25, "min_floors": None},
        format="json",
    )
    world.run()
    assert breaches(world, "plot_width") == [] and breaches(world, "too_few_floors") == []
    (use,) = world.links(type="violates", rule="prohibited_use")
    # Read from the recorded use: a suggestion for a person to confirm.
    assert (
        use["subject"]["label"] == "B-002"
        and use["method"] == "inferred"
        and use["confidence"] == 0.7
    )
    assert use["details"]["matched"] == "filling station"


def test_a_zoning_layer_brings_the_national_standards_and_colours(
    world, admin, api, members_a, district_a
):
    # One zone over the whole community, written the way a drawing might have it.
    corners = [
        p
        for f in world.features("parcels", "parcel_id").values()
        for p in f["geometry"]["coordinates"][0]
    ]
    if isinstance(corners[0][0], list):  # multipolygons
        corners = [p for ring in corners for p in ring]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    box = [
        [min(xs) - 10, min(ys) - 10],
        [max(xs) + 10, min(ys) - 10],
        [max(xs) + 10, max(ys) + 10],
        [min(xs) - 10, max(ys) + 10],
        [min(xs) - 10, min(ys) - 10],
    ]
    world.add_layer("zoning", "polygon", [{"name": "zone", "type": "text"}], domain="J")
    world.add("zoning", {"type": "Polygon", "coordinates": [box]}, zone="ReB")
    far = [[x + 5000, y] for x, y in box]
    world.add("zoning", {"type": "Polygon", "coordinates": [far]}, zone="Chief's palace")

    style_url = reverse("project-zoning-style", args=[world.project])
    assert world.client.post(style_url).status_code == 400  # no zoning layer named yet
    world.set_roles({**ROLE_OF, "zoning": "zoning"})
    assert admin.post(reverse("standard-adopt-national"), {}, format="json").status_code == 200
    world.run()
    # Re B: 6 m at the front (3 m built), 50% coverage (64% built); sides and back at 3 m are met.
    assert breaches(world, "setback_front") == ALL and breaches(world, "coverage") == ALL
    assert breaches(world, "setback_side") == ["B-003"] and breaches(world, "setback_rear") == []
    assert breaches(world, "plot_size") == [] and breaches(world, "plot_width") == []
    assert world.links(type="violates", rule="coverage")[0]["details"]["zone"] == "Re B"

    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.post(style_url).status_code == 403
    styled = world.client.post(style_url)
    assert styled.status_code == 200, styled.content
    assert styled.json()["coloured"] == ["ReB"] and styled.json()["unknown"] == ["Chief's palace"]
    layer = world.client.get(reverse("layer-detail", args=[world.layers["zoning"]])).json()
    assert layer["style"]["kind"] == "categorized" and layer["style"]["field"] == "zone"
    assert (
        layer["style"]["categories"][0]["value"] == "ReB"
        and layer["style"]["categories"][0]["fill"] == "#E5AA70"
    )


# --- The zoning scheme register -------------------------------------------------------------------


def test_the_zoning_scheme_register_tracks_its_deadlines(
    world, api, members_a, district_a, district_b, make_member
):
    url = reverse("zoning-scheme-list")
    today = date.today()
    viewer = api(members_a[Role.VIEWER], district_a)
    body = {
        "project": world.project,
        "name": "Kasoa zoning scheme",
        "structure_plan_approved_on": str(today - timedelta(days=120)),
    }
    assert viewer.post(url, body, format="json").status_code == 403
    created = world.client.post(url, body, format="json")
    assert created.status_code == 201, created.content
    scheme = created.json()
    # r.29(1): 90 days from the structure plan's approval, 120 have passed.
    assert scheme["status"] == "draft" and scheme["deadlines"]["prepare"]["overdue"] is True
    assert scheme["deadlines"]["prepare"]["due_on"] == str(today - timedelta(days=30))

    detail = reverse("zoning-scheme-detail", args=[scheme["id"]])
    assert (
        world.client.patch(detail, {"status": "approved"}, format="json").status_code == 400
    )  # when?
    approved = world.client.patch(
        detail,
        {
            "status": "approved",
            "approved_on": str(today - timedelta(days=40)),
            "update_every_months": 60,
        },
        format="json",
    ).json()
    send = approved["deadlines"]["send_to_luspa"]
    # r.29(6): to LUSPA within 28 days; 40 have passed and it hasn't gone.
    assert (
        send["due_on"] == str(today - timedelta(days=12))
        and send["overdue"] is True
        and send["done_on"] is None
    )
    assert "prepare" not in approved["deadlines"]
    update_due = date.fromisoformat(approved["deadlines"]["update"]["due_on"])
    assert (update_due.year - today.year) in (4, 5) and approved["deadlines"]["update"][
        "overdue"
    ] is False

    sent = world.client.patch(detail, {"sent_to_luspa_on": str(today)}, format="json").json()
    assert sent["deadlines"]["send_to_luspa"]["overdue"] is False and sent["deadlines"][
        "send_to_luspa"
    ]["done_on"] == str(today)
    assert viewer.get(url, {"project": world.project}).json()[0]["id"] == scheme["id"]
    assert AuditLog.objects.filter(table_name="relations_zoningscheme").count() == 3

    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(url).json() == [] and other.get(detail).status_code == 404
    assert (
        other.post(url, {"project": world.project, "name": "Theirs"}, format="json").status_code
        == 400
    )
    with tenant_context(district_b.id):
        assert ZoningScheme.objects.count() == 0

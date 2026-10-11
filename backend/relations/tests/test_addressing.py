# ruff: noqa: E501 - long assertions read better on one line
"""Phase 20: street codes and property numbers (L.I. 2384 r.28). The fixture
community: Main Street runs west to east; B-001 to B-003 stand north of it
(on the left, going east) at about 535, 565 and 596 m from its start, and
B-004 to B-006 opposite them on the south side."""

import pytest
from django.urls import reverse

from core.models import AuditLog, Role
from relations import addressing

pytestmark = pytest.mark.django_db


def points(feature):
    """A line's positions, whether it came in as one line or several."""
    coordinates = feature["geometry"]["coordinates"]
    if isinstance(coordinates[0][0], int | float):
        return coordinates
    return [p for part in coordinates for p in part]


def numbers(proposal):
    return {row["label"]: row["number"] for row in proposal["rows"]}


def test_a_number_says_how_far_along_the_street():
    # Every 10 m: the pair of numbers (odd, even) for each stretch.
    assert [addressing.number_for(d, True, 10) for d in (0, 9.9, 10, 25, 152, 535)] == [
        1,
        1,
        1,
        3,
        15,
        53,
    ]
    assert [addressing.number_for(d, False, 10) for d in (0, 9.9, 10, 25, 152, 535)] == [
        2,
        2,
        2,
        4,
        16,
        54,
    ]
    # Every metre: the number is about the distance in metres.
    assert (addressing.number_for(152.4, True, 1), addressing.number_for(152.4, False, 1)) == (
        153,
        154,
    )
    assert [addressing._letters(n) for n in (0, 1, 2, 26, 27)] == ["", "A", "B", "Z", "AA"]


def test_properties_are_numbered_along_their_street(
    world, api, members_a, district_a, district_b, make_member
):
    """Gate: numbers follow distance and side, and nothing changes until applied."""
    url = reverse("project-addressing", args=[world.project])
    planner = world.client
    assert planner.get(url).status_code == 400  # which layers are the properties and the streets?
    world.set_roles()

    proposal = planner.get(url).json()
    assert (
        proposal["method"],
        proposal["odd_side"],
        proposal["properties"],
        proposal["numbered"],
        proposal["without_a_street"],
    ) == ("decametric", "left", 6, 6, 0)
    # Odd on the left going east (the north side); about a tenth of the metres from the start.
    assert numbers(proposal) == {
        "B-001": "53",
        "B-002": "57",
        "B-003": "59",
        "B-004": "54",
        "B-005": "58",
        "B-006": "60",
    }
    first = next(r for r in proposal["rows"] if r["label"] == "B-001")
    assert (first["street_name"], first["street_code"], first["side"], first["address"]) == (
        "Main Street",
        "SMA-001",
        "left",
        "53 Main Street",
    )
    assert first["distance_m"] == pytest.approx(535, abs=2) and first[
        "off_street_m"
    ] == pytest.approx(13, abs=1)
    assert (
        proposal["streets"] == 3 and proposal["new_street_codes"] == [] and proposal["changes"] == 6
    )

    # Other conventions: even on the left; one after another; from the other end of the street.
    assert numbers(planner.get(url, {"odd_side": "right"}).json()) == {
        "B-001": "54",
        "B-002": "58",
        "B-003": "60",
        "B-004": "53",
        "B-005": "57",
        "B-006": "59",
    }
    assert numbers(planner.get(url, {"method": "sequential"}).json()) == {
        "B-001": "1",
        "B-002": "3",
        "B-003": "5",
        "B-004": "2",
        "B-005": "4",
        "B-006": "6",
    }
    east_end = points(world.features("streets", "name")["Main Street"])[-1]
    turned = planner.post(
        reverse("crs-transform"),
        {
            "geometry": {"type": "Point", "coordinates": east_end},
            "from_crs": "EPSG:2136",
            "to_crs": "EPSG:4326",
        },
        format="json",
    ).json()["geometry"]["coordinates"]
    from_east = planner.get(
        url, {"method": "sequential", "lon": turned[0], "lat": turned[1]}
    ).json()
    # From the east end the north side is on the right, and B-003 comes first.
    assert numbers(from_east) == {
        "B-003": "2",
        "B-002": "4",
        "B-001": "6",
        "B-006": "1",
        "B-005": "3",
        "B-004": "5",
    }
    assert planner.get(url, {"method": "random"}).status_code == 400
    assert planner.get(url, {"lon": "east"}).status_code == 400

    # The schedule for the sign-maker.
    schedule = planner.get(url, {"type": "csv"})
    assert schedule.status_code == 200 and schedule["Content-Type"] == "text/csv"
    lines = schedule.content.decode("utf-8-sig").splitlines()
    assert (
        lines[0] == "Street,Street code,Number,Side,Metres from the start,Property,Address"
        and len(lines) == 7
    )
    assert lines[1].startswith("Main Street,SMA-001,53,left,") and lines[1].endswith(
        ",B-001,53 Main Street"
    )

    # Nothing is on the map yet. Viewers can look; planners apply.
    assert "house_no" not in world.features("buildings", "property_id")["B-001"]["properties"]
    viewer = api(members_a[Role.VIEWER], district_a)
    assert (
        viewer.get(url).status_code == 200
        and viewer.post(url, {}, format="json").status_code == 403
    )
    applied = planner.post(url, {}, format="json")
    assert applied.status_code == 200, applied.content
    assert applied.json() == {"written": {"streets": 0, "properties": 6}, "numbered": 6}
    building = world.features("buildings", "property_id")["B-001"]
    assert (building["properties"]["house_no"], building["properties"]["street"]) == (
        "53",
        "Main Street",
    )
    assert building["meta"]["version"] == 2
    assert (
        AuditLog.objects.filter(
            table_name="projects_feature", row_id=str(building["id"]), action="UPDATE"
        ).count()
        == 1
    )
    # Applying again changes nothing; the proposal now matches the map.
    assert planner.post(url, {}, format="json").json()["written"] == {"streets": 0, "properties": 0}
    assert planner.get(url).json()["changes"] == 0

    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert (
        other.get(url).status_code == 404 and other.post(url, {}, format="json").status_code == 404
    )


def test_streets_without_a_code_get_the_next_free_one(world):
    world.set_roles()
    url = reverse("project-addressing", args=[world.project])
    line = points(world.features("streets", "name")["Asafo Road"])
    world.add(
        "streets",
        {"type": "LineString", "coordinates": [[p[0] + 300, p[1]] for p in line]},
        name="New Road",
    )
    world.add("streets", {"type": "LineString", "coordinates": [[p[0] + 600, p[1]] for p in line]})
    proposal = world.client.get(url).json()
    # SMA-001 to 003 are taken by the fixture's streets; the district here is "DA".
    assert [c["code"] for c in proposal["new_street_codes"]] == ["DA-001", "DA-002"]
    assert proposal["streets"] == 5 and proposal["streets_without_a_name"] == 1
    written = world.client.post(url, {}, format="json").json()["written"]
    assert written["streets"] == 2
    assert world.features("streets", "name")["New Road"]["properties"]["street_code"] == "DA-001"

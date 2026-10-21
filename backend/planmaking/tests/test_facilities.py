# ruff: noqa: E501 - long assertions read better on one line
"""Facilities against the national planning standards (LUSPA 2025), for the
fixture community: six buildings along Main Street."""

import pytest
from django.urls import reverse

from core.models import Role
from planmaking import facilities
from relations.tests.test_relations import ROLE_OF, centre

pytestmark = pytest.mark.django_db


def test_a_facility_is_known_by_its_type():
    assert [
        facilities.classify(t)
        for t in (
            "Kasoa M/A Primary School",
            "JHS Block",
            "school",
            "CHPS compound",
            "Polyclinic",
            "Health Centre",
            "Central Market",
            "borehole",
            "Mosque",
            None,
        )
    ] == [
        "primary",
        "jhs",
        "primary",
        "chps",
        "polyclinic",
        "health_centre",
        "market",
        "borehole",
        None,
        None,
    ]


def test_facilities_against_the_standards(world, api, members_a, district_a):
    url = reverse("facility-check", args=[world.project])
    world.set_roles()
    nothing = world.client.get(url).json()
    assert (nothing["results"], nothing["facilities_layer"]) == (
        [],
        None,
    )  # no facilities layer yet
    # Six buildings, five people each by default.
    assert nothing["population"] == {
        "value": 30,
        "source": "estimated: 6 buildings × 5 people",
        "estimate": True,
    }

    world.add_layer(
        "Facilities",
        "point",
        [{"name": "type", "type": "text"}, {"name": "name", "type": "text"}],
        domain="E",
    )
    here = centre(world.features("buildings", "property_id")["B-001"])
    for kind in ("Primary School", "Borehole", "Mosque"):
        world.add("Facilities", {"type": "Point", "coordinates": here}, type=kind)
    world.set_roles({**ROLE_OF, "Facilities": "facilities"})

    data = world.client.get(url, {"population": "12000"}).json()
    rows = {r["code"]: r for r in data["results"]}
    assert data["population"] == {"value": 12000, "source": "given"}
    assert data["facilities_layer"]["name"] == "Facilities" and data["homes"] == 6
    # One primary school for every 5,000, within 2.5 km of every home.
    assert {
        k: rows["primary"][k] for k in ("need", "have", "short", "walk_m", "beyond", "status")
    } == {"need": 3, "have": 1, "short": 2, "walk_m": 2500, "beyond": 0, "status": "short"}
    # No JHS: two are needed, and every home is beyond 3.2 km of one.
    assert {k: rows["jhs"][k] for k in ("need", "have", "beyond")} == {
        "need": 2,
        "have": 0,
        "beyond": 6,
    }
    assert (rows["borehole"]["need"], rows["borehole"]["have"]) == (40, 1)
    # Parks: 1.2 acres for every 1,000 people.
    assert (rows["park"]["acres_need"], rows["park"]["acres_have"], rows["park"]["status"]) == (
        14.4,
        0.0,
        "short",
    )
    assert rows["primary"]["section"] == "3.1.1.2(b)" and data["source"].startswith(
        "Revised Zoning Guidelines"
    )
    assert data["unclassified"] == [{"type": "Mosque", "count": 1}]

    assert world.client.get(url, {"per_building": "10"}).json()["population"]["value"] == 60
    assert world.client.get(url, {"population": "many"}).status_code == 400
    assert world.client.get(url, {"population": "-5"}).status_code == 400
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(url).status_code == 200

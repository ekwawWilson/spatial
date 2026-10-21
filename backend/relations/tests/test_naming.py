# ruff: noqa: E501 - long assertions read better on one line
"""Street names from proposal to signs (L.I. 2384 r.28). The fixture has
three named streets: Main Street, Asafo Road and Market Road."""

from datetime import date

import pytest
from django.urls import reverse

from core.models import AuditLog, Role

pytestmark = pytest.mark.django_db

TODAY = str(date.today())


def street_id(world, name):
    return world.features("streets", "name")[name]["id"]


def step(client, item, action, body=None, expect=200):
    done = client.post(
        reverse(f"street-name-{action}", args=[item["id"]]), body or {}, format="json"
    )
    assert done.status_code == expect, (action, done.status_code, done.content)
    return done.json()


def test_a_street_is_named(world, admin, api, members_a, district_a):
    world.set_roles()
    planner = world.client
    market = street_id(world, "Market Road")
    url = reverse("street-name-list")
    assert (
        planner.post(
            url, {"project": world.project, "street": market, "name": "  "}, format="json"
        ).status_code
        == 400
    )
    proposed = planner.post(
        url,
        {
            "project": world.project,
            "street": market,
            "name": "Yaa  Asantewaa Avenue",
            "basis": "Queen mother of Ejisu",
            "proposed_by": "Unit Committee",
        },
        format="json",
    )
    assert proposed.status_code == 201, proposed.content
    item = proposed.json()
    assert (item["name"], item["status"], item["clashes"]) == (
        "Yaa Asantewaa Avenue",
        "proposed",
        [],
    )
    # One name at a time for a street.
    assert (
        planner.post(
            url, {"project": world.project, "street": market, "name": "Other"}, format="json"
        ).status_code
        == 400
    )

    # The Committee decides only after the community has been consulted, and only the Committee decides.
    step(admin, item, "decide", {"approve": True}, expect=400)
    item = step(planner, item, "consult", {"note": "Durbar at the chief's palace, 120 present."})
    assert (item["status"], item["consulted_on"]) == ("consulted", TODAY)
    assert (
        planner.post(
            reverse("street-name-decide", args=[item["id"]]), {"approve": True}, format="json"
        ).status_code
        == 403
    )

    # It is on the Spatial Planning Committee's next agenda.
    meeting = admin.post(
        reverse("committee-meeting-list"), {"committee": "dspc", "held_on": TODAY}, format="json"
    ).json()
    assert [i["title"] for i in meeting["agenda"] if i["type"] == "street"] == [
        "Street name: Yaa Asantewaa Avenue (Relations plan)"
    ]

    approved = step(admin, item, "decide", {"approve": True, "note": "Minute 4 of the meeting."})
    assert (approved["status"], approved["previous_name"], approved["written_to_map"]) == (
        "approved",
        "Market Road",
        True,
    )
    # Now on the map, as an audited change.
    street = world.features("streets", "name")["Yaa Asantewaa Avenue"]
    assert street["id"] == market
    assert AuditLog.objects.filter(
        table_name="projects_feature", row_id=str(market), action="UPDATE"
    ).exists()

    step(planner, approved, "mark", {"step": "published"})
    signed = step(planner, approved, "mark", {"step": "signs"})
    assert (signed["published_on"], signed["signs_on"]) == (TODAY, TODAY)
    assert (
        planner.get(url, {"project": world.project, "status": "approved"}).json()["results"][0][
            "name"
        ]
        == "Yaa Asantewaa Avenue"
    )
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(url, {"project": world.project}).status_code == 200
    assert (
        viewer.post(
            url, {"project": world.project, "street": market, "name": "X"}, format="json"
        ).status_code
        == 403
    )


def test_a_name_already_used_is_not_approved(world, admin):
    world.set_roles()
    planner = world.client
    item = planner.post(
        reverse("street-name-list"),
        {"project": world.project, "street": street_id(world, "Market Road"), "name": "asafo road"},
        format="json",
    ).json()
    assert item["clashes"] == [f"already the name of street #{street_id(world, 'Asafo Road')}"]
    step(planner, item, "consult")
    refused = step(admin, item, "decide", {"approve": True}, expect=400)
    assert "should be unique" in str(refused)
    refused = step(admin, item, "decide", {"approve": False, "note": "Already in use."})
    assert refused["status"] == "refused"
    step(planner, refused, "mark", {"step": "signs"}, expect=400)
    assert "Market Road" in world.features("streets", "name")  # unchanged

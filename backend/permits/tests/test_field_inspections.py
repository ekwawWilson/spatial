# ruff: noqa: E501 - long assertions read better on one line
"""Permit site inspections done in the field: listed in every pull, sent
back as a change, and recorded as if in the office (r.44(7)(f))."""

import uuid

import pytest
from django.urls import reverse

from core.models import Role

pytestmark = pytest.mark.django_db
DEVICE = "phone-1"


def receive(world, parcel):
    site = world.features("parcels", "parcel_id")[parcel]
    made = world.client.post(
        reverse("permit-application-list"),
        {
            "project": world.project,
            "kind": "development",
            "category": "building",
            "applicant_name": "Ama Mensah",
            "applicant_phone": "0240000000",
            "proposed_use": "Residential",
            "proposed_floors": 2,
            "site_feature": site["id"],
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    return made.json()


def inspection_change(permit_id, **extra):
    return {
        "change_id": str(uuid.uuid4()),
        "op": "inspection",
        "inspection": {
            "permit": permit_id,
            "findings": {"started": "No, the site is bare."},
            "summary": "Setbacks can be met.",
            **extra,
        },
    }


def push(client, *changes):
    response = client.post(
        reverse("sync-push"), {"device_id": DEVICE, "changes": list(changes)}, format="json"
    )
    assert response.status_code == 200, response.content
    return response.json()["results"]


def test_a_site_inspection_from_the_field(world, api, members_a, district_a):
    officer = api(members_a[Role.FIELD_OFFICER], district_a)
    viewer = api(members_a[Role.VIEWER], district_a)
    waiting = receive(world, "P-001")
    receive(world, "P-002")  # received but not acknowledged: not for inspection yet
    world.client.post(
        reverse("permit-application-acknowledge", args=[waiting["id"]]), {}, format="json"
    )

    layers = ",".join(str(i) for i in world.layers.values())
    pulled = officer.get(reverse("sync-pull"), {"project": world.project, "layers": layers}).json()
    [listed] = pulled["inspections"]
    assert (listed["permit"], listed["number"], listed["purpose"], listed["storeys"]) == (
        waiting["id"],
        waiting["number"],
        "application",
        2,
    )
    assert listed["title"] == "Erection of a building or structure: Residential"
    assert (
        len(listed["centre"]) == 2
        and -3.5 < listed["centre"][0] < 1.5
        and 4.5 < listed["centre"][1] < 11.5
    )  # in Ghana
    assert listed["due_on"] and [p["code"] for p in listed["points"]][0]
    assert "Ama" not in str(listed) and "0240000000" not in str(listed)

    # Recorded from the phone, once even if sent twice.
    change = inspection_change(
        waiting["id"], findings={listed["points"][0]["code"]: "No, the site is bare."}
    )
    [result] = push(officer, change)
    assert result["status"] == "applied", result
    [again] = push(officer, change)
    assert again.get("repeat") is True
    detail = world.client.get(reverse("permit-application-detail", args=[waiting["id"]])).json()
    assert (
        len(detail["inspections"]) == 1
        and detail["inspections"][0]["summary"] == "Setbacks can be met."
    )
    assert detail["inspections"][0]["inspected_by"] == members_a[Role.FIELD_OFFICER].email

    # A viewer can't sync at all; an unknown application, an unknown point, a bad date are refused.
    refused = viewer.post(
        reverse("sync-push"),
        {"device_id": DEVICE, "changes": [inspection_change(waiting["id"])]},
        format="json",
    )
    assert refused.status_code == 403
    assert push(officer, inspection_change(999_999))[0]["status"] == "rejected"
    assert (
        push(officer, inspection_change(waiting["id"], findings={"colour": "blue"}))[0]["status"]
        == "rejected"
    )
    assert push(officer, inspection_change(waiting["id"], on="soon"))[0]["status"] == "rejected"
    assert push(officer, {"change_id": str(uuid.uuid4()), "op": "survey"})[0]["errors"] == [
        "op: must be create, update, task or inspection"
    ]

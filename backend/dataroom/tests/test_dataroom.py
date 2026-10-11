# ruff: noqa: E501 - long assertions read better on one line
"""Phase 16: the Public Data Room (Act 925 s.47; L.I. 2384 r.64, r.67-68).
What the public sees without signing in, and only once the district opens
its room and publishes a project."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from dataroom.models import InformationRequest
from relations.tests.test_relations import ROLE_OF, centre

pytestmark = pytest.mark.django_db

TODAY = date.today()
SETTINGS = "dataroom-settings"


@pytest.fixture
def anyone():
    return APIClient()  # no sign-in


def public(name, *args):
    return reverse(f"public-{name}", args=["DA", *args])


def receive(world, parcel, **extra):
    site = world.features("parcels", "parcel_id")[parcel]
    body = {
        "project": world.project,
        "kind": "development",
        "category": "building",
        "applicant_name": "Ama Mensah",
        "applicant_phone": "0240000000",
        "proposed_use": "Residential",
        "proposed_floors": 1,
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


def to_committee(world, parcel, recommendation="grant"):
    app = receive(world, parcel)
    step(world.client, "acknowledge", app)
    step(world.client, "inspect", app, {"summary": "Seen."})
    return step(world.client, "report", app, {"recommendation": recommendation})


def test_nothing_is_public_until_the_room_is_opened(
    world, admin, anyone, api, members_a, district_a
):
    receive(world, "P-001")
    for path in (
        public("room"),
        public("register"),
        public("zone") + "?lon=0&lat=5",
        public("status") + "?number=x",
    ):
        assert anyone.get(path).status_code == 404, path
    assert (
        anyone.post(
            public("requests"),
            {"name": "K", "phone": "1", "subject": "s", "body": "b"},
            format="json",
        ).status_code
        == 404
    )
    assert anyone.get(reverse("public-rooms")).json() == []
    assert anyone.get(reverse(SETTINGS)).status_code == 401

    # Only the district administrator opens it.
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(reverse(SETTINGS)).json()["is_open"] is False
    assert (
        world.client.patch(reverse(SETTINGS), {"is_open": True}, format="json").status_code == 403
    )
    opened = admin.patch(
        reverse(SETTINGS),
        {"is_open": True, "welcome": "Welcome.", "contact": "Room 4, 8am to 5pm"},
        format="json",
    )
    assert opened.status_code == 200 and opened.json()["code"] == "DA"
    assert anyone.get(reverse("public-rooms")).json() == [{"code": "DA", "assembly": "District A"}]
    room = anyone.get(public("room")).json()
    assert (room["assembly"], room["welcome"], room["contact"], room["answer_within_days"]) == (
        "District A",
        "Welcome.",
        "Room 4, 8am to 5pm",
        5,
    )
    # Open, but no project published: the register is empty.
    assert anyone.get(public("register")).json() == {"results": []}
    assert (
        anyone.get(reverse("public-room", args=["da"])).status_code == 200
    )  # the code in any case
    assert anyone.get(reverse("public-room", args=["ZZ"])).status_code == 404
    assert AuditLog.objects.filter(table_name="dataroom_dataroom", action="UPDATE").count() == 1


def test_the_register_of_permits(world, admin, anyone):
    """Gate: the register shows what r.67(3) lists, and no personal data."""
    issued = to_committee(world, "P-001")
    step(admin, "decide", issued, {"decision": "grant"})
    step(world.client, "fees", issued, {"stage": "permit", "amount": "850", "receipt": "R1"})
    issued = step(admin, "issue", issued)
    refused = to_committee(world, "P-002", "refuse")
    step(admin, "decide", refused, {"decision": "refuse", "reasons": "In the road reservation."})
    pending = receive(world, "P-003")
    gone = receive(world, "P-004")
    step(world.client, "withdraw", gone)

    admin.patch(reverse(SETTINGS), {"is_open": True}, format="json")
    publications = reverse("dataroom-publication-list")
    assert (
        world.client.post(publications, {"project": world.project}, format="json").status_code
        == 403
    )
    published = admin.post(publications, {"project": world.project}, format="json")
    assert published.status_code == 201 and published.json()["permits"] is True
    assert (
        admin.post(publications, {"project": world.project}, format="json").status_code == 400
    )  # once

    rows = {r["number"]: r for r in anyone.get(public("register")).json()["results"]}
    assert set(rows) == {
        issued["number"],
        refused["number"],
        pending["number"],
    }  # not the withdrawn one
    row = rows[issued["number"]]
    assert (row["status"], row["permit"], row["for"], row["locality"]) == (
        "Permit issued",
        "Development permit",
        "Erection of a building or structure",
        "Relations plan",
    )
    assert row["issued_on"] == str(TODAY) and row["expired"] is False and row["reasons"] == ""
    assert (
        rows[refused["number"]]["status"] == "Refused"
        and rows[refused["number"]]["reasons"] == "In the road reservation."
    )
    assert rows[pending["number"]]["status"] == "Pending"
    # r.68(2)(b): no names unless the district chooses, and never contact details.
    assert all(r["applicant"] is None for r in rows.values())
    assert "0240000000" not in str(rows) and "phone" not in str(rows)
    admin.patch(reverse(SETTINGS), {"show_applicants": True}, format="json")
    assert anyone.get(public("register")).json()["results"][0]["applicant"] == "Ama Mensah"

    assert [
        r["number"] for r in anyone.get(public("register"), {"status": "issued"}).json()["results"]
    ] == [issued["number"]]
    assert [
        r["number"]
        for r in anyone.get(public("register"), {"q": pending["number"][-4:]}).json()["results"]
    ] == [pending["number"]]

    # An applicant checks an application by its number, published or not.
    status = anyone.get(public("status"), {"number": pending["number"].lower()}).json()
    assert (
        status["status"] == "Pending"
        and status["next_step"]["label"] == "Acknowledge receipt in writing"
    )
    assert (
        status["next_step"]["due_on"] == str(TODAY + timedelta(days=7))
        and "applicant" not in status
    )
    assert anyone.get(public("status"), {"number": "DA/DP/1999/0001"}).status_code == 404
    assert anyone.get(public("status")).status_code == 404

    # Taken off the register again.
    admin.patch(
        reverse("dataroom-publication-detail", args=[published.json()["id"]]),
        {"permits": False},
        format="json",
    )
    assert anyone.get(public("register")).json() == {"results": []}


def test_what_can_i_build_here(world, admin, anyone):
    """Gate: a place's zone, its uses and the Assembly's standard for it."""
    planner = world.client
    parcels = world.features("parcels", "parcel_id")

    def lonlat(xy):
        moved = planner.post(
            reverse("crs-transform"),
            {
                "geometry": {"type": "Point", "coordinates": xy},
                "from_crs": "EPSG:2136",
                "to_crs": "EPSG:4326",
            },
            format="json",
        )
        assert moved.status_code == 200, moved.content
        lon, lat = moved.json()["geometry"]["coordinates"][:2]
        return {"lon": lon, "lat": lat}

    here = lonlat(centre(parcels["P-001"]))
    x, y = centre(parcels["P-001"])
    nowhere = lonlat([x + 50000, y])
    world.set_roles()
    admin.patch(reverse(SETTINGS), {"is_open": True}, format="json")
    assert anyone.get(public("zone"), here).json()["found"] is False  # nothing published yet
    publication = admin.post(
        reverse("dataroom-publication-list"), {"project": world.project}, format="json"
    ).json()

    # From the parcel's land use: the district's own word for the zone.
    plain = anyone.get(public("zone"), here).json()
    assert (plain["found"], plain["zone"], plain["from"], plain["code"], plain["standard"]) == (
        True,
        "residential",
        "the parcel's land use",
        None,
        None,
    )

    # With a zoning layer in the national codes, and the standards adopted.
    corners = [p for f in parcels.values() for p in f["geometry"]["coordinates"][0]]
    if isinstance(corners[0][0], list):
        corners = [p for ring in corners for p in ring]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    box = [
        [min(xs), min(ys)],
        [max(xs), min(ys)],
        [max(xs), max(ys)],
        [min(xs), max(ys)],
        [min(xs), min(ys)],
    ]
    world.add_layer("zoning", "polygon", [{"name": "zone", "type": "text"}], domain="J")
    world.add("zoning", {"type": "Polygon", "coordinates": [box]}, zone="ReB")
    world.set_roles({**ROLE_OF, "zoning": "zoning"})
    admin.post(reverse("standard-adopt-national"), {}, format="json")
    zone = anyone.get(public("zone"), here).json()
    assert (zone["zone"], zone["code"], zone["from"], zone["colour"]) == (
        "ReB",
        "Re B",
        "the zoning scheme",
        "#E5AA70",
    )
    assert (
        zone["name"] == "Residential Zone B: medium density"
        and zone["locality"] == "Relations plan"
    )
    assert "Local shop" in zone["permitted"] and "Gas filling stations" in zone["prohibited"]
    assert (
        zone["standard"]["front_setback_m"],
        zone["standard"]["max_floors"],
        zone["standard"]["min_plot_m2"],
    ) == (6, 3, 647)
    assert "permit" in zone["note"]

    assert anyone.get(public("zone"), nowhere).json()["found"] is False
    assert anyone.get(public("zone"), {"lon": "east", "lat": 5}).status_code == 400
    assert anyone.get(public("zone"), {"lon": 200, "lat": 5}).status_code == 400
    # Zoning taken out of the public room.
    admin.patch(
        reverse("dataroom-publication-detail", args=[publication["id"]]),
        {"zoning": False},
        format="json",
    )
    assert anyone.get(public("zone"), here).json()["found"] is False


def test_documents_on_display(world, admin, anyone, api, members_a, district_a):
    admin.patch(reverse(SETTINGS), {"is_open": True}, format="json")
    documents = reverse("dataroom-document-list")

    def put_up(client, title, **extra):
        upload = SimpleUploadedFile(
            f"{title}.pdf", f"%PDF {title}".encode(), content_type="application/pdf"
        )
        return client.post(
            documents,
            {"file": upload, "kind": "notice", "title": title, **extra},
            format="multipart",
        )

    assert (
        put_up(world.client, "Draft local plan").status_code == 403
    )  # the administrator's to publish
    shown = put_up(admin, "Draft local plan", display_until=str(TODAY + timedelta(days=60)))
    assert shown.status_code == 201, shown.content
    put_up(
        admin,
        "Last year's notice",
        display_from=str(TODAY - timedelta(days=400)),
        display_until=str(TODAY - timedelta(days=1)),
    )
    put_up(admin, "Next month's notice", display_from=str(TODAY + timedelta(days=20)))
    assert (
        put_up(
            admin,
            "Backwards",
            display_from=str(TODAY),
            display_until=str(TODAY - timedelta(days=2)),
        ).status_code
        == 400
    )

    # Staff see all three; the public only what is on display today.
    viewer = api(members_a[Role.VIEWER], district_a)
    assert len(viewer.get(documents).json()) == 3
    on_display = anyone.get(public("room")).json()["documents"]
    assert [(d["title"], d["kind_label"], d["display_until"]) for d in on_display] == [
        ("Draft local plan", "Notice", str(TODAY + timedelta(days=60)))
    ]
    got = anyone.get(public("document", shown.json()["id"]))
    assert got.status_code == 200 and b"".join(got.streaming_content) == b"%PDF Draft local plan"
    past = next(d for d in viewer.get(documents).json() if d["title"] == "Last year's notice")
    assert anyone.get(public("document", past["id"])).status_code == 404
    assert (
        viewer.delete(reverse("dataroom-document-detail", args=[shown.json()["id"]])).status_code
        == 403
    )
    assert (
        admin.delete(reverse("dataroom-document-detail", args=[shown.json()["id"]])).status_code
        == 204
    )
    assert anyone.get(public("room")).json()["documents"] == []


def test_requests_for_information_are_answered_within_five_days(
    world, admin, anyone, api, members_a, district_a, district_b, make_member
):
    admin.patch(reverse(SETTINGS), {"is_open": True}, format="json")
    ask = {
        "name": "Kojo Antwi",
        "subject": "Zoning of plot 14",
        "body": "What is plot 14 zoned for?",
    }
    assert (
        anyone.post(public("requests"), ask, format="json").status_code == 400
    )  # no way to answer
    made = anyone.post(public("requests"), {**ask, "phone": "0200000000"}, format="json")
    assert made.status_code == 201, made.content
    # r.64(7): five days.
    assert made.json() == {
        "reference": f"DA/IR/{TODAY.year}/0001",
        "received_on": str(TODAY),
        "answer_due_on": str(TODAY + timedelta(days=5)),
    }
    second = anyone.post(
        public("requests"), {**ask, "email": "kojo@example.test"}, format="json"
    ).json()
    assert second["reference"].endswith("/0002")

    requests = reverse("dataroom-request-list")
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(requests).status_code == 403  # they hold people's contact details
    listed = world.client.get(requests).json()
    assert (listed["open"], listed["overdue"], listed["answer_within_days"]) == (2, 0, 5)
    first = next(r for r in listed["results"] if r["reference"].endswith("/0001"))
    assert first["phone"] == "0200000000" and first["overdue"] is False

    # Ten days on, unanswered: overdue. Answered then: done, but late. r.64(8): kept on record.
    InformationRequest.objects.filter(pk=first["id"]).update(received_on=TODAY - timedelta(days=10))
    assert world.client.get(requests).json()["overdue"] == 1
    answer = reverse("dataroom-request-answer", args=[first["id"]])
    done = world.client.post(
        answer, {"answer": "Re B, medium-density residential."}, format="json"
    ).json()
    assert (done["status"], done["answered_on"], done["late"], done["overdue"]) == (
        "answered",
        str(TODAY),
        True,
        False,
    )
    assert world.client.post(answer, {"answer": "Again."}, format="json").status_code == 400
    declined = world.client.post(
        reverse("dataroom-request-answer", args=[listed["results"][0]["id"]]),
        {"answer": "Held by the Lands Commission.", "declined": True},
        format="json",
    ).json()
    assert declined["status"] == "declined" and declined["late"] is False
    log = AuditLog.objects.filter(table_name="dataroom_informationrequest")
    # Two asked, two answered by staff (r.64(8): kept on record).
    assert log.filter(action="INSERT").count() == 2
    assert log.filter(action="UPDATE", user_id__isnull=False).count() == 2

    # Another district: its room is closed, and its staff see none of this.
    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert (
        other.get(requests).json()["results"] == []
        and other.post(answer, {"answer": "x"}, format="json").status_code == 404
    )
    assert anyone.get(reverse("public-room", args=["DB"])).status_code == 404
    theirs = other.get(reverse(SETTINGS)).json()
    assert (theirs["code"], theirs["is_open"]) == ("DB", False)
    with tenant_context(district_b.id):
        assert InformationRequest.objects.count() == 0

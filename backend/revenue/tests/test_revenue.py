# ruff: noqa: E501 - long assertions read better on one line
"""Phase 21: the property register, rates and the revenue link, and
betterment (L.I. 2384 r.40-41). The fixture community: buildings B-001 to
B-006 stand about 13 m from the centreline of Main Street."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog, Role

pytestmark = pytest.mark.django_db

TODAY = date.today()
YEAR = TODAY.year


def days(n):
    return str(TODAY + timedelta(days=n))


def csv_file(name, text):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def register(client, world, what, **body):
    return client.post(reverse("register-action", args=[world.project, what]), body, format="json")


def upload(client, world, what, name, text):
    return client.post(
        reverse("register-action", args=[world.project, what]),
        {"file": csv_file(name, text)},
        format="multipart",
    )


def properties(client, world, **params):
    response = client.get(reverse("revenue-property-list"), {"project": world.project, **params})
    assert response.status_code == 200, response.content
    return {p["number"]: p for p in response.json()["results"]}


@pytest.fixture
def ready(world, admin):
    """A register for the fixture, every property residential but B-006 (industrial), and this year's residential rate."""
    world.set_roles()
    built = register(world.client, world, "build")
    assert built.status_code == 200, built.content
    assert built.json() == {"added": 6, "already": 0, "total": 6}
    for number, prop in properties(world.client, world).items():
        use = "industrial" if number == "B-006" else "residential"
        world.client.patch(
            reverse("revenue-property-detail", args=[prop["id"]]), {"use": use}, format="json"
        )
    band = world.client.post(
        reverse("revenue-rate-list"),
        {
            "year": YEAR,
            "use": "residential",
            "impost": "0.005",
            "minimum": "50.00",
            "flat": "100.00",
        },
        format="json",
    )
    assert band.status_code == 201, band.content
    return world


def test_the_register_is_built_from_the_map_once(world):
    assert (
        register(world.client, world, "build").status_code == 400
    )  # which layer holds the properties?
    world.set_roles()
    assert register(world.client, world, "build").json() == {"added": 6, "already": 0, "total": 6}
    assert register(world.client, world, "build").json() == {"added": 0, "already": 6, "total": 6}
    assert sorted(properties(world.client, world)) == [
        "B-001",
        "B-002",
        "B-003",
        "B-004",
        "B-005",
        "B-006",
    ]


def test_rates_bills_and_the_revenue_system(
    ready, api, members_a, district_a, district_b, make_member
):
    """Gate: every bill in the sample matches one property; never billed is exactly what has no bill."""
    world, planner = ready, ready.client
    url = reverse("revenue-rate-list")
    assert (
        planner.post(
            url, {"year": YEAR, "use": "residential", "impost": "0.004"}, format="json"
        ).status_code
        == 400
    )  # already set
    assert (
        planner.post(
            url, {"year": YEAR, "use": "commercial", "impost": "5"}, format="json"
        ).status_code
        == 400
    )  # a share, not a percent
    viewer = api(members_a[Role.VIEWER], district_a)
    assert (
        viewer.post(
            url, {"year": YEAR, "use": "commercial", "impost": "0.01"}, format="json"
        ).status_code
        == 403
    )

    # The valuation list: two properties valued, one row that matches nothing.
    valued = upload(
        planner,
        world,
        "valuations",
        "valuations.csv",
        'number,valuation_ref,rateable_value,valued_on,owner\nB-001,LVD/0001,"200,000.00",2026-01-15,Kwame Addo\nB-002,LVD/0002,5000,,\nX-999,LVD/9999,1000,,\n',
    )
    assert valued.status_code == 200, valued.content
    assert (valued.json()["matched"], valued.json()["unmatched"]) == (
        2,
        [{"row": 4, "reference": "LVD/9999"}],
    )
    assert (
        upload(
            planner, world, "valuations", "bad.csv", "number,rateable_value\nB-003,lots\n"
        ).status_code
        == 400
    )

    # Bills for the year: the rate on the value, the minimum, the flat rate for the unvalued; none for a use with no rate.
    billed = register(planner, world, "bills", year=YEAR).json()
    assert (billed["billed"], billed["total"], billed["skipped_count"]) == (5, "1350.00", 1)
    assert billed["skipped"] == [
        {"number": "B-006", "reason": f"No {YEAR} rate is set for industrial property."}
    ]
    props = properties(planner, world)
    assert [(b["amount"], b["reference"]) for b in props["B-001"]["bills"]] == [
        ("1000.00", f"DA/PR/{YEAR}/00001")
    ]
    assert (
        props["B-002"]["bills"][0]["amount"] == "50.00"
        and props["B-003"]["bills"][0]["amount"] == "100.00"
    )
    assert register(planner, world, "bills", year=YEAR).json()["billed"] == 0  # once a year

    # Bills and payments from the revenue system: each row matches one property, or is reported.
    synced = upload(
        planner,
        world,
        "revenue",
        "dlrev.csv",
        f"property,revenue_ref,year,bill,amount,paid,paid_on\nB-001,ACC-1,{YEAR},R-77,1000,1000,{days(-2)}\nB-003,ACC-3,{YEAR},R-78,,40,\nZ-1,ACC-9,{YEAR},R-79,10,10,\n",
    )
    assert synced.status_code == 200, synced.content
    assert (synced.json()["rows"], synced.json()["matched"], synced.json()["unmatched"]) == (
        3,
        2,
        [{"row": 4, "reference": "ACC-9"}],
    )
    props = properties(planner, world)
    assert (
        props["B-001"]["revenue_ref"],
        props["B-001"]["bills"][0]["paid"],
        props["B-001"]["bills"][0]["source"],
        props["B-001"]["bills"][0]["reference"],
    ) == ("ACC-1", "1000.00", "revenue", "R-77")
    assert props["B-003"]["bills"][0]["owing"] == "60.00"

    # What the map and the lists show: never billed, owing, paid up.
    assert sorted(properties(planner, world, status="never_billed")) == ["B-006"]
    assert sorted(properties(planner, world, status="paid")) == ["B-001"]
    assert sorted(properties(planner, world, status="unpaid")) == [
        "B-002",
        "B-003",
        "B-004",
        "B-005",
    ]
    summary = planner.get(reverse("register", args=[world.project])).json()
    assert summary == {
        "properties": 6,
        "valued": 2,
        "by_status": {"never_billed": 1, "unpaid": 4, "paid": 1},
        "billed": "1350.00",
        "paid": "1040.00",
        "owing": "310.00",
        "collected_pct": 77.0,
    }

    # A payment at the office settles B-003.
    paid = planner.post(
        reverse("revenue-property-payment", args=[props["B-003"]["id"]]),
        {"year": YEAR, "amount": "60.00"},
        format="json",
    )
    assert paid.json()["status"] == "paid" and paid.json()["bills"][0]["last_paid_on"] == str(TODAY)
    assert (
        planner.post(
            reverse("revenue-property-payment", args=[props["B-003"]["id"]]),
            {"year": YEAR - 5, "amount": "1"},
            format="json",
        ).status_code
        == 400
    )

    # The rates map layer: a point per property, coloured by status; again, nothing changes.
    mapped = register(planner, world, "map").json()
    assert (mapped["written"], mapped["removed"]) == (6, 0)
    points = world.client.get(reverse("layer-features", args=[mapped["layer"]])).json()["features"]
    assert sorted((f["properties"]["property_no"], f["properties"]["status"]) for f in points) == [
        ("B-001", "Paid up"),
        ("B-002", "Owing"),
        ("B-003", "Paid up"),
        ("B-004", "Owing"),
        ("B-005", "Owing"),
        ("B-006", "Never billed"),
    ]
    assert register(planner, world, "map").json()["written"] == 0

    # Owners are personal data; the register exports for the revenue system.
    assert properties(planner, world)["B-001"]["owner_name"] == "Kwame Addo"
    assert properties(viewer, world)["B-001"]["owner_name"] == "restricted"
    exported = viewer.get(reverse("register-csv", args=[world.project]))
    lines = exported.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("number,address,use,owner,") and len(lines) == 7
    assert "Kwame" not in exported.content.decode("utf-8-sig")
    assert (
        viewer.post(
            reverse("register-action", args=[world.project, "bills"]), {"year": YEAR}, format="json"
        ).status_code
        == 403
    )
    assert AuditLog.objects.filter(table_name="revenue_bill", action="UPDATE").exists()

    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert (
        other.get(reverse("revenue-property-detail", args=[props["B-001"]["id"]])).status_code
        == 404
    )
    assert other.get(reverse("revenue-rate-list")).json() == []


def test_betterment_from_the_works_to_the_certificate(ready):
    world, planner = ready, ready.client
    main_street = world.features("streets", "name")["Main Street"]["id"]
    url = reverse("revenue-betterment-list")
    made = planner.post(
        url,
        {
            "project": world.project,
            "name": "Main Street paving",
            "works": "Asphalt and side drains",
            "works_feature": main_street,
            "reach_m": "10",
            "completed_on": days(-100),
            "basis": "sum",
            "amount": "500",
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    scheme = made.json()
    assert (scheme["clocks"]["serve_by"], scheme["clocks"]["rule"]) == (days(-10), "r.40(7)")
    find = reverse("revenue-betterment-find", args=[scheme["id"]])
    # The buildings stand about 13 m from the centreline: none within 10 m, all six within 20 m.
    assert planner.post(find, {}, format="json").json()["found"] == {"found": 0, "added": 0}
    planner.patch(
        reverse("revenue-betterment-detail", args=[scheme["id"]]), {"reach_m": "20"}, format="json"
    )
    found = planner.post(find, {}, format="json").json()
    assert found["found"] == {"found": 6, "added": 6}
    assert (
        found["charges_count"],
        found["total"],
        found["clocks"]["unserved"],
        found["clocks"]["overdue"],
    ) == (6, "3000.00", 6, True)
    assert all(13 <= float(c["distance_m"]) <= 14 for c in found["charges"])
    assert planner.post(find, {}, format="json").json()["found"] == {"found": 6, "added": 0}

    # r.40(3): the notice published; r.40(7): an assessment served (late: after the 90 days).
    published = planner.post(
        reverse("revenue-betterment-publish", args=[scheme["id"]]),
        {"how": "newspaper", "on": days(-50)},
        format="json",
    ).json()
    assert [p["on"] for p in published["clocks"]["published"]] == [days(-50), None, None]
    assert (
        planner.post(
            reverse("revenue-betterment-publish", args=[scheme["id"]]),
            {"how": "radio"},
            format="json",
        ).status_code
        == 400
    )
    first = found["charges"][0]
    charge_url = reverse("revenue-charge-detail", args=[first["id"]])
    served = planner.patch(charge_url, {"served_on": days(-5)}, format="json").json()
    assert served["served_on"] == days(-5)
    after = planner.get(reverse("revenue-betterment-detail", args=[scheme["id"]])).json()["clocks"]
    assert (after["unserved"], after["served_late"]) == (5, 1)
    assert planner.patch(charge_url, {"served_on": days(3)}, format="json").status_code == 400

    # Charged on the increase in value instead: nothing is due until the increase is assessed.
    planner.patch(
        reverse("revenue-betterment-detail", args=[scheme["id"]]),
        {"basis": "rate", "amount": "0.25"},
        format="json",
    )
    assert (
        planner.get(
            reverse("revenue-charge-paper", args=[first["id"]]), {"kind": "assessment"}
        ).status_code
        == 400
    )
    assessed = planner.patch(charge_url, {"increase": "4000"}, format="json").json()
    assert assessed["amount"] == "1000.00"
    assert (
        planner.patch(
            reverse("revenue-betterment-detail", args=[scheme["id"]]),
            {"amount": "2"},
            format="json",
        ).status_code
        == 400
    )

    # The papers: the notice, the assessment, the certificate of what is due, then of payment.
    for response in (
        planner.get(reverse("revenue-betterment-notice", args=[scheme["id"]])),
        planner.get(
            reverse("revenue-charge-paper", args=[first["id"]]),
            {"kind": "assessment", "payment": "at the Assembly's cash office within 30 days."},
        ),
        planner.get(reverse("revenue-charge-paper", args=[first["id"]]), {"kind": "certificate"}),
    ):
        assert response.status_code == 200 and response.content.startswith(b"%PDF")
    settled = planner.patch(charge_url, {"paid": "1000", "paid_on": days(-1)}, format="json").json()
    assert settled["paid"] == "1000.00"
    assert planner.get(
        reverse("revenue-charge-paper", args=[first["id"]]), {"kind": "certificate"}
    ).content.startswith(b"%PDF")
    assert (
        planner.get(
            reverse("revenue-charge-paper", args=[first["id"]]), {"kind": "receipt"}
        ).status_code
        == 400
    )
    listed = planner.get(url, {"project": world.project}).json()["results"]
    assert [(s["name"], s["charges_count"], s["collected"]) for s in listed] == [
        ("Main Street paving", 6, "1000.00")
    ]

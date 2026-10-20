# ruff: noqa: E501 - long assertions read better on one line
"""Phase 22: the district's periodic return, and the exchange API that lets
national bodies read its records with a key it issues and can revoke."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from dataroom.models import InformationRequest
from enforcement.models import Case, Notice
from landchange.models import Application as LandApplication
from permits.models import Application
from planmaking.models import PlanProcess
from projects.models import PlanProject
from revenue.models import Bill, Property

pytestmark = pytest.mark.django_db

TODAY = date.today()
# A whole past quarter, so every date below falls inside it.
Q_START = date(TODAY.year - 1, 4, 1)
Q_LABEL = f"{TODAY.year - 1}-Q2"


def on(n: int) -> date:
    return Q_START + timedelta(days=n)


@pytest.fixture
def records(world, district_a):
    """A quarter's work, made straight in the database."""
    with tenant_context(district_a.id):
        project = PlanProject.objects.get(pk=world.project)
        site = world.features("parcels", "parcel_id")["P-001"]["id"]

        def permit(n, status, decided, **extra):
            return Application.objects.create(
                district_id=district_a.id,
                project=project,
                number=f"DA/DP/2025/{n:04d}",
                kind="development",
                category="building",
                applicant_name="Ama Mensah",
                applicant_phone="0240000000",
                proposed_use="Residential",
                proposed_floors=2,
                received_on=on(1),
                decided_on=decided,
                status=status,
                **extra,
            )

        permit(1, Application.Status.ISSUED, on(20), issued_on=on(25), site_id=site)
        permit(2, Application.Status.REFUSED, on(45))
        permit(3, Application.Status.RECEIVED, None)
        LandApplication.objects.create(
            district_id=district_a.id,
            project=project,
            number="DA/RZ/2025/0001",
            kind="rezoning",
            applicant_name="K",
            received_on=on(2),
            decided_on=on(70),
            status=LandApplication.Status.APPROVED,
        )
        case = Case.objects.create(
            district_id=district_a.id,
            project=project,
            number="DA/EN/2025/0001",
            origin="inspection",
            contravention="no_permit",
            opened_on=on(5),
            owner_name="Kwesi Appiah",
            feature_id=site,
        )
        Notice.objects.create(
            district_id=district_a.id,
            case=case,
            kind="stop",
            grounds="Wall",
            issued_on=on(5),
            served_on=on(6),
        )
        Notice.objects.create(
            district_id=district_a.id,
            case=case,
            kind="rectification",
            grounds="Wall",
            issued_on=on(6),
        )  # not served
        PlanProcess.objects.create(
            district_id=district_a.id,
            project=project,
            steps={
                "commence": {"on": on(3).isoformat(), "note": ""},
                "approve": {"on": on(80).isoformat(), "note": ""},
            },
        )
        InformationRequest.objects.create(
            district_id=district_a.id,
            reference="DA/IR/2025/0001",
            name="Akua",
            subject="Zoning",
            body="?",
            received_on=on(10),
            answered_on=on(12),
            status="answered",
        )
        prop = Property.objects.create(district_id=district_a.id, project=project, number="B-001")
        Bill.objects.create(
            district_id=district_a.id,
            property=prop,
            year=2025,
            amount="1000.00",
            paid="250.00",
            issued_on=on(15),
            last_paid_on=on(30),
        )
    return world


def test_the_quarterly_return(records, api, members_a, district_a):
    url = reverse("reports-return")
    viewer = api(members_a[Role.VIEWER], district_a)
    data = viewer.get(url, {"period": Q_LABEL}).json()
    assert data["period"] == {
        "label": f"Quarter 2 of {TODAY.year - 1}",
        "from": f"{TODAY.year - 1}-04-01",
        "to": f"{TODAY.year - 1}-06-30",
    }
    p = data["permits"]
    assert (p["received"], p["decided"], p["granted"], p["refused"], p["issued"]) == (3, 2, 1, 1, 1)
    # Decided 19 and 44 days after receipt: one within the 30 days.
    assert (p["decided_within_limit_pct"], p["average_days_to_decision"]) == (50.0, 31.5)
    assert p["received_by_category"] == [
        {"category": "Erection of a building or structure", "count": 3}
    ]
    assert data["land"][0] == {"kind": "Re-zoning", "received": 1, "approved": 1, "refused": 0}
    e = data["enforcement"]
    assert (e["cases_opened"], e["notices_served"], e["notices_by_kind"]) == (
        1,
        1,
        [{"notice": "Stop Notice or Order for Discontinuance", "form": "48A", "count": 1}],
    )
    assert data["plans"]["commenced"] == ["Relations plan"] and data["plans"]["approved"] == [
        "Relations plan"
    ]
    assert data["data_room"] == {
        "requests_received": 1,
        "answered": 1,
        "answered_within_limit_pct": 100.0,
    }
    assert (data["revenue"]["bills_issued"], data["revenue"]["billed"]) == (1, "1000.00")
    # No names anywhere.
    assert "Ama" not in str(data) and "Kwesi" not in str(data)

    # The next quarter is empty; a year holds it all; a period can be given by dates.
    assert viewer.get(url, {"period": f"{TODAY.year - 1}-Q3"}).json()["permits"]["received"] == 0
    assert viewer.get(url, {"period": str(TODAY.year - 1)}).json()["permits"]["received"] == 3
    assert (
        viewer.get(url, {"from": on(0).isoformat(), "to": on(10).isoformat()}).json()["permits"][
            "decided"
        ]
        == 0
    )
    for bad in (
        {"period": "2025-Q5"},
        {"period": "soon"},
        {"from": "2025-05-01", "to": "2025-04-01"},
    ):
        assert viewer.get(url, bad).status_code == 400

    # To file: a CSV and a PDF.
    lines = (
        viewer.get(url, {"period": Q_LABEL, "type": "csv"}).content.decode("utf-8-sig").splitlines()
    )
    assert lines[0] == "section,measure,value" and "Permits,Applications received,3" in lines
    printed = viewer.get(url, {"period": Q_LABEL, "type": "pdf"})
    assert printed.status_code == 200 and printed.content.startswith(b"%PDF")


def test_a_national_body_reads_with_a_key(
    records, admin, api, members_a, district_a, district_b, make_member
):
    keys = reverse("exchange-key-list")
    planner = api(members_a[Role.PLANNER], district_a)
    assert (
        planner.post(keys, {"name": "LUSPA", "scopes": ["permits"]}, format="json").status_code
        == 403
    )
    assert (
        admin.post(keys, {"name": "LUSPA", "scopes": ["parcels"]}, format="json").status_code == 400
    )
    made = admin.post(
        keys,
        {"name": "LUSPA, Accra", "scopes": ["permits", "enforcement", "plans", "returns"]},
        format="json",
    )
    assert made.status_code == 201, made.content
    key = made.json()["key"]
    assert key.startswith("DA.") and made.json()["scopes"] == [
        "enforcement",
        "permits",
        "plans",
        "returns",
    ]
    # Shown once: the list never repeats it.
    listed = admin.get(keys).json()
    assert "key" not in listed["keys"][0] and listed["keys"][0]["prefix"] == key[3:15]
    assert set(listed["scopes"]) == {"permits", "plans", "zoning", "enforcement", "returns"}

    outsider = APIClient()

    def read(dataset, secret=key, **params):
        return outsider.get(
            reverse("exchange-data", args=[dataset]), params, HTTP_AUTHORIZATION=f"Key {secret}"
        )

    permits = read("permits")
    assert permits.status_code == 200, permits.content
    body = permits.json()
    assert (body["type"], body["district"], body["count"]) == (
        "FeatureCollection",
        {"code": "DA", "name": "District A"},
        2,
    )
    first = body["features"][0]
    assert (
        first["properties"]["number"] == "DA/DP/2025/0001"
        and first["properties"]["status"] == "Permit issued"
    )
    assert first["geometry"]["type"] in ("Polygon", "MultiPolygon")  # WGS 84
    assert body["features"][1]["geometry"] is None
    assert "Ama" not in str(body) and "0240000000" not in str(body)
    assert read("permits", since=on(30).isoformat()).json()["count"] == 1
    notices = read("enforcement").json()
    assert [f["properties"]["notice"] for f in notices["features"]] == [
        "Stop Notice or Order for Discontinuance"
    ]
    assert "Kwesi" not in str(notices)
    assert read("plans").json()["features"][0]["properties"]["approved_on"] == on(80).isoformat()
    assert read("returns", period=Q_LABEL).json()["permits"]["received"] == 3

    # What the key may not do, and keys that don't work.
    assert read("zoning").status_code == 403
    assert read("parcels").status_code == 404
    assert read("permits", secret="DA.not-the-key-at-all").status_code == 401
    assert read("permits", secret="DB." + key[3:]).status_code == 401  # another district's code
    assert outsider.get(reverse("exchange-data", args=["permits"])).status_code == 401
    make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test")

    # Each read is counted, and recorded in the audit log; revoked, the key stops working.
    with tenant_context(district_a.id):
        assert (
            AuditLog.objects.filter(table_name="exchange_exchangekey", action="UPDATE").count() >= 5
        )
        made_entry = AuditLog.objects.filter(table_name="exchange_exchangekey").first()
        assert made_entry is not None and "digest" not in str(made_entry.after)
    assert (
        admin.get(keys).json()["keys"][0]["uses"] == 5
    )  # the five reads allowed; refusals are not reads
    revoked = admin.post(
        reverse("exchange-key-revoke", args=[made.json()["id"]]), {}, format="json"
    )
    assert revoked.json()["revoked_at"] is not None
    assert read("permits").status_code == 401

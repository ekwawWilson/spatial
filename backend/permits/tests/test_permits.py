# ruff: noqa: E501 - long assertions read better on one line
"""Phase 15: planning and development permits (L.I. 2384 r.43-46), from the
day an application is received to the certificate, with the Regulations'
deadlines. Sites are the fixture community's parcels (30 x 30 m, 900 m2, 10 m
from Main Street; P-006 lies in the flood-prone area)."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from permits.models import Application
from projects.models import Feature
from relations.models import LayerRole

pytestmark = pytest.mark.django_db

TODAY = date.today()
LIST = "permit-application-list"


def url(name, application, **kwargs):
    return reverse(f"permit-application-{name}", args=[application["id"]], **kwargs)


def receive(client, world, parcel="P-001", **extra):
    site = world.features("parcels", "parcel_id")[parcel]
    body = {
        "project": world.project,
        "kind": "development",
        "category": "building",
        "applicant_name": "Ama Mensah",
        "applicant_phone": "0240000000",
        "proposed_use": "Residential",
        "proposed_floors": 2,
        "site_feature": site["id"],
        **extra,
    }
    if body["site_feature"] is None:
        del body["site_feature"]  # no site, or one given as a shape
    return client.post(reverse(LIST), body, format="json")


def result(application, code):
    return next(r for r in application["checks"]["results"] if r["code"] == code)


def test_what_the_regulations_fix(planner):
    data = planner.get(reverse("permits-registry")).json()
    assert [c["days"] for c in data["clocks"]] == [7, 14, 21, 30]
    assert [c["rule"] for c in data["clocks"]] == ["r.44(6)", "r.44(7)", "r.44(8)", "r.44(10)"]
    assert len(data["inspection_points"]) == 13 and len(data["categories"]) == 20
    assert {c["kind"] for c in data["categories"]} == {"planning", "development"}
    assert data["permit_valid_years"] == 5


def test_an_application_from_receipt_to_certificate(world, admin, api, members_a, district_a):
    """Gate: one application through every step, each with the right role."""
    world.set_roles()
    planner = world.client
    viewer = api(members_a[Role.VIEWER], district_a)
    officer = api(members_a[Role.FIELD_OFFICER], district_a)
    assert receive(viewer, world).status_code == 403 and receive(officer, world).status_code == 403

    created = receive(planner, world)
    assert created.status_code == 201, created.content
    app = created.json()
    # r.44(7)(b): it has its number; the site is on the map in the permits layer.
    assert app["number"] == f"DA/DP/{TODAY.year}/0001" and app["status"] == "received"
    role = LayerRole.objects.get(project_id=world.project, role="permits")
    site = Feature.objects.get(pk=app["site"])
    assert site.layer_id == role.layer_id and site.properties["application_no"] == app["number"]
    # Two storeys: structural drawings are required as well (r.45(9)(d)).
    assert [r["code"] for r in app["requirements"]] == [
        "land_right",
        "site_plan",
        "block_plan",
        "architectural",
        "structural",
    ]
    assert [c["due_on"] for c in app["clocks"]] == [
        str(TODAY + timedelta(days=n)) for n in (7, 14, 21, 30)
    ]
    assert app["next_due"]["code"] == "acknowledge" and app["next_due"]["overdue"] is False
    assert result(app, "plot_size")["measured_m2"] == pytest.approx(900, abs=5)

    # r.44(6): acknowledged; it goes to the Technical Sub-Committee.
    app = planner.post(url("acknowledge", app), {}, format="json").json()
    assert app["status"] == "review" and app["acknowledged_on"] == str(TODAY)
    paper = planner.get(url("acknowledgement", app))
    assert paper.status_code == 200 and paper.content.startswith(b"%PDF")

    # A submitted document counts against its requirement.
    upload = SimpleUploadedFile(
        "site-plan.pdf", b"%PDF-1.4 site plan", content_type="application/pdf"
    )
    app = planner.post(
        url("documents", app), {"file": upload, "requirement": "site_plan"}, format="multipart"
    ).json()
    assert {r["code"]: r["submitted"] for r in app["requirements"]}["site_plan"] == 1
    document = app["documents"][0]
    assert (
        b"".join(
            viewer.get(reverse("permit-document-download", args=[document["id"]])).streaming_content
        )
        == b"%PDF-1.4 site plan"
    )
    assert (
        viewer.delete(reverse("permit-document-detail", args=[document["id"]])).status_code == 403
    )

    # r.44(7)(d): circulated; Works comments.
    app = planner.post(
        url("comments", app),
        {"agency": "Works Department", "body": "Drain to be shown."},
        format="json",
    ).json()
    assert app["comments"][0]["agency"] == "Works Department"

    # r.44(8) needs r.44(7)(f) first. A field officer inspects.
    assert (
        planner.post(url("report", app), {"recommendation": "grant"}, format="json").status_code
        == 400
    )
    assert (
        officer.post(url("inspect", app), {"findings": {"moon": "full"}}, format="json").status_code
        == 400
    )
    app = officer.post(
        url("inspect", app),
        {"findings": {"plot_size": "30 x 30 m", "started": "No"}, "summary": "As submitted."},
        format="json",
    ).json()
    assert (
        app["inspected_on"] == str(TODAY) and app["inspections"][0]["findings"]["started"] == "No"
    )
    assert (
        officer.post(url("report", app), {"recommendation": "grant"}, format="json").status_code
        == 403
    )
    app = planner.post(
        url("report", app), {"recommendation": "grant", "report": "Conforms."}, format="json"
    ).json()
    assert app["status"] == "reported"

    # r.44(9): the committee's decision is the district administrator's to record.
    grant = {"decision": "grant", "conditions": "Plant two trees."}
    assert planner.post(url("decide", app), grant, format="json").status_code == 403
    app = admin.post(url("decide", app), grant, format="json").json()
    assert app["status"] == "granted" and app["conditions"] == "Plant two trees."
    assert planner.get(url("certificate", app)).status_code == 404  # not issued yet

    # r.44(11): the permit fee, then the certificate (r.44(10)), valid five years.
    assert admin.post(url("issue", app), {}, format="json").status_code == 400
    app = planner.post(
        url("fees", app),
        {"stage": "permit", "amount": "850.00", "receipt": "GCR 0012345"},
        format="json",
    ).json()
    assert app["permit_fee"] == "850.00" and app["permit_paid_on"] == str(TODAY)
    app = admin.post(url("issue", app), {}, format="json").json()
    assert app["status"] == "issued" and app["issued_on"] == str(TODAY) and app["expired"] is False
    assert date.fromisoformat(app["expires_on"]).year == TODAY.year + 5 and app["next_due"] is None
    assert [c["done_on"] for c in app["clocks"]] == [str(TODAY)] * 4 and not any(
        c["late"] for c in app["clocks"]
    )
    certificate = viewer.get(url("certificate", app))
    assert certificate.status_code == 200 and certificate.content.startswith(b"%PDF")
    assert [e["kind"] for e in app["events"]] == [
        "received",
        "acknowledged",
        "inspected",
        "reported",
        "granted",
        "permit_fee_paid",
        "issued",
    ]
    site.refresh_from_db()
    assert site.properties["status"] == "Permit issued"

    # Anyone holding the certificate can check it; nobody can guess one.
    token = app["verify_url"].rsplit("/", 1)[1]
    anyone = APIClient()
    checked = anyone.get(reverse("permit-verify", args=[token]))
    assert checked.status_code == 200, checked.content
    assert checked.json() == {
        "assembly": "District A",
        "number": app["number"],
        "permit": "Development permit",
        "for": "Erection of a building or structure",
        "applicant": "Ama Mensah",
        "locality": "Relations plan",
        "proposed_use": "Residential",
        "issued_on": str(TODAY),
        "expires_on": app["expires_on"],
        "valid": True,
    }
    assert anyone.get(reverse("permit-verify", args=["x" * 32])).status_code == 404
    assert anyone.get(reverse("permit-verify", args=["short"])).status_code == 404
    assert anyone.get(reverse(LIST)).status_code == 401

    # Audited, without the certificate's code.
    log = AuditLog.objects.filter(table_name="permits_application", row_id=str(app["id"]))
    assert log.filter(action="INSERT").count() == 1 and log.filter(action="UPDATE").count() >= 5
    assert token not in str(list(log.values_list("before", "after")))
    # Closed: it can't be edited or decided again.
    assert (
        planner.patch(url("detail", app), {"proposed_use": "Hotel"}, format="json").status_code
        == 400
    )
    assert (
        admin.post(
            url("decide", app), {"decision": "refuse", "reasons": "x"}, format="json"
        ).status_code
        == 400
    )


def test_the_deadlines_run_from_the_day_of_receipt(world):
    planner = world.client
    old = receive(planner, world, received_on=str(TODAY - timedelta(days=40))).json()
    assert [c["overdue"] for c in old["clocks"]] == [True, True, True, True]
    fresh = receive(planner, world, parcel="P-002").json()
    listed = planner.get(reverse(LIST), {"project": world.project}).json()
    assert listed["summary"] == {
        "total": 2,
        "open": 2,
        "overdue": 1,
        "by_status": {
            "received": 2,
            "review": 0,
            "reported": 0,
            "granted": 0,
            "deferred": 0,
            "refused": 0,
            "issued": 0,
            "withdrawn": 0,
        },
    }
    late = planner.get(reverse(LIST), {"overdue": "true"}).json()["results"]
    assert [a["number"] for a in late] == [old["number"]] and late[0]["next_due"][
        "code"
    ] == "acknowledge"
    assert [a["number"] for a in planner.get(reverse(LIST), {"q": "0002"}).json()["results"]] == [
        fresh["number"]
    ]

    # Acknowledged on day 10: done, but late. Dates can't run backwards or ahead.
    assert (
        planner.post(
            url("acknowledge", old), {"on": str(TODAY - timedelta(days=41))}, format="json"
        ).status_code
        == 400
    )
    assert (
        planner.post(
            url("acknowledge", old), {"on": str(TODAY + timedelta(days=1))}, format="json"
        ).status_code
        == 400
    )
    done = planner.post(
        url("acknowledge", old), {"on": str(TODAY - timedelta(days=30))}, format="json"
    ).json()
    first = done["clocks"][0]
    assert (
        first["done_on"] == str(TODAY - timedelta(days=30))
        and first["late"] is True
        and first["overdue"] is False
    )
    assert done["next_due"]["code"] == "inspect" and done["next_due"]["overdue"] is True
    assert receive(planner, world, received_on=str(TODAY + timedelta(days=2))).status_code == 400

    # Withdrawn: nothing is due any more.
    gone = planner.post(
        url("withdraw", fresh), {"note": "Applicant's request."}, format="json"
    ).json()
    assert (
        gone["status"] == "withdrawn"
        and gone["next_due"] is None
        and not any(c["overdue"] for c in gone["clocks"])
    )


def test_refusals_and_deferrals_carry_their_reasons(world, admin):
    planner = world.client

    def to_committee(parcel):
        app = receive(planner, world, parcel=parcel).json()
        planner.post(url("acknowledge", app), {}, format="json")
        planner.post(url("inspect", app), {"summary": "Seen."}, format="json")
        return planner.post(
            url("report", app),
            {"recommendation": "refuse", "report": "Road reservation."},
            format="json",
        ).json()

    app = to_committee("P-001")
    # r.44(13): reasons in writing.
    assert admin.post(url("decide", app), {"decision": "refuse"}, format="json").status_code == 400
    refused = admin.post(
        url("decide", app),
        {"decision": "refuse", "reasons": "The plot is in the road reservation."},
        format="json",
    ).json()
    assert refused["status"] == "refused" and refused["next_due"] is None
    letter = planner.get(url("letter", refused))
    assert letter.status_code == 200 and letter.content.startswith(b"%PDF")
    assert (
        planner.post(
            url("fees", refused), {"stage": "permit", "amount": "1", "receipt": "x"}, format="json"
        ).status_code
        == 400
    )

    # Deferred: looked at again, reported again, then granted.
    app = to_committee("P-002")
    deferred = admin.post(
        url("decide", app),
        {"decision": "defer", "reasons": "Structural drawings missing."},
        format="json",
    ).json()
    assert (
        deferred["status"] == "deferred" and planner.get(url("letter", deferred)).status_code == 200
    )
    planner.post(url("inspect", deferred), {"summary": "Drawings now in."}, format="json")
    again = planner.post(url("report", deferred), {"recommendation": "grant"}, format="json").json()
    assert again["status"] == "reported" and len(again["inspections"]) == 2
    granted = admin.post(url("decide", again), {"decision": "grant"}, format="json").json()
    assert granted["status"] == "granted" and planner.get(url("letter", granted)).status_code == 404


def test_the_automatic_checks_advise_from_the_map(world, admin):
    """Gate: each check catches its seeded problem and passes a clean site."""
    world.set_roles()
    planner = world.client
    standard = {
        "zone": "residential",
        "min_plot_m2": 1000,
        "min_width_m": 20,
        "max_floors": 2,
        "front_setback_m": 6,
        "side_setback_m": 3,
        "rear_setback_m": 3,
        "max_coverage_pct": 50,
        "prohibited_uses": ["filling station"],
        "build_in_flood_area": False,
    }
    assert admin.post(reverse("standard-list"), standard, format="json").status_code == 201

    app = receive(
        planner, world, parcel="P-006", proposed_use="Fuel filling station", proposed_floors=3
    ).json()
    assert app["checks"]["zone"] == {
        "value": "residential",
        "from": "the parcel's land use",
        "national": None,
        "name": None,
    }
    outcomes = {r["code"]: r["outcome"] for r in app["checks"]["results"]}
    assert outcomes == {
        "zone": "pass",
        "use": "fail",  # a filling station, where the zone prohibits one
        "plot_size": "fail",  # 900 m2 where 1,000 is asked
        "plot_width": "pass",  # 30 m at the street where 20 is asked
        "floors": "fail",  # 3 where 2 are allowed
        "drawings": "unknown",  # setbacks and coverage are read off the block plan
        "flood": "fail",  # P-006 is in the flood-prone area, where the zone allows no building
        "access": "pass",  # Main Street is 10 m away
        "overlap": "pass",
    }
    assert result(app, "plot_width")["measured_m"] == pytest.approx(30, abs=0.3)
    assert result(app, "access")["distance_m"] == pytest.approx(10, abs=0.5)
    drawings = result(app, "drawings")["detail"]
    assert "6 m at the front" in drawings and "coverage up to 50%" in drawings
    # Half of the 900 m2 plot may be built on.
    assert int(drawings.split("(")[1].split(" m²")[0]) == pytest.approx(450, abs=2)
    assert app["check_counts"] == {"pass": 4, "fail": 4, "warn": 0, "unknown": 1}

    # A clean site in the same zone, once the plot minimum is met.
    admin.patch(
        reverse("standard-detail", args=[app["checks"]["standard"]["id"]]),
        {"min_plot_m2": 800},
        format="json",
    )
    clean = receive(planner, world, parcel="P-001").json()
    assert {r["code"]: r["outcome"] for r in clean["checks"]["results"]} == {
        "zone": "pass", "use": "pass", "plot_size": "pass", "plot_width": "pass", "floors": "pass",
        "drawings": "unknown", "flood": "pass", "access": "pass", "overlap": "pass",
    }  # fmt: skip

    # A second application on the same land is pointed out; correcting the first re-runs its checks.
    second = receive(planner, world, parcel="P-006", proposed_use="Shop").json()
    assert (
        result(second, "overlap")["outcome"] == "warn"
        and app["number"] in result(second, "overlap")["detail"]
    )
    fixed = planner.patch(
        url("detail", app), {"proposed_use": "House", "proposed_floors": 2}, format="json"
    ).json()
    assert (
        result(fixed, "use")["outcome"] == "pass" and result(fixed, "floors")["outcome"] == "pass"
    )
    assert Feature.objects.get(pk=fixed["site"]).properties["proposed_use"] == "House"


def test_sites_numbers_and_kinds(world):
    planner = world.client
    # A site given as a shape, in another coordinate system.
    parcel = world.features("parcels", "parcel_id")["P-002"]
    wgs = planner.post(
        reverse("crs-transform"),
        {"geometry": parcel["geometry"], "from_crs": "EPSG:2136", "to_crs": "EPSG:4326"},
        format="json",
    )
    assert wgs.status_code == 200, wgs.content
    drawn = receive(
        planner,
        world,
        site_feature=None,
        site_geometry=wgs.json()["geometry"],
        site_crs="EPSG:4326",
    )
    assert drawn.status_code == 201, drawn.content
    assert result(drawn.json(), "plot_size")["measured_m2"] == pytest.approx(900, abs=5)
    assert (
        receive(
            planner,
            world,
            site_feature=None,
            site_geometry={"type": "Point", "coordinates": [0, 0]},
            site_crs="EPSG:9999",
        ).status_code
        == 400
    )
    no_site = receive(planner, world, site_feature=None).json()
    assert no_site["site"] is None and no_site["checks"]["results"][0]["code"] == "site"

    # One series per kind and year. A category belongs to one kind of permit.
    planning = receive(
        planner, world, kind="planning", category="change_of_use", proposed_floors=None
    ).json()
    assert planning["number"] == f"DA/PP/{TODAY.year}/0001"
    assert [r["code"] for r in planning["requirements"]] == [
        "land_right",
        "site_plan",
        "block_plan",
        "zoning_report",
    ]
    assert receive(planner, world, parcel="P-003").json()["number"] == f"DA/DP/{TODAY.year}/0003"
    assert receive(planner, world, kind="planning", category="building").status_code == 400
    assert receive(planner, world, category="swimming").status_code == 400
    # The officer asks for a report "where applicable".
    asked = planner.patch(
        url("detail", planning), {"extra_requirements": ["traffic"]}, format="json"
    ).json()
    assert asked["requirements"][-1] == {
        "code": "traffic",
        "label": "Traffic impact report",
        "rule": "r.44(3)(f), r.45(9)(g)",
        "asked_for": True,
        "submitted": 0,
    }
    assert (
        planner.patch(
            url("detail", planning), {"extra_requirements": ["weather"]}, format="json"
        ).status_code
        == 400
    )
    assert (
        planner.patch(url("detail", planning), {"kind": "development"}, format="json").status_code
        == 400
    )


def test_fees_roles_and_tenancy(world, admin, api, members_a, district_a, district_b, make_member):
    planner = world.client
    fees = reverse("permit-fee-list")
    line = {
        "stage": "processing",
        "kind": "development",
        "label": "Processing fee, development permit",
        "amount": "150.00",
    }
    assert (
        planner.post(fees, line, format="json").status_code == 403
    )  # the fee-fixing resolution is the administrator's
    assert admin.post(fees, line, format="json").status_code == 201
    assert admin.post(fees, line, format="json").status_code == 400  # one per line
    assert (
        admin.post(fees, {**line, "category": "demolition"}, format="json").status_code == 400
    )  # a planning-permit category
    assert planner.get(fees).json()[0]["amount"] == "150.00"

    app = receive(planner, world).json()
    viewer = api(members_a[Role.VIEWER], district_a)
    seen = viewer.get(url("detail", app)).json()
    # Contact details are personal data: shown to those who may see restricted fields.
    assert seen["applicant_name"] == "Ama Mensah" and seen["applicant_phone"] == "restricted"
    assert planner.get(url("detail", app)).json()["applicant_phone"] == "0240000000"
    assert viewer.post(url("acknowledge", app), {}, format="json").status_code == 403

    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert (
        other.get(reverse(LIST)).json()["results"] == []
        and other.get(url("detail", app)).status_code == 404
    )
    assert other.post(url("acknowledge", app), {}, format="json").status_code == 404
    assert other.get(fees).json() == []
    assert receive(other, world).status_code == 404  # not their project
    with tenant_context(district_b.id):
        assert Application.objects.count() == 0

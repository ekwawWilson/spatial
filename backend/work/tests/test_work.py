# ruff: noqa: E501 - long assertions read better on one line
"""Phase 23: the work list across the modules, handing records to officers,
the quick search, and the setup checklist for a new district."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from committees.models import Committee, Meeting
from core.models import AuditLog, Role
from core.tenancy import tenant_context
from dataroom.models import InformationRequest
from enforcement.models import Case
from landchange.models import Application as LandApplication
from permits.models import Application
from projects.models import PlanProject

pytestmark = pytest.mark.django_db

TODAY = date.today()


@pytest.fixture
def records(world, district_a):
    with tenant_context(district_a.id):
        project = PlanProject.objects.get(pk=world.project)
        permit = Application.objects.create(
            district_id=district_a.id,
            project=project,
            number="DA/DP/2026/0001",
            kind="development",
            category="building",
            applicant_name="Ama Mensah",
            proposed_use="Residential",
            received_on=TODAY - timedelta(days=40),
        )
        land = LandApplication.objects.create(
            district_id=district_a.id,
            project=project,
            number="DA/RZ/2026/0001",
            kind="rezoning",
            applicant_name="Kofi Boateng",
            received_on=TODAY - timedelta(days=3),
        )
        case = Case.objects.create(
            district_id=district_a.id,
            project=project,
            number="DA/EN/2026/0001",
            origin="inspection",
            contravention="no_permit",
            opened_on=TODAY,
            owner_name="Kwesi Appiah",
        )
        InformationRequest.objects.create(
            district_id=district_a.id,
            reference="DA/IR/2026/0001",
            name="Akua Owusu",
            subject="Zoning of plot 12",
            body="?",
            received_on=TODAY - timedelta(days=10),
        )
        committee = Committee.objects.create(district_id=district_a.id, kind="dspc")
        meeting = Meeting.objects.create(
            district_id=district_a.id, committee=committee, held_on=TODAY + timedelta(days=2)
        )
    world.permit, world.land, world.case, world.meeting = permit, land, case, meeting
    return world


def test_the_work_list(records, api, members_a, district_a):
    url = reverse("work")
    viewer = api(members_a[Role.VIEWER], district_a)
    data = viewer.get(url).json()
    by_kind = {i["kind"]: i for i in data["items"]}
    assert set(by_kind) >= {"permit", "land", "case", "request", "meeting"}
    permit = by_kind["permit"]
    assert (permit["number"], permit["link"], permit["assignable"]) == (
        "DA/DP/2026/0001",
        f"/projects/{records.project}/permits/{records.permit.pk}",
        True,
    )
    request = by_kind["request"]
    assert (request["overdue"], request["days"], request["rule"]) == (True, -5, "r.64(7)")
    meeting = by_kind["meeting"]
    assert meeting["step"].startswith("Serve the notice") and meeting["overdue"] is True
    assert by_kind["case"]["step"] == "Serve a notice" and by_kind["case"]["due_on"] is None
    # The most pressing first: everything late, then by date, then the undated.
    flags = [(i["overdue"], i["due_on"] is None) for i in data["items"]]
    assert flags == sorted(flags, key=lambda f: (not f[0], f[1]))
    assert data["items"][-1]["due_on"] is None
    # Names of people only for the roles that may see them.
    assert all(i["who"] is None for i in data["items"])
    assert "Ama" not in str(data) and "Akua" not in str(data)
    planner = api(members_a[Role.PLANNER], district_a).get(url).json()
    assert {i["kind"]: i["who"] for i in planner["items"]}["permit"] == "Ama Mensah"
    # Counts; the setup checklist is the administrator's alone.
    assert data["counts"]["unassigned"] == 3 and data["counts"]["mine"] == 0
    assert data["counts"]["overdue"] == sum(1 for i in data["items"] if i["overdue"])
    assert data["setup"] is None and planner["setup"] is None


def test_handing_records_to_officers(records, api, members_a, district_a, district_b, make_member):
    assign = reverse("work-assign")
    planner = api(members_a[Role.PLANNER], district_a)
    field = members_a[Role.FIELD_OFFICER]
    officers = planner.get(reverse("work-officers")).json()
    assert {o["role"] for o in officers} == {"district_admin", "planner", "field_officer"}

    done = planner.post(
        assign, {"kind": "permit", "id": records.permit.pk, "officer": field.pk}, format="json"
    )
    assert done.status_code == 200, done.content
    assert done.json()["officer"] == {"id": field.pk, "name": field.email}
    detail = planner.get(reverse("permit-application-detail", args=[records.permit.pk])).json()
    assert detail["officer"]["id"] == field.pk
    with tenant_context(district_a.id):
        assert AuditLog.objects.filter(
            table_name="permits_application", action="UPDATE", row_id=str(records.permit.pk)
        ).exists()

    # Their own list.
    mine = api(field, district_a).get(reverse("work"), {"mine": "1"}).json()
    assert [i["number"] for i in mine["items"]] == ["DA/DP/2026/0001"]
    assert mine["counts"]["mine"] == 1

    # A case, then taken back.
    assert (
        planner.post(
            assign, {"kind": "case", "id": records.case.pk, "officer": field.pk}, format="json"
        ).status_code
        == 200
    )
    back = planner.post(
        assign, {"kind": "case", "id": records.case.pk, "officer": None}, format="json"
    )
    assert back.json()["officer"] is None

    # Who may hand records out, and to whom.
    viewer = api(members_a[Role.VIEWER], district_a)
    assert (
        viewer.post(
            assign, {"kind": "permit", "id": records.permit.pk, "officer": field.pk}, format="json"
        ).status_code
        == 403
    )
    assert (
        api(field, district_a)
        .post(assign, {"kind": "land", "id": records.land.pk, "officer": field.pk}, format="json")
        .status_code
        == 403
    )
    outsider = make_member(district_b, Role.PLANNER, "b.planner@example.test")
    for bad in (
        {"kind": "permit", "id": records.permit.pk, "officer": members_a[Role.VIEWER].pk},
        {"kind": "permit", "id": records.permit.pk, "officer": outsider.pk},
        {"kind": "permit", "id": 999999, "officer": field.pk},
        {"kind": "parcel", "id": records.permit.pk, "officer": field.pk},
    ):
        assert planner.post(assign, bad, format="json").status_code == 400, bad
    # Another district never sees the record.
    b_admin = make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test")
    assert (
        api(b_admin, district_b)
        .post(
            assign,
            {"kind": "permit", "id": records.permit.pk, "officer": outsider.pk},
            format="json",
        )
        .status_code
        == 400
    )
    assert api(b_admin, district_b).get(reverse("work")).json()["items"] == []


def test_quick_search(records, api, members_a, district_a, district_b, make_member):
    url = reverse("search")
    planner = api(members_a[Role.PLANNER], district_a)
    found = planner.get(url, {"q": "0001"}).json()["results"]
    assert {r["kind"] for r in found} >= {"permit", "land", "case", "request"}
    permit = next(r for r in found if r["kind"] == "permit")
    assert permit["link"] == f"/projects/{records.project}/permits/{records.permit.pk}"
    # By an applicant's name: only for roles that may see names.
    assert [r["title"] for r in planner.get(url, {"q": "mensah"}).json()["results"]] == [
        "DA/DP/2026/0001"
    ]
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(url, {"q": "mensah"}).json()["results"] == []
    assert "Ama" not in str(viewer.get(url, {"q": "0001"}).json())
    # A project by name; too short a search finds nothing; another district finds nothing.
    assert any(
        r["kind"] == "project" for r in planner.get(url, {"q": "relations"}).json()["results"]
    )
    assert planner.get(url, {"q": "D"}).json()["results"] == []
    b = make_member(district_b, Role.PLANNER, "b.planner@example.test")
    assert api(b, district_b).get(url, {"q": "0001"}).json()["results"] == []


def test_setup_checklist(records, api, members_a, district_a):
    admin = api(members_a[Role.DISTRICT_ADMIN], district_a)
    setup = {s["code"]: s for s in admin.get(reverse("work")).json()["setup"]}
    assert list(setup) == [
        "crs",
        "staff",
        "project",
        "basemap",
        "committees",
        "fees",
        "rates",
        "dataroom",
    ]
    assert setup["staff"]["done"] and setup["project"]["done"]
    # The committee was made without members.
    assert not setup["committees"]["done"] and setup["committees"]["link"] == "/committees"
    assert setup["fees"]["link"] == f"/projects/{records.project}/permits"
    assert not setup["dataroom"]["done"]

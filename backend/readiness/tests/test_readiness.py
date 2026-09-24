"""Phase 7: the readiness checklist, its metrics, score and actions."""

import csv
import io
import json
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from projects.models import Feature
from readiness.defaults import DEFAULT_ITEMS
from readiness.models import Item, Template

pytestmark = pytest.mark.django_db

# A 1000 ft square planning area in the Ghana National Grid (feet).
X0, Y0, SIDE = 1190000.0, 337000.0, 1000.0


def ring(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


AREA = ring(X0, Y0, X0 + SIDE, Y0 + SIDE)
WEST_HALF = ring(X0, Y0, X0 + SIDE / 2, Y0 + SIDE)
EVERYWHERE = ring(X0 - 10, Y0 - 10, X0 + SIDE + 10, Y0 + SIDE + 10)


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def admin(api, members_a, district_a):
    return api(members_a[Role.DISTRICT_ADMIN], district_a)


@pytest.fixture
def viewer(api, members_a, district_a):
    return api(members_a[Role.VIEWER], district_a)


def new_project(client, name="Readiness plan"):
    return client.post(reverse("project-list"), {"name": name}, format="json").json()


def set_area(client, project_id, coords=AREA):
    response = client.put(
        reverse("project-boundary", args=[project_id]),
        {"geometry": {"type": "Polygon", "coordinates": [coords]}, "method": "coordinates"},
        format="json",
    )
    assert response.status_code == 200, response.content


def checklist(client, project_id):
    response = client.get(reverse("project-checklist", args=[project_id]))
    assert response.status_code == 200, response.content
    return response.json()


def item_by_key(data, key):
    return next(item for item in data["items"] if item["key"] == key)


def buildings_layer(client, project_id, name="Buildings and land use"):
    response = client.post(
        reverse("layer-list"),
        {
            "project": project_id,
            "name": name,
            "domain": "C",
            "geometry_type": "polygon",
            "schema": [
                {"name": "use", "type": "text"},
                {"name": "storeys", "type": "integer"},
            ],
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def add(client, layer_id, coords, **properties):
    response = client.post(
        reverse("layer-features", args=[layer_id]),
        {"geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": properties},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def patch_item(client, item_id, **values):
    return client.patch(reverse("checklist-item-detail", args=[item_id]), values, format="json")


# --- Template and instances --------------------------------------------------------------


def test_a_new_project_gets_the_default_checklist(planner):
    project = new_project(planner)
    data = checklist(planner, project["id"])
    assert data["total"] == len(DEFAULT_ITEMS) == 21
    assert [g["group"] for g in data["groups"]] == [
        "authority",
        "planning_area",
        "base_map",
        "existing",
        "people",
    ]
    assert data["score"] == 0
    assert all(item["status"] == "not_started" for item in data["items"])


def test_district_template_is_used_for_new_projects_only(admin, planner, district_a):
    before = new_project(planner, "Before")
    template_url = reverse("readiness-template")
    assert admin.get(template_url).json()["own"] is False
    assert planner.post(template_url).status_code == 403
    assert admin.post(template_url).status_code == 201

    created = admin.post(
        reverse("template-item-list"),
        {
            "group": "people",
            "key": "chief-consent",
            "title": "Chief's written consent",
            "kind": "document",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    bad = admin.post(
        reverse("template-item-list"),
        {"group": "existing", "key": "x", "title": "X", "kind": "layer", "rules": {"speed": 1}},
        format="json",
    )
    assert bad.status_code == 400

    after = new_project(planner, "After")
    assert checklist(planner, after["id"])["total"] == 22
    assert checklist(planner, before["id"])["total"] == 21  # unchanged...
    refreshed = planner.post(reverse("project-checklist", args=[before["id"]])).json()
    assert refreshed["added"] == 1 and refreshed["total"] == 22  # ...until asked

    # The platform default is untouched, and the district can go back to it.
    default = Template.objects.get(district__isnull=True)
    assert default.items.count() == 21
    assert admin.delete(template_url).status_code == 204
    assert admin.get(template_url).json()["own"] is False


# --- Metrics -----------------------------------------------------------------------------


def test_metrics_on_known_data(planner):
    """Gate: feature count, coverage, attribute completeness, age and % verified."""
    project = new_project(planner)
    set_area(planner, project["id"])
    layer = buildings_layer(planner, project["id"])
    first = add(planner, layer["id"], WEST_HALF, use="house", storeys=2)
    add(planner, layer["id"], ring(X0 + 100, Y0 + 100, X0 + 150, Y0 + 150), use="shop")
    Feature.objects.filter(pk=first["id"]).update(verified=True)

    item = item_by_key(checklist(planner, project["id"]), "buildings")
    assert item["linked_layer"] == layer["id"]  # linked by name
    m = item["metrics"]
    assert m["feature_count"] == 2
    assert 45 <= m["coverage"] <= 62  # the west half, plus the grid cells it touches
    assert m["attributes"] == pytest.approx(75.0)  # 3 of 4 values
    assert m["verified"] == pytest.approx(50.0)
    assert m["age_days"] == 0

    add(planner, layer["id"], EVERYWHERE, use="yard", storeys=0)
    m = item_by_key(checklist(planner, project["id"]), "buildings")["metrics"]
    assert m["coverage"] == pytest.approx(100.0)


def test_coverage_needs_the_planning_area(planner):
    project = new_project(planner)
    layer = buildings_layer(planner, project["id"])
    add(planner, layer["id"], AREA, use="house", storeys=1)
    item = item_by_key(checklist(planner, project["id"]), "buildings")
    assert item["metrics"]["coverage"] is None
    problems = [c["problem"] for c in item["checks"] if not c["ok"]]
    assert "Coverage needs the planning-area boundary." in problems


# --- Status, rules and score ---------------------------------------------------------------


def test_items_are_ready_only_when_their_rules_are_met(planner):
    project = new_project(planner)
    set_area(planner, project["id"])
    layer = buildings_layer(planner, project["id"])
    add(planner, layer["id"], WEST_HALF, use="house", storeys=2)
    item = item_by_key(checklist(planner, project["id"]), "buildings")

    refused = patch_item(planner, item["id"], status="ready")
    assert refused.status_code == 400
    assert any("Covers" in p for p in refused.json()["status"])

    add(planner, layer["id"], EVERYWHERE, use="yard", storeys=0)
    accepted = patch_item(planner, item["id"], status="ready")
    assert accepted.status_code == 200, accepted.content
    assert accepted.json()["complete"] is True


def test_boundary_item_follows_the_boundary_status(planner):
    project = new_project(planner)
    item = item_by_key(checklist(planner, project["id"]), "boundary")
    assert any("planning area is needed" in b for b in item["blockers"])
    set_area(planner, project["id"])
    assert patch_item(planner, item["id"], status="ready").status_code == 400  # still draft
    planner.post(
        reverse("project-boundary-status", args=[project["id"]]),
        {"status": "agreed"},
        format="json",
    )
    assert patch_item(planner, item["id"], status="ready").status_code == 200


def test_score_updates_after_an_import(planner, tmp_path, django_capture_on_commit_callbacks):
    """Gate: import into a new layer named after the item; the item links to
    it, is measured, and the score moves once it's marked ready."""
    project = new_project(planner)
    data = checklist(planner, project["id"])
    item = item_by_key(data, "development")  # min_features: 1
    assert item["linked_layer"] is None

    path = tmp_path / "permits.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-1.75, 4.93]},
                        "properties": {"ref": "P1"},
                    }
                ],
            }
        )
    )
    with open(path, "rb") as fh:
        job = planner.post(
            reverse("datajob-upload"), {"project": project["id"], "file": fh}, format="multipart"
        ).json()
    source = job["inspection"]["layers"][0]
    with django_capture_on_commit_callbacks(execute=True):
        response = planner.post(
            reverse("datajob-run", args=[job["id"]]),
            {
                "layers": [
                    {
                        "source": source["name"],
                        "crs": "EPSG:4326",
                        "crs_confirmed": True,
                        "new_layer": {
                            "name": item["title"],
                            "domain": item["domain"],
                            "geometry_type": "point",
                        },
                        "fields": [
                            {"source": f["name"], "target": f["suggested_name"], "type": f["type"]}
                            for f in source["fields"]
                        ],
                    }
                ]
            },
            format="json",
        )
    assert response.status_code in (200, 202), response.content

    item = item_by_key(checklist(planner, project["id"]), "development")
    assert item["linked_layer"] is not None
    assert item["metrics"]["feature_count"] == 1
    assert item["rules_met"] is True
    assert patch_item(planner, item["id"], status="ready").status_code == 200
    assert checklist(planner, project["id"])["score"] == round(100 / 21)


def test_only_district_admins_verify(planner, admin):
    project = new_project(planner)
    item = item_by_key(checklist(planner, project["id"]), "assembly-resolution")
    assert patch_item(planner, item["id"], status="verified").status_code == 400
    assert patch_item(admin, item["id"], status="verified").status_code == 200
    assert patch_item(planner, item["id"], status="in_progress").status_code == 400


def test_owner_must_be_a_member_and_layer_of_the_project(
    planner, members_a, make_member, district_b
):
    project = new_project(planner)
    other = new_project(planner, "Other")
    other_layer = buildings_layer(planner, other["id"], name="Elsewhere")
    item = item_by_key(checklist(planner, project["id"]), "buildings")
    outsider = make_member(district_b, Role.PLANNER, "outsider@example.test")
    assert patch_item(planner, item["id"], owner=outsider.id).status_code == 400
    assert patch_item(planner, item["id"], linked_layer=other_layer["id"]).status_code == 400
    ok = patch_item(
        planner, item["id"], owner=members_a[Role.PLANNER].id, due_date="2020-01-01", notes="Survey"
    )
    assert ok.status_code == 200
    assert ok.json()["owner_name"]
    assert any("Overdue" in b for b in ok.json()["blockers"])


# --- Actions -----------------------------------------------------------------------------


def test_draw_action_creates_the_items_layer(planner):
    project = new_project(planner)
    item = item_by_key(checklist(planner, project["id"]), "streets")
    url = reverse("checklist-item-create-layer", args=[item["id"]])
    response = planner.post(url)
    assert response.status_code == 201, response.content
    layer = planner.get(reverse("layer-detail", args=[response.json()["layer"]])).json()
    assert (layer["name"], layer["domain"], layer["geometry_type"]) == (
        "Streets and access",
        "D",
        "line",
    )
    assert response.json()["linked_layer"] == layer["id"]
    assert planner.post(url).status_code == 400  # already has one
    document = item_by_key(checklist(planner, project["id"]), "public-notice")
    assert (
        planner.post(reverse("checklist-item-create-layer", args=[document["id"]])).status_code
        == 400
    )


def test_attachments(planner, viewer):
    project = new_project(planner)
    item = item_by_key(checklist(planner, project["id"]), "assembly-resolution")
    upload = SimpleUploadedFile("resolution.pdf", b"%PDF-1.4 resolution", "application/pdf")
    response = planner.post(
        reverse("checklist-item-attachments", args=[item["id"]]),
        {"file": upload},
        format="multipart",
    )
    assert response.status_code == 201, response.content
    attachment = response.json()["attachments"][0]
    assert attachment["name"] == "resolution.pdf"

    download = viewer.get(reverse("checklist-attachment-download", args=[attachment["id"]]))
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == b"%PDF-1.4 resolution"
    assert (
        viewer.delete(reverse("checklist-attachment-detail", args=[attachment["id"]])).status_code
        == 403
    )
    assert (
        planner.delete(reverse("checklist-attachment-detail", args=[attachment["id"]])).status_code
        == 204
    )
    assert (
        item_by_key(checklist(planner, project["id"]), "assembly-resolution")["attachments"] == []
    )


def test_export_csv_and_pdf(planner):
    project = new_project(planner)
    url = reverse("project-checklist-export", args=[project["id"]])
    response = planner.get(url, {"format": "csv"})
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["Group", "Item", "Status"]
    assert "Agreed planning-area boundary" in [r[1] for r in rows if len(r) > 1]
    assert rows[-1][:2] == ["Score", "0%"]

    pdf = planner.get(url, {"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert planner.get(url, {"format": "xls"}).status_code == 400


def test_district_dashboard(planner):
    new_project(planner, "Alpha")
    new_project(planner, "Beta")
    data = planner.get(reverse("readiness-dashboard")).json()
    assert [p["name"] for p in data["projects"]] == ["Alpha", "Beta"]
    assert data["score"] == 0
    assert all(p["total"] == 21 for p in data["projects"])


# --- Tenancy, roles, audit -----------------------------------------------------------------


def test_other_districts_cannot_see_the_checklist(planner, api, make_member, district_b):
    project = new_project(planner)
    item = item_by_key(checklist(planner, project["id"]), "buildings")
    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(reverse("project-checklist", args=[project["id"]])).status_code == 404
    assert other.get(reverse("checklist-item-detail", args=[item["id"]])).status_code == 404
    assert patch_item(other, item["id"], notes="x").status_code == 404
    with tenant_context(district_b.id):
        assert Item.objects.count() == 0  # row-level security, not just the view filter


def test_viewers_read_but_cannot_change(planner, viewer):
    project = new_project(planner)
    item = item_by_key(checklist(viewer, project["id"]), "buildings")
    assert viewer.get(reverse("checklist-item-detail", args=[item["id"]])).status_code == 200
    assert patch_item(viewer, item["id"], notes="x").status_code == 403
    assert viewer.post(reverse("checklist-item-create-layer", args=[item["id"]])).status_code == 403
    assert viewer.post(reverse("project-checklist", args=[project["id"]])).status_code == 403


def test_item_changes_are_audited(planner):
    project = new_project(planner)
    item = item_by_key(checklist(planner, project["id"]), "plan-period")
    patch_item(planner, item["id"], status="in_progress", notes="10 years")
    entry = AuditLog.objects.filter(
        table_name="readiness_item", row_id=str(item["id"]), action="UPDATE"
    ).latest("id")
    assert entry.before["status"] == "not_started"
    assert entry.after["status"] == "in_progress"
    assert entry.after["notes"] == "10 years"


def test_attachment_files_stay_under_media(planner, settings):
    project = new_project(planner)
    item = item_by_key(checklist(planner, project["id"]), "public-notice")
    upload = SimpleUploadedFile("../../escape.txt", b"x", "text/plain")
    planner.post(
        reverse("checklist-item-attachments", args=[item["id"]]),
        {"file": upload},
        format="multipart",
    )
    files = [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]
    assert files and all(Path(settings.MEDIA_ROOT) in p.parents for p in files)

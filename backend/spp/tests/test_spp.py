"""Phase 8: .spp project files: contents, encryption, keys, and opening."""

import base64
import io
import os
import sqlite3
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.urls import reverse

from core.models import AuditLog, Role
from crs.services import register_custom
from projects.models import Feature, Layer, PlanProject
from spp import container, keys, package
from spp.models import FileRecord

pytestmark = pytest.mark.django_db


def new_key(key_id: str) -> str:
    return f"{key_id}:{base64.b64encode(os.urandom(32)).decode()}"


KEY_A = new_key("assembly-2026")
SQUARE = [
    [1190600.123456789, 337700.987654321],
    [1190800.5, 337700.25],
    [1190800.75, 337900.125],
    [1190600.0625, 337900.03125],
    [1190600.123456789, 337700.987654321],
]
LOCAL_TM = (
    "+proj=tmerc +lat_0=5.5 +lon_0=-0.2 +k=1 +x_0=50000 +y_0=50000 "
    "+a=6378300 +rf=296 +towgs84=-170,33,326,0,0,0,0 +units=m +no_defs"
)


@pytest.fixture(autouse=True)
def _org_key(settings):
    settings.SPP_ORG_KEYS = KEY_A


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def admin(api, members_a, district_a):
    return api(members_a[Role.DISTRICT_ADMIN], district_a)


@pytest.fixture
def planner_b(api, make_member, district_b):
    return api(make_member(district_b, Role.PLANNER, "b.planner@example.test"), district_b)


def make_project(client, name="Kasoa local plan", crs=None):
    """A project with a planning area, a parcels layer (two features, one
    edited so it has history), a styled layer, and checklist progress."""
    body = {"name": name, "community": "Kasoa"}
    if crs:
        body["crs"] = crs
    project = client.post(reverse("project-list"), body, format="json").json()
    assert "id" in project, project
    layer = client.post(
        reverse("layer-list"),
        {
            "project": project["id"],
            "name": "Parcels",
            "domain": "B",
            "geometry_type": "polygon",
            "schema": [
                {"name": "pid", "type": "text", "required": True},
                {"name": "area", "type": "decimal"},
            ],
        },
        format="json",
    ).json()
    features = []
    for i, shift in enumerate((0, 500)):
        coords = [[x + shift, y] for x, y in SQUARE]
        created = client.post(
            reverse("layer-features", args=[layer["id"]]),
            {
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {"pid": f"P-{i}", "area": 1.5 + i},
            },
            format="json",
        )
        assert created.status_code == 201, created.content
        features.append(created.json())
    # A second version of the first feature.
    moved = [[x + 10, y + 10] for x, y in SQUARE]
    edited = client.patch(
        reverse("feature-detail", args=[features[0]["id"]]),
        {
            "version": 1,
            "geometry": {"type": "Polygon", "coordinates": [moved]},
            "properties": {"pid": "P-0", "area": 2.25},
        },
        format="json",
    )
    assert edited.status_code == 200, edited.content
    return project, layer, features, moved


def add_checklist_progress(client, project_id):
    data = client.get(reverse("project-checklist", args=[project_id])).json()
    item = next(i for i in data["items"] if i["key"] == "assembly-resolution")
    client.patch(
        reverse("checklist-item-detail", args=[item["id"]]),
        {"status": "ready", "notes": "Resolution 14/2026", "due_date": "2026-12-01"},
        format="json",
    )
    upload = SimpleUploadedFile("resolution.pdf", b"%PDF-1.4 the resolution", "application/pdf")
    response = client.post(
        reverse("checklist-item-attachments", args=[item["id"]]),
        {"file": upload},
        format="multipart",
    )
    assert response.status_code == 201, response.content


def save(client, project_id) -> bytes:
    response = client.post(reverse("project-spp-save", args=[project_id]))
    assert response.status_code == 200, getattr(response, "content", b"")
    assert response["Content-Disposition"].endswith('.spp"')
    return b"".join(response.streaming_content)


def open_file(client, data: bytes, name="project.spp"):
    upload = SimpleUploadedFile(name, data, "application/octet-stream")
    return client.post(reverse("spp-open"), {"file": upload}, format="multipart")


def native(client, layer_id):
    url = reverse("layer-features", args=[layer_id]) + "?geometry=native"
    return {f["properties"]["pid"]: f for f in client.get(url).json()["features"]}


# --- The file --------------------------------------------------------------------------


def test_the_file_is_unreadable_without_the_platform(planner):
    """Gate: generic tools can't open it (not a zip, not a GeoPackage) and
    nothing about the project is legible in it."""
    project, *_ = make_project(planner)
    data = save(planner, project["id"])
    assert data.startswith(container.MAGIC)
    assert not zipfile.is_zipfile(io.BytesIO(data))
    assert b"SQLite format 3" not in data and b"PK\x03\x04" not in data
    for secret in (b"Kasoa", b"Parcels", b"P-0", b"manifest", b"gpkg"):
        assert secret not in data
    # Only the key's id is readable.
    assert b"assembly-2026" in data


def test_sqlite_refuses_it(planner, tmp_path):
    project, *_ = make_project(planner)
    path = tmp_path / "p.spp"
    path.write_bytes(save(planner, project["id"]))
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(path).execute("SELECT count(*) FROM sqlite_master").fetchall()


# --- Opening on another "server" (another district) -------------------------------------


def test_opens_in_another_district_with_everything(planner, planner_b, district_a, district_b):
    """Gate: the same key opens the file elsewhere; coordinates, attributes,
    history, checklist and documents arrive intact under new ids."""
    project, layer, features, moved = make_project(planner)
    planner.put(
        reverse("project-boundary", args=[project["id"]]),
        {"geometry": {"type": "Polygon", "coordinates": [SQUARE]}, "method": "coordinates"},
        format="json",
    )
    planner.post(
        reverse("project-boundary-status", args=[project["id"]]),
        {"status": "agreed"},
        format="json",
    )
    style = {**layer["style"], "fill": "#123456"}
    planner.patch(reverse("layer-detail", args=[layer["id"]]), {"style": style}, format="json")
    add_checklist_progress(planner, project["id"])
    before = native(planner, layer["id"])

    data = save(planner, project["id"])
    response = open_file(planner_b, data)
    assert response.status_code == 201, response.content
    report = response.json()
    assert report["name"] == "Kasoa local plan" and report["renamed_from"] is None
    assert report["from_district"] == district_a.name
    assert (report["layers"], report["features"]) == (2, 3)  # parcels + planning area
    assert report["new_feature_ids"] == 3  # the originals still exist on this server

    opened = PlanProject.objects.get(pk=report["project"])
    assert opened.district_id == district_b.id and opened.pk != project["id"]
    assert opened.crs.code == "EPSG:2136"
    assert opened.boundary_status == "agreed" and opened.boundary_feature is not None
    parcels = Layer.objects.get(project=opened, name="Parcels")
    assert parcels.pk != layer["id"]
    assert parcels.style["fill"] == "#123456"
    assert [f["name"] for f in parcels.schema] == ["pid", "area"]

    # Coordinates of record: exactly the same numbers.
    after = native(planner_b, parcels.pk)
    assert set(after) == {"P-0", "P-1"}
    for pid, original in before.items():
        assert after[pid]["geometry"] == original["geometry"]
        assert after[pid]["properties"] == original["properties"]
        assert after[pid]["meta"]["version"] == original["meta"]["version"]
        assert after[pid]["id"] != original["id"]
    assert after["P-0"]["geometry"]["coordinates"] == [moved]

    # History came too: the first version can be seen and restored.
    history = planner_b.get(reverse("feature-history", args=[after["P-0"]["id"]])).json()
    first = history[-1]
    assert (first["version"], first["action"]) == (1, "INSERT")
    assert first["geometry"]["coordinates"] == [SQUARE]
    restored = planner_b.post(
        reverse("feature-restore", args=[after["P-0"]["id"]]),
        {"audit_id": first["audit_id"], "version": after["P-0"]["meta"]["version"]},
        format="json",
    )
    assert restored.status_code == 200, restored.content
    assert restored.json()["geometry"]["coordinates"] == [SQUARE]

    # Checklist state and its document.
    items = planner_b.get(reverse("project-checklist", args=[opened.pk])).json()["items"]
    resolution = next(i for i in items if i["key"] == "assembly-resolution")
    assert (resolution["status"], resolution["notes"], resolution["due_date"]) == (
        "ready",
        "Resolution 14/2026",
        "2026-12-01",
    )
    assert len(items) == 22  # the file's checklist, not a second default one
    download = planner_b.get(
        reverse("checklist-attachment-download", args=[resolution["attachments"][0]["id"]])
    )
    assert b"".join(download.streaming_content) == b"%PDF-1.4 the resolution"

    # The original is untouched, and both ends are on record.
    assert native(planner, layer["id"]) == before
    assert FileRecord.objects.filter(district=district_a, direction="saved").count() == 1
    record = FileRecord.objects.get(district=district_b, direction="opened")
    assert record.key_id == "assembly-2026" and record.project_id == opened.pk
    assert AuditLog.objects.filter(table_name="spp_filerecord", row_id=str(record.pk)).exists()


def test_opening_where_the_project_exists_makes_a_renamed_copy(planner):
    project, layer, *_ = make_project(planner)
    data = save(planner, project["id"])
    report = open_file(planner, data).json()
    assert report["name"] == "Kasoa local plan (2)"
    assert report["renamed_from"] == "Kasoa local plan"
    assert open_file(planner, data).json()["name"] == "Kasoa local plan (3)"


def test_feature_ids_survive_when_the_original_is_gone(planner):
    """Opening on a server that doesn't have the project keeps feature UUIDs."""
    project, layer, *_ = make_project(planner)
    uuids = set(Feature.objects.filter(layer_id=layer["id"]).values_list("uuid", flat=True))
    data = save(planner, project["id"])
    PlanProject.objects.filter(pk=project["id"]).update(boundary_feature=None)
    Feature.objects.filter(layer__project_id=project["id"]).delete()
    Layer.objects.filter(project_id=project["id"]).delete()
    PlanProject.objects.filter(pk=project["id"]).delete()

    report = open_file(planner, data).json()
    assert report["new_feature_ids"] == 0 and report["renamed_from"] is None
    kept = set(
        Feature.objects.filter(layer__project_id=report["project"]).values_list("uuid", flat=True)
    )
    assert kept == uuids


def test_custom_coordinate_system_travels_with_the_project(
    planner, planner_b, district_a, district_b
):
    system = register_custom(
        name="Kasoa local grid", definition=LOCAL_TM, district=district_a, user=None
    )
    body = {"name": "Local grid plan", "crs": system.pk}
    project = planner.post(reverse("project-list"), body, format="json").json()
    layer = planner.post(
        reverse("layer-list"),
        {
            "project": project["id"],
            "name": "Pegs",
            "geometry_type": "point",
            "schema": [{"name": "pid", "type": "text"}],
        },
        format="json",
    ).json()
    planner.post(
        reverse("layer-features", args=[layer["id"]]),
        {
            "geometry": {"type": "Point", "coordinates": [50123.456789, 49876.54321]},
            "properties": {"pid": "A"},
        },
        format="json",
    )
    report = open_file(planner_b, save(planner, project["id"])).json()
    assert len(report["crs_added"]) == 1, report
    opened = PlanProject.objects.get(pk=report["project"])
    assert opened.crs.district_id == district_b.id and opened.crs.srid != system.srid
    pegs = Layer.objects.get(project=opened)
    assert native(planner_b, pegs.pk)["A"]["geometry"]["coordinates"] == [50123.456789, 49876.54321]
    # Its history is readable under the new SRID.
    feature_id = native(planner_b, pegs.pk)["A"]["id"]
    history = planner_b.get(reverse("feature-history", args=[feature_id])).json()
    assert history[-1]["geometry"]["coordinates"] == [50123.456789, 49876.54321]
    # Opening again reuses the system it added.
    assert open_file(planner_b, save(planner, project["id"])).json()["crs_added"] == []


# --- Keys ------------------------------------------------------------------------------


def test_a_different_key_gives_a_clear_error(planner, settings):
    """Gate: a server without the file's key explains why it can't open it."""
    project, *_ = make_project(planner)
    data = save(planner, project["id"])
    count = PlanProject.objects.count()

    settings.SPP_ORG_KEYS = new_key("another-assembly")
    response = open_file(planner, data)
    assert response.status_code == 400
    assert "organisation key 'assembly-2026', which this server doesn't have" in str(
        response.json()
    )

    # Same id, different secret (two organisations chose the same name).
    settings.SPP_ORG_KEYS = new_key("assembly-2026")
    response = open_file(planner, data)
    assert response.status_code == 400
    assert "isn't the one the file was made with" in str(response.json())
    assert PlanProject.objects.count() == count


def test_rotation_keeps_old_files_opening(planner, settings):
    project, *_ = make_project(planner)
    old_file = save(planner, project["id"])
    settings.SPP_ORG_KEYS = new_key("assembly-2027") + "," + KEY_A  # new first, old kept
    assert open_file(planner, old_file).status_code == 201
    new_file = save(planner, project["id"])
    assert FileRecord.objects.filter(direction="saved").latest("id").key_id == "assembly-2027"
    settings.SPP_ORG_KEYS = KEY_A  # a server that never got the new key
    assert open_file(planner, new_file).status_code == 400


def test_no_key_configured_is_explained(planner, settings):
    project, *_ = make_project(planner)
    data = save(planner, project["id"])
    settings.SPP_ORG_KEYS = ""
    response = planner.post(reverse("project-spp-save", args=[project["id"]]))
    assert response.status_code == 400 and "no organisation key" in str(response.json())
    assert open_file(planner, data).status_code == 400


@pytest.mark.parametrize(
    "value,problem",
    [
        ("nocolon", "expected key_id:base64key"),
        ("id:not-base64!", "not valid base64"),
        ("id:" + base64.b64encode(b"short").decode(), "must be 32 bytes"),
        (KEY_A + "," + KEY_A, "two keys called"),
    ],
)
def test_malformed_keys_are_reported_without_echoing_them(value, problem):
    with pytest.raises(keys.KeyError_) as error:
        keys.parse(value)
    assert problem in str(error.value)
    assert value.split(":")[-1] not in str(error.value) or ":" not in value


def test_key_command_generates_installs_and_lists(tmp_path, settings, capsys):
    env = tmp_path / ".env"
    env.write_text("DJANGO_DEBUG=false\nSPP_ORG_KEYS=\n")
    call_command("spp_key", "generate", "--id", "first", "--write-env", str(env))
    call_command("spp_key", "generate", "--id", "second", "--write-env", str(env))
    line = next(x for x in env.read_text().splitlines() if x.startswith("SPP_ORG_KEYS="))
    ring = keys.parse(line.split("=", 1)[1])
    assert [k.key_id for k in ring] == ["second", "first"]  # newest is active, old kept
    assert "DJANGO_DEBUG=false" in env.read_text()
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    with pytest.raises(CommandError):
        call_command("spp_key", "generate", "--id", "first", "--write-env", str(env))

    settings.SPP_ORG_KEYS = line.split("=", 1)[1]
    capsys.readouterr()
    call_command("spp_key", "list")
    listed = capsys.readouterr().out
    assert "second" in listed and "active" in listed
    assert all(base64.b64encode(k.secret).decode() not in listed for k in ring)


def test_key_fingerprints_are_for_system_admins(api, system_admin, admin):
    assert admin.get(reverse("spp-keys")).status_code == 403
    body = api(system_admin).get(reverse("spp-keys")).json()
    assert body["configured"] is True
    assert body["keys"][0]["key_id"] == "assembly-2026" and body["keys"][0]["active"] is True
    assert KEY_A.split(":")[1] not in str(body)


# --- Tampering and versions --------------------------------------------------------------


def test_a_file_with_one_changed_byte_is_rejected(planner):
    """Gate: any single changed byte is detected, wherever it is."""
    project, *_ = make_project(planner)
    data = save(planner, project["id"])
    count = PlanProject.objects.count()
    positions = [0, 9, 13, 40, 200, 340, len(data) // 2, len(data) - 17, len(data) - 1]
    for position in positions:
        changed = bytearray(data)
        changed[position] ^= 0x01
        response = open_file(planner, bytes(changed))
        assert response.status_code == 400, position
    assert open_file(planner, data[:-1]).status_code == 400  # truncated
    assert open_file(planner, data + b"\x00").status_code == 400  # extended
    assert open_file(planner, b"just some bytes").status_code == 400
    assert "isn't a .spp project file" in str(open_file(planner, b"PK\x03\x04 a zip").json())
    assert PlanProject.objects.count() == count


def test_a_file_from_an_older_version_is_upgraded(planner, monkeypatch):
    """Gate: files written by an older package version still open. Version 1
    is the only one so far, so this drives the upgrade path with a stand-in
    next version: the reader is at 2 and upgrades the version-1 file."""
    project, *_ = make_project(planner)
    data = save(planner, project["id"])
    upgraded = []

    def one_to_two(root: Path) -> None:
        assert (root / "project.json").is_file()
        upgraded.append(root)

    monkeypatch.setattr(package, "PACKAGE_VERSION", 2)
    monkeypatch.setattr(package, "UPGRADES", {1: one_to_two})
    assert open_file(planner, data).status_code == 201
    assert len(upgraded) == 1

    monkeypatch.setattr(package, "UPGRADES", {})  # support for version 1 dropped
    assert "no longer supported" in str(open_file(planner, data).json())


def test_a_file_from_a_newer_version_is_refused(planner, monkeypatch):
    project, *_ = make_project(planner)
    data = save(planner, project["id"])
    monkeypatch.setattr(package, "PACKAGE_VERSION", 0)
    response = open_file(planner, data)
    assert response.status_code == 400 and "newer version" in str(response.json())

    newer = bytearray(data)
    newer[8:10] = (container.CONTAINER_VERSION + 1).to_bytes(2, "big")
    assert "newer version" in str(open_file(planner, bytes(newer)).json())


# --- Roles and tenancy -------------------------------------------------------------------


def test_roles(planner, api, members_a, district_a, planner_b):
    project, *_ = make_project(planner)
    data = save(planner, project["id"])
    for role in (Role.VIEWER, Role.FIELD_OFFICER):
        client = api(members_a[role], district_a)
        assert client.post(reverse("project-spp-save", args=[project["id"]])).status_code == 403
        assert open_file(client, data).status_code == 403
    # Another district can't save this district's project.
    assert planner_b.post(reverse("project-spp-save", args=[project["id"]])).status_code == 404


def test_basemaps_come_without_keys(planner, admin, planner_b, api, make_member, district_b):
    created = admin.post(
        reverse("basemap-list"),
        {
            "name": "Assembly drone tiles",
            "kind": "xyz",
            "url": "https://tiles.example.test/{z}/{x}/{y}.png",
            "requires_key": True,
            "api_key": "SECRET-KEY-123",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    project, *_ = make_project(planner)
    data = save(planner, project["id"])

    # A planner can't add basemaps: it's reported, not silently dropped.
    assert "Assembly drone tiles" in open_file(planner_b, data).json()["basemaps_skipped"]
    admin_b = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    report = open_file(admin_b, data).json()
    assert report["basemaps_added"] == ["Assembly drone tiles (needs its API key)"]
    listed = admin_b.get(reverse("basemap-list")).json()
    mine = next(b for b in listed if b["name"] == "Assembly drone tiles")
    assert mine["has_key"] is False

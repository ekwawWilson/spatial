"""Phase 10: push, pull, conflicts, photo uploads and ground-truthing."""

import hashlib
import uuid

import pytest
from django.urls import reverse

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from projects.models import Feature
from sync import photos
from sync.models import AppliedChange, Conflict, FieldTask, Photo, Tombstone

pytestmark = pytest.mark.django_db

DEVICE = "device-1"
# A point in the Ghana National Grid (feet) and roughly the same place in WGS 84.
NATIVE_POINT = [1190700.0, 337800.0]
SQUARE = [
    [1190600.0, 337700.0],
    [1190800.0, 337700.0],
    [1190800.0, 337900.0],
    [1190600.0, 337900.0],
    [1190600.0, 337700.0],
]


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def officer(api, members_a, district_a):
    return api(members_a[Role.FIELD_OFFICER], district_a)


@pytest.fixture
def project(planner):
    project = planner.post(reverse("project-list"), {"name": "Sync plan"}, format="json").json()
    layer = planner.post(
        reverse("layer-list"),
        {
            "project": project["id"],
            "name": "Buildings and land use",
            "domain": "C",
            "geometry_type": "polygon",
            "schema": [
                {"name": "use", "type": "choice", "choices": ["house", "shop"], "required": True},
                {"name": "storeys", "type": "integer"},
                {"name": "owner", "type": "text"},
            ],
        },
        format="json",
    ).json()
    pegs = planner.post(
        reverse("layer-list"),
        {
            "project": project["id"],
            "name": "Pegs",
            "geometry_type": "point",
            "schema": [{"name": "pid", "type": "text"}],
        },
        format="json",
    ).json()
    return {"id": project["id"], "layer": layer["id"], "pegs": pegs["id"]}


def office_feature(client, layer_id, **properties):
    response = client.post(
        reverse("layer-features", args=[layer_id]),
        {
            "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
            "properties": {"use": "house", **properties},
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def wgs(client, point):
    """The server's own conversion of a native point to WGS 84."""
    response = client.post(
        reverse("crs-transform"),
        {"from_crs": "EPSG:2136", "to_crs": "EPSG:4326", "points": [point]},
        format="json",
    )
    assert response.status_code == 200, response.content
    return response.json()["points"][0]


def push(client, *changes, device=DEVICE):
    response = client.post(
        reverse("sync-push"), {"device_id": device, "changes": list(changes)}, format="json"
    )
    assert response.status_code == 200, response.content
    return response.json()["results"]


def pull(client, project_id, **params):
    response = client.get(reverse("sync-pull"), {"project": project_id, **params})
    assert response.status_code == 200, response.content
    return response.json()


def create_change(layer_id, lonlat, **extra):
    return {
        "change_id": str(uuid.uuid4()),
        "op": "create",
        "layer": layer_id,
        "feature_uuid": str(uuid.uuid4()),
        "geometry": {"type": "Point", "coordinates": lonlat},
        "properties": {"pid": "A1"},
        "capture": {
            "method": "gps",
            "accuracy_m": 3.2,
            "readings": 5,
            "fix_time": "2026-10-06T09:00:00Z",
            "captured_at": "2026-10-06T09:00:05Z",
            "notes": "by the gate",
        },
        **extra,
    }


def update_change(feature, **extra):
    return {
        "change_id": str(uuid.uuid4()),
        "op": "update",
        "feature_uuid": feature["meta"]["uuid"],
        "base_version": feature["meta"]["version"],
        **extra,
    }


# --- Capture offline, sync, appears on the web -------------------------------------------------


def test_a_field_capture_arrives_on_the_web_exactly_once(officer, planner, project):
    """Gate: capture offline -> sync -> the edit appears on the web; a retry
    never creates a duplicate."""
    lonlat = wgs(planner, NATIVE_POINT)
    change = create_change(project["pegs"], lonlat)
    (first,) = push(officer, change)
    assert first["status"] == "applied" and first["feature"]["version"] == 1

    # The reply was lost, so the device sends the same change again.
    (again,) = push(officer, change)
    assert again["repeat"] is True and again["feature"] == first["feature"]
    # Even under a new change id, the same capture isn't added twice.
    (third,) = push(officer, {**change, "change_id": str(uuid.uuid4())})
    assert third["duplicate"] is True and third["feature"]["id"] == first["feature"]["id"]
    assert Feature.objects.filter(layer_id=project["pegs"]).count() == 1

    # On the web: in the layer's CRS, marked as a field capture, with who and how.
    url = reverse("feature-detail", args=[first["feature"]["id"]])
    feature = planner.get(url).json()
    assert feature["meta"]["origin"] == "field"
    x, y = feature["geometry"]["coordinates"]
    assert abs(x - NATIVE_POINT[0]) < 0.001 and abs(y - NATIVE_POINT[1]) < 0.001  # under 1 mm
    captures = planner.get(reverse("sync-captures"), {"feature": first["feature"]["id"]}).json()
    assert captures[0]["method"] == "gps" and captures[0]["accuracy_m"] == 3.2
    assert captures[0]["readings"] == 5 and captures[0]["notes"] == "by the gate"
    assert captures[0]["captured_by"].startswith("field_officer")
    assert AuditLog.objects.filter(table_name="sync_capture").exists()


def test_bad_changes_are_rejected_one_by_one(officer, planner, project):
    lonlat = wgs(planner, NATIVE_POINT)
    good = create_change(project["pegs"], lonlat)
    wrong_field = create_change(project["pegs"], lonlat, properties={"nope": 1})
    wrong_shape = create_change(project["layer"], lonlat, properties={"use": "house"})
    results = push(officer, wrong_field, good, wrong_shape, {"op": "create"}, "nonsense")
    assert [r["status"] for r in results] == [
        "rejected",
        "applied",
        "rejected",
        "rejected",
        "rejected",
    ]
    assert "not a field of this layer" in str(results[0]["errors"])
    assert "polygon layer" in str(results[2]["errors"])
    # A rejected change can be corrected and sent again under the same id.
    (fixed,) = push(officer, {**wrong_field, "properties": {"pid": "B2"}})
    assert fixed["status"] == "applied"


# --- Conflicts ---------------------------------------------------------------------------------


def conflicting_edit(officer, planner, project):
    """The device edits version 1 while the office has moved on to version 2."""
    feature = office_feature(planner, project["layer"], storeys=1, owner="Ama")
    patched = planner.patch(
        reverse("feature-detail", args=[feature["id"]]),
        {"version": 1, "properties": {"storeys": 2}},
        format="json",
    )
    assert patched.status_code == 200
    (result,) = push(
        officer,
        update_change(feature, properties={"use": "shop", "storeys": 3, "owner": "Ama"}),
    )
    return feature, result


def test_an_edit_on_an_older_version_goes_to_the_conflict_queue(officer, planner, project):
    """Gate: the same feature edited on the web and on a device lands in the queue."""
    feature, result = conflicting_edit(officer, planner, project)
    assert result["status"] == "conflict"
    current = planner.get(reverse("feature-detail", args=[feature["id"]])).json()
    assert current["properties"]["storeys"] == 2 and current["properties"]["use"] == "house"

    listed = planner.get(
        reverse("sync-conflict-list"), {"project": project["id"], "status": "open"}
    ).json()
    assert [c["id"] for c in listed] == [result["conflict"]]
    detail = planner.get(reverse("sync-conflict-detail", args=[result["conflict"]])).json()
    assert (detail["base_version"], detail["server_version"]) == (1, 2)
    assert detail["office"]["properties"]["storeys"] == 2
    assert detail["field"]["properties"] == {"use": "shop", "storeys": 3, "owner": "Ama"}
    assert detail["office"]["geometry"]["type"] == "Polygon"

    # An edit on the current version is applied straight away.
    (fine,) = push(officer, update_change(current, properties={"owner": "Kofi"}))
    assert fine["status"] == "applied" and fine["feature"]["version"] == 3


@pytest.mark.parametrize(
    "body,expected,version",
    [
        ({"resolution": "keep_office"}, {"use": "house", "storeys": 2, "owner": "Ama"}, 2),
        ({"resolution": "keep_field"}, {"use": "shop", "storeys": 3, "owner": "Ama"}, 3),
        (
            {"resolution": "merged", "properties": {"use": "shop", "storeys": 2}},
            {"use": "shop", "storeys": 2, "owner": "Ama"},
            3,
        ),
    ],
)
def test_each_way_of_resolving_a_conflict(officer, planner, project, body, expected, version):
    """Gate: keep office, keep field, and merge field by field all work."""
    feature, result = conflicting_edit(officer, planner, project)
    url = reverse("sync-conflict-resolve", args=[result["conflict"]])
    assert officer.post(url, body, format="json").status_code == 403  # officers don't resolve
    response = planner.post(url, body, format="json")
    assert response.status_code == 200, response.content
    assert (
        response.json()["status"] == "resolved"
        and response.json()["resolution"] == body["resolution"]
    )
    current = planner.get(reverse("feature-detail", args=[feature["id"]])).json()
    assert current["properties"] == expected and current["meta"]["version"] == version
    assert planner.post(url, body, format="json").status_code == 400  # already resolved
    assert AuditLog.objects.filter(table_name="sync_conflict", action="UPDATE").exists()


def test_keeping_the_field_shape(officer, planner, project):
    lonlat = wgs(planner, NATIVE_POINT)
    (created,) = push(officer, create_change(project["pegs"], lonlat))
    feature = planner.get(reverse("feature-detail", args=[created["feature"]["id"]])).json()
    planner.patch(
        reverse("feature-detail", args=[feature["id"]]),
        {"version": 1, "properties": {"pid": "office"}},
        format="json",
    )
    moved = wgs(planner, [NATIVE_POINT[0] + 30, NATIVE_POINT[1]])
    (result,) = push(
        officer, update_change(feature, geometry={"type": "Point", "coordinates": moved})
    )
    assert result["status"] == "conflict"
    planner.post(
        reverse("sync-conflict-resolve", args=[result["conflict"]]),
        {"resolution": "merged", "properties": {}, "use_field_geometry": True},
        format="json",
    )
    current = planner.get(reverse("feature-detail", args=[feature["id"]])).json()
    assert abs(current["geometry"]["coordinates"][0] - (NATIVE_POINT[0] + 30)) < 0.001
    assert current["properties"]["pid"] == "office"


# --- Pull ----------------------------------------------------------------------------------------


def test_pull_is_incremental_and_includes_deletions(officer, planner, project):
    kept = office_feature(planner, project["layer"], owner="keep")
    gone = office_feature(planner, project["layer"], owner="gone")
    first = pull(officer, project["id"])
    assert first["full"] is True and len(first["features"]) == 2 and first["deleted"] == []
    lon, lat = first["features"][0]["geometry"]["coordinates"][0][0]
    assert -4 < lon < 2 and 4 < lat < 12  # WGS 84

    # Nothing has changed: the next pull is empty (apart from the look-back window).
    later = "2100-01-01T00:00:00+00:00"
    assert pull(officer, project["id"], since=later)["features"] == []

    since = "2000-01-01T00:00:00+00:00"
    planner.patch(
        reverse("feature-detail", args=[kept["id"]]),
        {"version": 1, "properties": {"owner": "changed"}},
        format="json",
    )
    assert planner.delete(reverse("feature-detail", args=[gone["id"]])).status_code == 204
    second = pull(officer, project["id"], since=since)
    assert second["full"] is False
    assert [f["properties"]["owner"] for f in second["features"]] == ["changed"]
    assert second["deleted"] == [gone["meta"]["uuid"]]
    assert Tombstone.objects.filter(feature_uuid=gone["meta"]["uuid"]).count() == 1

    only_pegs = pull(officer, project["id"], layers=str(project["pegs"]))
    assert only_pegs["features"] == [] and [layer["name"] for layer in only_pegs["layers"]] == [
        "Pegs"
    ]
    assert (
        officer.get(
            reverse("sync-pull"), {"project": project["id"], "since": "yesterday"}
        ).status_code
        == 400
    )


# --- Photos --------------------------------------------------------------------------------------


def start_photo(client, feature_uuid, data, **extra):
    return client.post(
        reverse("sync-photo-list"),
        {
            "uuid": str(uuid.uuid4()),
            "feature_uuid": feature_uuid,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "latitude": 5.6,
            "longitude": -0.2,
            "accuracy_m": 4.0,
            "taken_at": "2026-10-06T09:01:00Z",
            **extra,
        },
        format="json",
    )


def send_chunk(client, photo_uuid, offset, data):
    return client.put(
        reverse("sync-photo-chunk", args=[photo_uuid]) + f"?offset={offset}",
        data,
        content_type="application/octet-stream",
    )


def test_a_photo_upload_resumes_after_a_break_without_damage(officer, planner, project):
    """Gate: cut the connection halfway, resume: no duplicate, no corruption."""
    lonlat = wgs(planner, NATIVE_POINT)
    change = create_change(project["pegs"], lonlat)
    (created,) = push(officer, change)
    data = b"\xff\xd8" + bytes(range(256)) * 40  # 10 242 bytes
    started = start_photo(officer, change["feature_uuid"], data)
    assert started.status_code == 201, started.content
    photo_uuid = started.json()["uuid"]

    assert send_chunk(officer, photo_uuid, 0, data[:4000]).json()["received"] == 4000
    # The connection drops. The device doesn't know whether the chunk arrived,
    # so it asks, then sends the same chunk again by mistake: refused, not doubled.
    assert officer.get(reverse("sync-photo-detail", args=[photo_uuid])).json()["received"] == 4000
    repeated = send_chunk(officer, photo_uuid, 0, data[:4000])
    assert repeated.status_code == 409 and repeated.json()["received"] == 4000
    skipped = send_chunk(officer, photo_uuid, 9000, data[9000:])
    assert skipped.status_code == 409  # a gap is refused too

    # Starting the same upload again returns the one in progress.
    again = officer.post(
        reverse("sync-photo-list"),
        {
            "uuid": photo_uuid,
            "feature_uuid": change["feature_uuid"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        format="json",
    )
    assert again.status_code == 200 and again.json()["received"] == 4000

    done = send_chunk(officer, photo_uuid, 4000, data[4000:])
    assert done.status_code == 200 and done.json()["complete"] is True
    assert Photo.objects.count() == 1

    # On the web: listed for the feature, and byte-for-byte what was taken.
    listed = planner.get(reverse("sync-photo-list"), {"feature": created["feature"]["id"]}).json()
    assert [p["uuid"] for p in listed] == [photo_uuid] and listed[0]["latitude"] == 5.6
    served = planner.get(reverse("sync-photo-file", args=[photo_uuid]))
    assert b"".join(served.streaming_content) == data
    # Chunks after completion change nothing.
    assert send_chunk(officer, photo_uuid, 0, b"junk").json()["complete"] is True


def test_a_damaged_photo_is_refused_and_can_be_sent_again(officer, planner, project):
    lonlat = wgs(planner, NATIVE_POINT)
    change = create_change(project["pegs"], lonlat)
    push(officer, change)
    data = b"\xff\xd8" + b"photo" * 100
    photo_uuid = start_photo(officer, change["feature_uuid"], data).json()["uuid"]
    damaged = send_chunk(officer, photo_uuid, 0, data[:-1] + b"X")
    assert damaged.status_code == 400 and "checksum" in str(damaged.json())
    assert officer.get(reverse("sync-photo-detail", args=[photo_uuid])).json()["received"] == 0
    assert planner.get(reverse("sync-photo-file", args=[photo_uuid])).status_code == 404
    assert send_chunk(officer, photo_uuid, 0, data).json()["complete"] is True


def test_photo_limits(officer, planner, project, monkeypatch):
    lonlat = wgs(planner, NATIVE_POINT)
    change = create_change(project["pegs"], lonlat)
    unknown = start_photo(officer, change["feature_uuid"], b"x" * 10)
    assert unknown.status_code == 400 and "Send the feature first" in str(unknown.json())
    push(officer, change)
    data = b"x" * 100
    photo_uuid = start_photo(officer, change["feature_uuid"], data).json()["uuid"]
    monkeypatch.setattr(photos, "MAX_CHUNK_BYTES", 60)
    assert send_chunk(officer, photo_uuid, 0, data).status_code == 400  # chunk too large
    assert send_chunk(officer, photo_uuid, 0, data[:50]).status_code == 200
    overflow = send_chunk(officer, photo_uuid, 50, data[50:] + b"y")
    assert overflow.status_code == 400 and "More bytes" in str(overflow.json())


# --- Ground-truthing -----------------------------------------------------------------------------


def test_ground_truthing_updates_the_checklist(officer, planner, project):
    """Gate: completing a ground-truthing task updates the checklist."""
    a = office_feature(planner, project["layer"], owner="a")
    b = office_feature(planner, project["layer"], owner="b")
    c = office_feature(planner, project["layer"], owner="c")
    checklist = planner.get(reverse("project-checklist", args=[project["id"]])).json()
    item = next(i for i in checklist["items"] if i["key"] == "buildings")
    assert item["linked_layer"] == project["layer"] and item["metrics"]["verified"] == 0

    url = reverse("checklist-item-send-to-field", args=[item["id"]])
    assert officer.post(url).status_code == 403
    sent = planner.post(url)
    assert sent.status_code == 201 and sent.json()["created"] == 3
    assert planner.post(url).json() == {"created": 0, "already_open": 3, "verified": 0}

    # The device gets the tasks with its pull.
    tasks = {t["feature_uuid"]: t for t in pull(officer, project["id"])["tasks"]}
    assert set(tasks) == {a["meta"]["uuid"], b["meta"]["uuid"], c["meta"]["uuid"]}
    assert tasks[a["meta"]["uuid"]]["item"] == "Buildings and land use"

    def done(feature, outcome, **extra):
        task = {"id": tasks[feature["meta"]["uuid"]]["id"], "outcome": outcome, "notes": "seen"}
        return {"change_id": str(uuid.uuid4()), "op": "task", "task": task, **extra}

    # Confirm one, correct one (the correction is an ordinary edit), one not found.
    confirm = done(a, "confirmed")
    results = push(
        officer,
        confirm,
        update_change(b, properties={"use": "shop"}),
        done(b, "corrected"),
        done(c, "not_found"),
        confirm,  # sent twice: counted once
    )
    assert [r["status"] for r in results] == ["applied"] * 5
    assert results[4]["repeat"] is True

    item = next(
        i
        for i in planner.get(reverse("project-checklist", args=[project["id"]])).json()["items"]
        if i["key"] == "buildings"
    )
    assert item["metrics"]["verified"] == pytest.approx(200 / 3)  # two of three
    summary = planner.get(reverse("sync-tasks"), {"project": project["id"]}).json()
    assert summary["counts"] == {"open": 0, "confirmed": 1, "corrected": 1, "not_found": 1}
    assert Feature.objects.get(pk=c["id"]).verified is False
    corrected = planner.get(reverse("feature-detail", args=[b["id"]])).json()
    assert corrected["properties"]["use"] == "shop" and corrected["meta"]["verified"] is True

    # Verified features come down with the next pull; only the unverified one is sent again.
    assert planner.post(url).json() == {"created": 1, "already_open": 0, "verified": 2}
    assert FieldTask.objects.filter(feature_id=c["id"], status="open").count() == 1


def test_send_to_field_needs_a_layer(planner, project):
    checklist = planner.get(reverse("project-checklist", args=[project["id"]])).json()
    streets = next(i for i in checklist["items"] if i["key"] == "streets")
    response = planner.post(reverse("checklist-item-send-to-field", args=[streets["id"]]))
    assert response.status_code == 400 and "no layer yet" in str(response.json())


# --- Roles and tenancy ---------------------------------------------------------------------------


def test_roles_and_tenancy(
    api, members_a, district_a, district_b, make_member, planner, officer, project
):
    lonlat = wgs(planner, NATIVE_POINT)
    viewer = api(members_a[Role.VIEWER], district_a)
    body = {"device_id": DEVICE, "changes": []}
    assert viewer.post(reverse("sync-push"), body, format="json").status_code == 403
    assert viewer.get(reverse("sync-pull"), {"project": project["id"]}).status_code == 403

    # Another district can't push into this district's layer, or pull its project.
    other = api(make_member(district_b, Role.FIELD_OFFICER, "b.officer@example.test"), district_b)
    (refused,) = push(other, create_change(project["pegs"], lonlat))
    assert refused["status"] == "rejected" and "isn't a layer of this district" in str(
        refused["errors"]
    )
    assert other.get(reverse("sync-pull"), {"project": project["id"]}).status_code == 404

    (mine,) = push(officer, create_change(project["pegs"], lonlat))
    assert mine["status"] == "applied"
    with tenant_context(district_b.id):  # row-level security, not just the view filters
        assert AppliedChange.objects.count() == 0
        assert Conflict.objects.count() == 0 and Photo.objects.count() == 0
    assert push(officer, *[{"x": 1}] * 3)[0]["status"] == "rejected"
    too_many = officer.post(
        reverse("sync-push"), {"device_id": DEVICE, "changes": [{}] * 501}, format="json"
    )
    assert too_many.status_code == 400

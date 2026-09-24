"""Phase 6: editing operations, boundaries and their validation."""

import json
from pathlib import Path

import pytest
from django.urls import reverse
from osgeo import ogr

from core.models import Role
from crs.models import CoordinateSystem
from crs.services import transform_points
from projects.geometry import read_geometries
from projects.models import Feature, PlanProject

ogr.UseExceptions()
pytestmark = pytest.mark.django_db

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
def admin(api, members_a, district_a):
    return api(members_a[Role.DISTRICT_ADMIN], district_a)


def new_project(client, name):
    return client.post(reverse("project-list"), {"name": name}, format="json").json()


def polygon_layer(client, project_id, name="Parcels"):
    return client.post(
        reverse("layer-list"),
        {
            "project": project_id,
            "name": name,
            "geometry_type": "polygon",
            "schema": [{"name": "pid", "type": "text"}],
        },
        format="json",
    ).json()


def add(client, layer_id, coords=SQUARE, **extra):
    return client.post(
        reverse("layer-features", args=[layer_id]),
        {
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"pid": "P"},
            **extra,
        },
        format="json",
    )


def community_geometry(fixtures_dir: Path, code: str) -> dict:
    ds = ogr.Open(str(Path(fixtures_dir) / "generated" / "sample.gpkg"))
    layer = ds.GetLayerByName("communities")
    for feature in layer:
        if feature.GetField("code") == code:
            return json.loads(feature.GetGeometryRef().ExportToJson(["SIGNIFICANT_FIGURES=17"]))
    raise AssertionError(code)


# --- Boundaries --------------------------------------------------------------------------


def test_seeded_overlap_between_community_boundaries_is_reported(planner, fixtures_dir):
    """Gate: the overlap report detects the fixture's 10 m overlap."""
    a = new_project(planner, "Community A plan")
    b = new_project(planner, "Community B plan")
    for project, code in ((a, "SMA-A"), (b, "SMA-B")):
        response = planner.put(
            reverse("project-boundary", args=[project["id"]]),
            {"geometry": community_geometry(fixtures_dir, code), "method": "import"},
            format="json",
        )
        assert response.status_code == 200, response.data
    report = planner.get(reverse("project-boundary", args=[a["id"]])).json()
    [neighbour] = report["neighbours"]
    assert neighbour["kind"] == "overlap" and neighbour["name"] == "Community B plan"
    assert neighbour["area_m2"] == pytest.approx(10 * 2000, rel=0.02)  # 10 m strip, 2 km long
    assert report["valid"] and report["area_ha"] == pytest.approx(1000 * 2000 / 10_000, rel=0.02)
    assert report["native_units"] == "Gold Coast foot" and report["area_native"] > report["area_m2"]


def test_nearby_boundaries_that_dont_touch_are_reported_as_gaps(planner):
    a = new_project(planner, "Left")
    b = new_project(planner, "Right")
    left = [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]
    right = [[103, 0], [200, 0], [200, 100], [103, 100], [103, 0]]  # 3 ft ≈ 0.9 m apart
    for project, coords in ((a, left), (b, right)):
        planner.put(
            reverse("project-boundary", args=[project["id"]]),
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[x + 1190000, y + 337000] for x, y in coords]],
                },
                "method": "drawn",
            },
            format="json",
        )
    [neighbour] = planner.get(reverse("project-boundary", args=[a["id"]])).json()["neighbours"]
    assert neighbour["kind"] == "gap" and 0.8 < neighbour["distance_m"] < 1.0


def test_boundary_status_rules_and_lock(planner, admin):
    project = new_project(planner, "Status plan")
    url = reverse("project-boundary", args=[project["id"]])
    status_url = reverse("project-boundary-status", args=[project["id"]])
    assert (
        planner.post(status_url, {"status": "agreed"}, format="json").status_code == 400
    )  # no boundary yet
    planner.put(
        url,
        {"geometry": {"type": "Polygon", "coordinates": [SQUARE]}, "method": "drawn"},
        format="json",
    )

    assert (
        planner.post(status_url, {"status": "approved"}, format="json").status_code == 400
    )  # must agree first
    assert planner.post(status_url, {"status": "agreed"}, format="json").status_code == 200
    assert planner.post(status_url, {"status": "approved"}, format="json").status_code == 403
    assert admin.post(status_url, {"status": "approved"}, format="json").status_code == 200

    # An approved boundary can't be edited, directly or through the feature.
    assert (
        planner.put(
            url,
            {"geometry": {"type": "Polygon", "coordinates": [SQUARE]}, "method": "drawn"},
            format="json",
        ).status_code
        == 400
    )
    feature_id = PlanProject.objects.get(pk=project["id"]).boundary_feature_id
    patch = planner.patch(
        reverse("feature-detail", args=[feature_id]),
        {"version": 1, "properties": {"name": "x"}},
        format="json",
    )
    assert patch.status_code == 400 and "reopen" in json.dumps(patch.json())
    assert planner.delete(reverse("feature-detail", args=[feature_id])).status_code == 400

    # Only an administrator reopens it.
    assert planner.post(status_url, {"status": "draft"}, format="json").status_code == 403
    assert admin.post(status_url, {"status": "draft"}, format="json").status_code == 200


def test_boundary_outside_the_district_is_measured(planner, api, system_admin, district_a):
    project = new_project(planner, "Edge plan")
    planner.put(
        reverse("project-boundary", args=[project["id"]]),
        {"geometry": {"type": "Polygon", "coordinates": [SQUARE]}, "method": "drawn"},
        format="json",
    )
    assert (
        planner.get(reverse("project-boundary", args=[project["id"]])).json()[
            "district_boundary_loaded"
        ]
        is False
    )
    # District boundary covering only the western half of the square.
    grid, wgs = (
        CoordinateSystem.objects.get(code="EPSG:2136"),
        CoordinateSystem.objects.get(code="EPSG:4326"),
    )
    corners, _ = transform_points(
        [(1190000, 337000), (1190700, 337000), (1190700, 338500), (1190000, 338500)], grid, wgs
    )
    ring = [list(c) for c in corners] + [list(corners[0])]
    response = api(system_admin).put(
        reverse("district-boundary", args=[district_a.id]),
        {"geometry": {"type": "Polygon", "coordinates": [ring]}},
        format="json",
    )
    assert response.status_code == 200, response.data
    report = planner.get(reverse("project-boundary", args=[project["id"]])).json()
    assert report["district_boundary_loaded"] is True
    assert report["outside_district_m2"] == pytest.approx(report["area_m2"] / 2, rel=0.02)


def test_only_system_admins_load_district_boundaries(admin, district_a):
    response = admin.put(
        reverse("district-boundary", args=[district_a.id]), {"geometry": {}}, format="json"
    )
    assert response.status_code == 403


# --- Editing -------------------------------------------------------------------------------


def test_history_and_restore(planner):
    project = new_project(planner, "History plan")
    layer = polygon_layer(planner, project["id"])
    created = add(planner, layer["id"]).json()
    moved = [[x + 50, y] for x, y in SQUARE]
    updated = planner.patch(
        reverse("feature-detail", args=[created["id"]]),
        {
            "version": 1,
            "geometry": {"type": "Polygon", "coordinates": [moved]},
            "properties": {"pid": "Q"},
        },
        format="json",
    ).json()
    history = planner.get(reverse("feature-history", args=[created["id"]])).json()
    original = next(
        h for h in history if h["geometry"] and h["geometry"]["coordinates"] == [SQUARE]
    )
    assert history[0]["geometry"]["coordinates"] == [moved]  # newest first

    restored = planner.post(
        reverse("feature-restore", args=[created["id"]]),
        {"audit_id": original["audit_id"], "version": updated["meta"]["version"]},
        format="json",
    )
    assert restored.status_code == 200, restored.data
    assert restored.json()["geometry"]["coordinates"] == [SQUARE]
    assert (
        restored.json()["meta"]["version"] == updated["meta"]["version"] + 1
    )  # a new version, history kept


def test_split_then_merge_back(planner):
    project = new_project(planner, "Split plan")
    layer = polygon_layer(planner, project["id"])
    created = add(planner, layer["id"]).json()
    blade = {"type": "LineString", "coordinates": [[1190700.0, 337600.0], [1190700.0, 338000.0]]}
    split = planner.post(
        reverse("feature-split", args=[created["id"]]),
        {"blade": blade, "version": 1},
        format="json",
    )
    assert split.status_code == 200, split.data
    pieces = split.json()["features"]
    assert len(pieces) == 2 and {p["properties"]["pid"] for p in pieces} == {"P"}

    ids = [p["id"] for p in pieces]
    merged = planner.post(
        reverse("feature-merge"), {"feature_ids": ids, "keep": ids[0]}, format="json"
    )
    assert merged.status_code == 200, merged.data
    assert Feature.objects.filter(layer_id=layer["id"]).count() == 1
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT ST_Area(geom_native) FROM projects_feature WHERE id = %s", [ids[0]])
        assert cursor.fetchone()[0] == pytest.approx(200 * 200)


def test_features_that_dont_touch_arent_merged(planner):
    project = new_project(planner, "Merge plan")
    layer = polygon_layer(planner, project["id"])
    a = add(planner, layer["id"]).json()
    b = add(planner, layer["id"], [[x + 1000, y] for x, y in SQUARE]).json()
    response = planner.post(
        reverse("feature-merge"),
        {"feature_ids": [a["id"], b["id"]], "keep": a["id"]},
        format="json",
    )
    assert response.status_code == 400 and "don't touch" in json.dumps(response.json())


def test_geometry_drawn_on_the_map_is_converted_explicitly(planner):
    project = new_project(planner, "Map plan")
    layer = polygon_layer(planner, project["id"])
    grid, merc = (
        CoordinateSystem.objects.get(code="EPSG:2136"),
        CoordinateSystem.objects.get(code="EPSG:3857"),
    )
    in_3857, _ = transform_points([tuple(p) for p in SQUARE], grid, merc)
    created = add(planner, layer["id"], [list(p) for p in in_3857], geometry_crs="EPSG:3857")
    assert created.status_code == 201, created.data
    native = read_geometries([created.json()["id"]], native=True)[created.json()["id"]]
    for got, want in zip(native["coordinates"][0], SQUARE, strict=True):
        assert got == pytest.approx(want, abs=1e-6)  # feet


def test_traverse_endpoint(planner):
    response = planner.post(
        reverse("traverse"),
        {
            "start": [1190600, 337700],
            "legs": [
                {"bearing": "N 0 E", "distance": 200},
                {"bearing": "90", "distance": 200},
                {"bearing": "S 0 E", "distance": 200},
                {"bearing": "270 00 00", "distance": 200.2},
            ],
            "adjust": True,
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    body = response.json()
    assert body["misclosure"] == pytest.approx(0.2)
    assert body["accuracy_ratio"] == pytest.approx(800.2 / 0.2)
    ring = body["polygon"]["coordinates"][0]
    assert ring[0] == ring[-1] == [1190600, 337700]


def test_viewers_cannot_edit(api, members_a, district_a, planner):
    project = new_project(planner, "Viewer plan")
    layer = polygon_layer(planner, project["id"])
    feature = add(planner, layer["id"]).json()
    viewer = api(members_a[Role.VIEWER], district_a)
    assert (
        viewer.post(
            reverse("feature-merge"),
            {"feature_ids": [feature["id"], feature["id"]], "keep": feature["id"]},
            format="json",
        ).status_code
        == 403
    )
    assert viewer.get(reverse("feature-history", args=[feature["id"]])).status_code == 200

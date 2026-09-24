"""Phase 3: projects, layers, features, tiles."""

import json
import time

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection
from django.urls import reverse

from core.models import Role
from core.tenancy import tenant_context
from crs.models import CoordinateSystem, DistrictCrsSettings, SystemCrsSettings, UserCrsPreference
from crs.services import transform_points
from projects import schema as schema_rules
from projects import styles
from projects.geometry import read_geometries
from projects.models import Feature, Layer, PlanProject

pytestmark = pytest.mark.django_db

# Coordinates with more digits than a surveyor would type, to prove nothing is
# rounded: Ghana National Grid feet, around Accra.
SQUARE_FT = [
    [1190631.4519123456, 337708.94461234567],
    [1190731.4519123456, 337708.94461234567],
    [1190731.4519123456, 337808.94461234567],
    [1190631.4519123456, 337808.94461234567],
    [1190631.4519123456, 337708.94461234567],
]
SCHEMA = [
    {"name": "parcel_id", "type": "text", "required": True},
    {"name": "floors", "type": "integer"},
    {
        "name": "use",
        "type": "choice",
        "choices": ["residential", "commercial"],
        "default": "residential",
    },
]


def crs(code: str) -> CoordinateSystem:
    return CoordinateSystem.objects.get(code=code)


@pytest.fixture
def planner(members_a):
    return members_a[Role.PLANNER]


@pytest.fixture
def client_a(api, planner, district_a):
    return api(planner, district_a)


@pytest.fixture
def project(client_a):
    response = client_a.post(reverse("project-list"), {"name": "Kasoa local plan"}, format="json")
    assert response.status_code == 201, response.data
    return PlanProject.objects.get(pk=response.json()["id"])


@pytest.fixture
def layer(client_a, project):
    response = client_a.post(
        reverse("layer-list"),
        {
            "project": project.id,
            "name": "Parcels",
            "domain": "B",
            "geometry_type": "polygon",
            "schema": SCHEMA,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return Layer.objects.get(pk=response.json()["id"])


def add_feature(client, layer, coords=SQUARE_FT, **props):
    return client.post(
        reverse("layer-features", args=[layer.id]),
        {
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"parcel_id": "P-1", **props},
        },
        format="json",
    )


# --- Projects and the CRS gate carried over from Phase 2 ------------------------------


def test_new_project_uses_the_resolved_default_crs(client_a, district_a):
    DistrictCrsSettings.objects.create(district=district_a, default_crs=crs("EPSG:25000"))
    response = client_a.post(reverse("project-list"), {"name": "P"}, format="json")
    assert response.json()["crs_detail"]["code"] == "EPSG:25000"


def test_changing_defaults_never_changes_an_existing_project_or_its_coordinates(
    client_a, layer, planner, district_a, system_admin, api
):
    feature_id = add_feature(client_a, layer).json()["id"]
    project = layer.project
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsEWKB(geom_native) FROM projects_feature WHERE id = %s", [feature_id]
        )
        before = bytes(cursor.fetchone()[0])

    SystemCrsSettings.objects.filter(pk=1).update(default_crs=crs("EPSG:32630"))
    DistrictCrsSettings.objects.create(district=district_a, default_crs=crs("EPSG:25000"))
    UserCrsPreference.objects.create(user=planner, preferred_crs=crs("EPSG:4326"))

    project.refresh_from_db()
    layer.refresh_from_db()
    assert project.crs.code == layer.crs.code == "EPSG:2136"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsEWKB(geom_native) FROM projects_feature WHERE id = %s", [feature_id]
        )
        assert bytes(cursor.fetchone()[0]) == before  # byte-identical


def test_project_crs_is_fixed(client_a, project):
    url = reverse("project-detail", args=[project.id])
    response = client_a.patch(url, {"crs": crs("EPSG:4326").id}, format="json")
    assert response.status_code == 400


def test_deleting_a_project_archives_it(client_a, project):
    assert client_a.delete(reverse("project-detail", args=[project.id])).status_code == 204
    project.refresh_from_db()
    assert project.status == "archived"
    assert project.id not in [
        p["id"] for p in client_a.get(reverse("project-list")).json()["results"]
    ]


# --- Native coordinates are stored exactly -------------------------------------------------


def test_native_coordinates_round_trip_exactly(client_a, layer):
    response = add_feature(client_a, layer)
    assert response.status_code == 201, response.data
    assert response.json()["geometry"]["coordinates"] == [SQUARE_FT]
    fetched = client_a.get(reverse("feature-detail", args=[response.json()["id"]])).json()
    assert fetched["geometry"]["coordinates"] == [SQUARE_FT]  # every digit


def test_wgs84_copy_uses_the_platform_operation(client_a, layer):
    feature_id = add_feature(client_a, layer).json()["id"]
    wgs = read_geometries([feature_id], native=False)[feature_id]
    expected, _ = transform_points(SQUARE_FT, crs("EPSG:2136"), crs("EPSG:4326"))
    for got, want in zip(wgs["coordinates"][0], expected, strict=True):
        assert got == pytest.approx(list(want), abs=1e-12)


def test_database_refuses_a_geometry_in_the_wrong_crs(layer, district_a):
    feature = Feature.objects.create(district=district_a, layer=layer, properties={})
    with pytest.raises(DatabaseError, match="does not match its layer"):
        with tenant_context(district_a.id), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE projects_feature"
                " SET geom_native = ST_SetSRID(ST_MakePoint(0, 0), 4326) WHERE id = %s",
                [feature.id],
            )


def test_layer_crs_is_locked_once_it_has_features(client_a, layer):
    add_feature(client_a, layer)
    url = reverse("layer-detail", args=[layer.id])
    assert client_a.patch(url, {"crs": crs("EPSG:25000").id}, format="json").status_code == 400
    with pytest.raises(DatabaseError, match="cannot change once it has features"):
        with tenant_context(layer.district_id):
            Layer.objects.filter(pk=layer.pk).update(crs=crs("EPSG:25000"))


@pytest.mark.parametrize(
    "geometry,message",
    [
        ({"type": "Point", "coordinates": [1, 2]}, "polygon layer"),
        (
            {"type": "Polygon", "coordinates": [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]]},
            "invalid",
        ),
        ({"type": "Polygon"}, "GeoJSON geometry"),
        ({"type": "Polygon", "coordinates": "nope"}, "malformed"),
    ],
)
def test_bad_geometries_are_rejected_with_a_reason(client_a, layer, geometry, message):
    response = client_a.post(
        reverse("layer-features", args=[layer.id]),
        {"geometry": geometry, "properties": {"parcel_id": "P"}},
        format="json",
    )
    assert response.status_code == 400
    assert message in json.dumps(response.json())


# --- Properties and schema --------------------------------------------------------------


def test_properties_are_validated_and_defaults_filled(client_a, layer):
    ok = add_feature(client_a, layer, floors=2)
    assert ok.json()["properties"] == {"parcel_id": "P-1", "floors": 2, "use": "residential"}
    bad = add_feature(client_a, layer, floors="two", colour="red")
    assert bad.status_code == 400
    assert set(bad.json()) == {"floors", "colour"}


def test_schema_rules():
    with pytest.raises(ValidationError):
        schema_rules.validate_schema([{"name": "Bad Name", "type": "text"}])
    with pytest.raises(ValidationError):
        schema_rules.validate_schema([{"name": "a", "type": "text"}, {"name": "a", "type": "text"}])
    with pytest.raises(ValidationError):
        schema_rules.validate_schema([{"name": "c", "type": "choice", "choices": []}])
    with pytest.raises(ValidationError):
        schema_rules.validate_schema([{"name": "d", "type": "date", "default": "31/12/2026"}])
    cleaned = schema_rules.validate_properties(
        schema_rules.validate_schema(
            [{"name": "d", "type": "date"}, {"name": "x", "type": "decimal"}]
        ),
        {"d": "2026-09-24", "x": "12.5"},
    )
    assert cleaned == {"d": "2026-09-24", "x": 12.5}


def test_schema_change_that_would_break_values_is_refused(client_a, layer):
    add_feature(client_a, layer, floors=3)
    url = reverse("layer-detail", args=[layer.id])
    as_choice = [
        f if f["name"] != "floors" else {"name": "floors", "type": "choice", "choices": ["1", "2"]}
        for f in SCHEMA
    ]
    response = client_a.patch(url, {"schema": as_choice}, format="json")
    assert response.status_code == 400 and "don't fit" in json.dumps(response.json())


def test_removing_a_field_with_values_needs_confirmation(client_a, layer):
    feature_id = add_feature(client_a, layer, floors=3).json()["id"]
    url = reverse("layer-detail", args=[layer.id])
    without_floors = [f for f in SCHEMA if f["name"] != "floors"]
    refused = client_a.patch(url, {"schema": without_floors}, format="json")
    assert refused.status_code == 400 and "confirm_drop=floors" in json.dumps(refused.json())
    ok = client_a.patch(f"{url}?confirm_drop=floors", {"schema": without_floors}, format="json")
    assert ok.status_code == 200
    assert "floors" not in Feature.objects.get(pk=feature_id).properties


def test_style_rules():
    assert styles.validate_style({}, [])["kind"] == "single"
    with pytest.raises(ValidationError):
        styles.validate_style({"kind": "single", "fill": "green"}, [])
    with pytest.raises(ValidationError):
        styles.validate_style({"kind": "categorized", "field": "missing", "categories": []}, [])
    ok = styles.validate_style(
        {
            "kind": "categorized",
            "field": "use",
            "categories": [{"value": "residential", "fill": "#f4d35e"}],
        },
        schema_rules.validate_schema(SCHEMA),
    )
    assert ok["categories"][0]["fill"] == "#f4d35e"


# --- Editing ----------------------------------------------------------------------------


def test_stale_edit_gets_a_conflict(client_a, layer):
    created = add_feature(client_a, layer).json()
    url = reverse("feature-detail", args=[created["id"]])
    first = client_a.patch(url, {"version": 1, "properties": {"floors": 2}}, format="json")
    assert first.status_code == 200 and first.json()["meta"]["version"] == 2
    stale = client_a.patch(url, {"version": 1, "properties": {"floors": 5}}, format="json")
    assert stale.status_code == 409
    assert stale.json()["current"]["properties"]["floors"] == 2


def test_edits_are_audited_with_geometry_history(client_a, layer):
    from core.models import AuditLog

    feature_id = add_feature(client_a, layer).json()["id"]
    moved = [[x + 10, y] for x, y in SQUARE_FT]
    client_a.patch(
        reverse("feature-detail", args=[feature_id]),
        {"version": 1, "geometry": {"type": "Polygon", "coordinates": [moved]}},
        format="json",
    )
    entries = AuditLog.objects.filter(table_name="projects_feature", row_id=str(feature_id))
    assert any(e.before and e.before.get("geom_native") for e in entries)
    assert all("geom_4326" not in (e.after or {}) for e in entries)


def test_layer_order(client_a, project):
    ids = []
    for name in ("A", "B", "C"):
        ids.append(
            client_a.post(
                reverse("layer-list"),
                {"project": project.id, "name": name, "geometry_type": "point"},
                format="json",
            ).json()["id"]
        )
    new_order = [ids[0], ids[2], ids[1]]
    assert (
        client_a.post(
            reverse("project-layer-order", args=[project.id]),
            {"layer_ids": new_order},
            format="json",
        ).status_code
        == 204
    )
    listed = client_a.get(reverse("layer-list"), {"project": project.id}).json()
    assert [layer["id"] for layer in listed] == new_order
    assert (
        client_a.post(
            reverse("project-layer-order", args=[project.id]), {"layer_ids": ids[:2]}, format="json"
        ).status_code
        == 400
    )


# --- Tiles ------------------------------------------------------------------------------


def tile_for(lon: float, lat: float, z: int) -> tuple[int, int, int]:
    import math

    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return z, x, y


def test_tile_contains_the_feature_and_is_cacheable(client_a, layer):
    feature_id = add_feature(client_a, layer).json()["id"]
    wgs = read_geometries([feature_id], native=False)[feature_id]
    lon, lat = wgs["coordinates"][0][0]
    z, x, y = tile_for(lon, lat, 16)
    url = reverse("layer-tile", args=[layer.id, z, x, y])
    response = client_a.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/vnd.mapbox-vector-tile"
    assert len(response.content) > 20
    assert client_a.get(url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code == 304
    far = reverse("layer-tile", args=[layer.id, 16, 0, 0])
    assert client_a.get(far).status_code == 204


def test_tiles_follow_district_isolation(api, layer, district_b, make_member):
    other = api(make_member(district_b, Role.DISTRICT_ADMIN), district_b)
    assert other.get(reverse("layer-tile", args=[layer.id, 0, 0, 0])).status_code == 403
    assert other.get(reverse("layer-features", args=[layer.id])).status_code == 404


# --- Permissions ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,can_edit",
    [
        (Role.DISTRICT_ADMIN, True),
        (Role.PLANNER, True),
        (Role.FIELD_OFFICER, False),
        (Role.VIEWER, False),
    ],
)
def test_roles(api, members_a, district_a, layer, role, can_edit):
    client = api(members_a[role], district_a)
    assert client.get(reverse("project-list")).status_code == 200
    assert client.get(reverse("layer-features", args=[layer.id])).status_code == 200
    created = add_feature(client, layer)
    assert created.status_code == (201 if can_edit else 403)
    new_layer = client.post(
        reverse("layer-list"),
        {"project": layer.project_id, "name": f"L-{role}", "geometry_type": "point"},
        format="json",
    )
    assert new_layer.status_code == (201 if can_edit else 403)


# --- Performance (gate: a 100k-feature layer pans smoothly) -----------------------------------


@pytest.mark.slow
def test_tiles_for_a_100k_feature_layer_are_fast(client_a, layer, district_a):
    """Loads 100,000 building-sized polygons around Accra, then times tiles.

    Gate: tiles at street zooms (14-17), where planners work with parcels and
    buildings, come back in under 500 ms. At zoom 12 one tile covers the whole
    area (all 100k buildings); its time is reported but not gated: the map
    shouldn't draw individual buildings that far out (min zoom, Phase 3 web)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO projects_feature
                (district_id, layer_id, uuid, properties, version, origin, verified,
                 created_at, updated_at, geom_native, geom_4326)
            SELECT %(district)s, %(layer)s, gen_random_uuid(),
                   jsonb_build_object('parcel_id', 'P-' || i),
                   1, 'import', false, now(), now(),
                   ST_SetSRID(ST_MakeEnvelope(x, y, x + 40, y + 40), 2136),
                   ST_Transform(ST_SetSRID(ST_MakeEnvelope(x, y, x + 40, y + 40), 2136), 4326)
            FROM (SELECT i, 1180000 + (i %% 316) * 60 AS x, 330000 + (i / 316) * 60 AS y
                  FROM generate_series(1, 100000) AS i) g
            """,
            {"district": district_a.id, "layer": layer.id},
        )
        cursor.execute("ANALYZE projects_feature")
    centre = (-0.2, 5.6)
    timings = {}
    for z in (12, 14, 15, 16, 17):
        z_, x, y = tile_for(*centre, z)
        start = time.perf_counter()
        response = client_a.get(reverse("layer-tile", args=[layer.id, z_, x, y]))
        timings[z] = round(time.perf_counter() - start, 3)
        assert response.status_code in (200, 204)
    print("tile timings (s):", timings)
    assert max(t for z, t in timings.items() if z >= 14) < 0.5, timings

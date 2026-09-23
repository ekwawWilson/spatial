"""Phase 2 exit gate: CRS registry, defaults, transformations."""

import csv
import math

import pytest
from django.conf import settings
from django.db import connection
from django.urls import reverse
from pyproj import CRS, Transformer

from core.models import Role
from core.tenancy import tenant_context
from crs import services
from crs.models import (
    CoordinateSystem,
    DistrictCrsSettings,
    PreferredTransformation,
    SystemCrsSettings,
    UserCrsPreference,
)
from crs.services import register_custom, resolve_default, transform_points

pytestmark = pytest.mark.django_db

# A 5 x 5 grid over Ghana (lon -3.2..1.2, lat 4.8..11.1), in WGS 84.
GHANA_LONLAT = [(-3.2 + 1.1 * i, 4.8 + 1.575 * j) for i in range(5) for j in range(5)]


def system(code: str) -> CoordinateSystem:
    return CoordinateSystem.objects.get(code=code)


def points_in(code: str) -> list[tuple[float, float]]:
    to = Transformer.from_crs("EPSG:4326", code, always_xy=True)
    return [to.transform(lon, lat) for lon, lat in GHANA_LONLAT]


def metres(system_: CoordinateSystem, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance between two positions of the same system, in metres."""
    if system_.unit_to_metre:
        return math.dist(a, b) * system_.unit_to_metre
    # Degrees: small-distance approximation, fine for millimetre checks.
    dlon = (a[0] - b[0]) * 111_320 * math.cos(math.radians(a[1]))
    dlat = (a[1] - b[1]) * 110_574
    return math.hypot(dlon, dlat)


# --- Registry -------------------------------------------------------------------


def test_builtins_are_seeded_with_ghana_systems():
    codes = set(CoordinateSystem.objects.filter(is_builtin=True).values_list("code", flat=True))
    assert {"EPSG:2136", "EPSG:25000", "EPSG:2137", "EPSG:4168", "EPSG:4326", "EPSG:32630"} <= codes
    ngg = system("EPSG:2136")
    assert ngg.units == "Gold Coast foot"
    assert ngg.unit_to_metre == pytest.approx(0.3047997101815088)
    assert "Ghana" in ngg.area_of_use


def test_initial_system_default_comes_from_settings():
    assert SystemCrsSettings.objects.get(pk=1).default_crs.code == settings.INITIAL_DEFAULT_CRS


def test_every_builtin_is_known_to_postgis_by_its_srid():
    for crs in CoordinateSystem.objects.filter(is_builtin=True):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", [crs.srid])
            assert cursor.fetchone(), crs.code


# --- Round trips (gate: A -> B -> A differs by < 1 mm) ------------------------------------

PAIRS = [
    ("EPSG:2136", "EPSG:4326"),
    ("EPSG:2136", "EPSG:32630"),
    ("EPSG:2136", "EPSG:25000"),
    ("EPSG:25000", "EPSG:4326"),
    ("EPSG:4168", "EPSG:4326"),
    ("EPSG:32630", "EPSG:3857"),
]


@pytest.mark.parametrize("a,b", PAIRS + [(b, a) for a, b in PAIRS])
def test_round_trip_is_within_a_millimetre(a, b):
    src, dst = system(a), system(b)
    start = points_in(a)
    there, _ = transform_points(start, src, dst)
    back, _ = transform_points(there, dst, src)
    worst = max(metres(src, p, q) for p, q in zip(start, back, strict=True))
    assert worst < 0.001, f"{a} -> {b} -> {a}: {worst * 1000:.4f} mm"


def test_round_trip_with_a_pinned_operation(system_admin):
    src, dst = system("EPSG:2136"), system("EPSG:4326")
    # Pin the *second* candidate, to prove the pin (not PROJ's ranking) is used.
    candidates = services.candidate_operations(src, dst)
    assert len(candidates) >= 2
    PreferredTransformation.objects.create(
        source=src,
        target=dst,
        name=candidates[1].name,
        pipeline=candidates[1].pipeline,
        accuracy_m=candidates[1].accuracy_m,
    )
    start = points_in("EPSG:2136")
    there, op = transform_points(start, src, dst)
    assert op.pinned and op.name == candidates[1].name
    back, reverse_op = transform_points(there, dst, src)
    assert reverse_op.name == candidates[1].name
    assert max(metres(src, p, q) for p, q in zip(start, back, strict=True)) < 0.001


def test_datum_shift_reports_its_accuracy():
    _, op = transform_points([(900000.0, 1900000.0)], system("EPSG:2136"), system("EPSG:4326"))
    assert op.accuracy_m is not None and op.accuracy_m >= 1  # metres, not millimetres
    assert "Accra to WGS 84" in op.name


def test_same_system_is_a_no_op():
    pts = [(900000.0, 1900000.0)]
    out, op = transform_points(pts, system("EPSG:2136"), system("EPSG:2136"))
    assert out == pts and op.accuracy_m == 0.0


def test_direction_does_not_change_the_operation():
    a, b = system("EPSG:2136"), system("EPSG:4326")
    assert services.describe_operation(a, b) == services.describe_operation(b, a)


# --- Official control points (gate) -----------------------------------------------


def test_against_official_control_points(fixtures_dir):
    with open(fixtures_dir / "source" / "control_points.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        pytest.skip("Official control points not provided yet (see fixtures/README.md)")
    grid, wgs = system("EPSG:2136"), system("EPSG:4326")
    points = [(float(r["easting_ft_2136"]), float(r["northing_ft_2136"])) for r in rows]
    computed, op = transform_points(points, grid, wgs)
    for row, got in zip(rows, computed, strict=True):
        expected = (float(row["lon_wgs84"]), float(row["lat_wgs84"]))
        tolerance = (op.accuracy_m or 0) + float(row["accuracy_m"] or 0)
        error = metres(wgs, got, expected)
        assert error <= tolerance, f"{row['point_id']}: {error:.2f} m > {tolerance:.2f} m"


# --- Defaults -----------------------------------------------------------------------


def test_default_resolution_order(make_user, district_a):
    user = make_user("kofi@example.test")
    assert resolve_default(user, district_a.id).source == "system"
    DistrictCrsSettings.objects.create(district=district_a, default_crs=system("EPSG:25000"))
    resolved = resolve_default(user, district_a.id)
    assert (resolved.source, resolved.crs.code) == ("district", "EPSG:25000")
    UserCrsPreference.objects.create(user=user, preferred_crs=system("EPSG:32630"))
    resolved = resolve_default(user, district_a.id)
    assert (resolved.source, resolved.crs.code) == ("user", "EPSG:32630")


def test_changing_a_default_touches_nothing_but_the_setting(api, system_admin):
    before = list(CoordinateSystem.objects.order_by("id").values())
    response = api(system_admin).put(
        reverse("crs-default-system"), {"crs": system("EPSG:25000").id}, format="json"
    )
    assert response.status_code == 204
    assert SystemCrsSettings.objects.get(pk=1).default_crs.code == "EPSG:25000"
    assert list(CoordinateSystem.objects.order_by("id").values()) == before


# --- Custom systems ------------------------------------------------------------------

# A local transverse Mercator on the Accra datum, as a surveyor might define it.
LOCAL_TM = (
    "+proj=tmerc +lat_0=5.5 +lon_0=-0.2 +k=1 +x_0=50000 +y_0=50000 "
    "+a=6378300 +rf=296 +towgs84=-170,33,326,0,0,0,0 +units=m +no_defs"
)


def test_custom_system_is_usable_in_postgis(system_admin, district_a):
    with tenant_context(district_a.id, user_id=system_admin.id, is_system_admin=True):
        custom = register_custom(
            name="Local TM", definition=LOCAL_TM, district=None, user=system_admin
        )
    assert custom.code == f"CUSTOM:{custom.srid}" and custom.srid >= 910000
    lon, lat = -0.21, 5.56
    expected, _ = transform_points([(lon, lat)], system("EPSG:4326"), custom)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_X(g), ST_Y(g)"
            " FROM ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s) g",
            [lon, lat, custom.srid],
        )
        got = cursor.fetchone()
    # PostGIS and pyproj may pick different datum shifts for a custom system; the
    # +towgs84 above pins it, so they must agree closely.
    assert math.dist(got, expected[0]) < 0.01


@pytest.mark.parametrize(
    "definition,message",
    [
        ("not a crs", "Not a valid coordinate reference system"),
        ("EPSG:2136", "EPSG:2136"),  # already an EPSG system
        ("", "blank"),
    ],
)
def test_invalid_custom_definitions_are_rejected(api, members_a, district_a, definition, message):
    client = api(members_a[Role.DISTRICT_ADMIN], district_a)
    response = client.post(reverse("crs-system-list"), {"definition": definition}, format="json")
    assert response.status_code == 400
    assert message.lower() in str(response.json()).lower()


def test_district_custom_system_is_private_to_the_district(
    api, members_a, district_a, district_b, make_member
):
    admin_a = members_a[Role.DISTRICT_ADMIN]
    created = api(admin_a, district_a).post(
        reverse("crs-system-list"), {"definition": LOCAL_TM, "name": "A local grid"}, format="json"
    )
    assert created.status_code == 201, created.data
    code = created.json()["code"]
    assert created.json()["scope"] == "district"

    listed_a = api(members_a[Role.VIEWER], district_a).get(reverse("crs-system-list")).json()
    assert code in {s["code"] for s in listed_a}

    admin_b = make_member(district_b, Role.DISTRICT_ADMIN)
    listed_b = api(admin_b, district_b).get(reverse("crs-system-list")).json()
    assert code not in {s["code"] for s in listed_b}
    transform = api(admin_b, district_b).post(
        reverse("crs-transform"),
        {"from_crs": code, "to_crs": "EPSG:4326", "points": [[50000, 50000]]},
        format="json",
    )
    assert transform.status_code == 400  # unknown in district B


def test_only_district_admins_add_district_systems(api, members_a, district_a):
    for role in (Role.PLANNER, Role.FIELD_OFFICER, Role.VIEWER):
        response = api(members_a[role], district_a).post(
            reverse("crs-system-list"), {"definition": LOCAL_TM}, format="json"
        )
        assert response.status_code == 403, role


def test_only_system_admins_add_global_systems(api, members_a, district_a, system_admin):
    body = {"definition": LOCAL_TM, "scope": "global"}
    admin = api(members_a[Role.DISTRICT_ADMIN], district_a)
    assert admin.post(reverse("crs-system-list"), body, format="json").status_code == 403
    response = api(system_admin).post(reverse("crs-system-list"), body, format="json")
    assert response.status_code == 201 and response.json()["scope"] == "global"


def test_validate_previews_without_saving(api, members_a, district_a):
    count = CoordinateSystem.objects.count()
    response = api(members_a[Role.VIEWER], district_a).post(
        reverse("crs-validate"), {"definition": "EPSG:2136"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["epsg"] == 2136 and response.json()["units"] == "Gold Coast foot"
    assert CoordinateSystem.objects.count() == count


def test_builtins_can_only_be_changed_by_system_admins(api, members_a, district_a):
    url = reverse("crs-system-detail", args=[system("EPSG:3857").id])
    response = api(members_a[Role.DISTRICT_ADMIN], district_a).patch(
        url, {"is_active": False}, format="json"
    )
    assert response.status_code == 403


def test_system_default_cannot_be_deactivated(api, system_admin):
    url = reverse("crs-system-detail", args=[services.system_default().id])
    assert api(system_admin).patch(url, {"is_active": False}, format="json").status_code == 400


# --- Defaults API -----------------------------------------------------------------------


def test_defaults_api_by_role(api, members_a, district_a, system_admin):
    viewer = api(members_a[Role.VIEWER], district_a)
    admin = api(members_a[Role.DISTRICT_ADMIN], district_a)
    utm = {"crs": system("EPSG:32630").id}
    metre_grid = {"crs": system("EPSG:25000").id}

    assert viewer.put(reverse("crs-default-me"), utm, format="json").status_code == 204
    assert viewer.put(reverse("crs-default-district"), metre_grid, format="json").status_code == 403
    assert admin.put(reverse("crs-default-district"), metre_grid, format="json").status_code == 204
    assert admin.put(reverse("crs-default-system"), metre_grid, format="json").status_code == 403

    viewer_view = viewer.get(reverse("crs-defaults")).json()
    assert viewer_view["effective"]["source"] == "user"
    assert viewer_view["district"]["code"] == "EPSG:25000"
    admin_view = admin.get(reverse("crs-defaults")).json()
    assert admin_view["effective"] == {"crs": admin_view["district"], "source": "district"}

    assert viewer.put(reverse("crs-default-me"), {"crs": None}, format="json").status_code == 204
    assert viewer.get(reverse("crs-defaults")).json()["effective"]["source"] == "district"


# --- Transform and operations API --------------------------------------------------------


def test_transform_points_api_reports_the_operation(api, members_a, district_a):
    response = api(members_a[Role.VIEWER], district_a).post(
        reverse("crs-transform"),
        {"from_crs": "EPSG:2136", "to_crs": "EPSG:4326", "points": [[900000, 1900000]]},
        format="json",
    )
    assert response.status_code == 200, response.data
    body = response.json()
    lon, lat = body["points"][0]
    assert -1.1 < lon < -0.9 and 9 < lat < 10  # central Ghana
    assert body["operation"]["accuracy_m"] >= 1


def test_transform_geometry_api(api, members_a, district_a):
    ring = [[-0.2, 5.6], [-0.19, 5.6], [-0.19, 5.61], [-0.2, 5.6]]
    response = api(members_a[Role.VIEWER], district_a).post(
        reverse("crs-transform"),
        {
            "from_crs": "EPSG:4326",
            "to_crs": "EPSG:32630",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    out = response.json()["geometry"]
    assert out["type"] == "Polygon" and len(out["coordinates"][0]) == 4
    assert out["coordinates"][0][0] == out["coordinates"][0][-1]  # ring stays closed


@pytest.mark.parametrize(
    "body",
    [
        {"from_crs": "EPSG:9999999", "to_crs": "EPSG:4326", "points": [[0, 0]]},
        {"from_crs": "EPSG:4326", "to_crs": "EPSG:2136"},
        {
            "from_crs": "EPSG:4326",
            "to_crs": "EPSG:2136",
            "points": [[0, 0]],
            "geometry": {"type": "Point", "coordinates": [0, 0]},
        },
    ],
)
def test_transform_api_rejects_bad_requests(api, members_a, district_a, body):
    client = api(members_a[Role.VIEWER], district_a)
    assert client.post(reverse("crs-transform"), body, format="json").status_code == 400


def test_operations_api_lists_candidates_and_pins(api, members_a, district_a, system_admin):
    params = {"from_crs": "EPSG:2136", "to_crs": "EPSG:4326"}
    listing = api(members_a[Role.VIEWER], district_a).get(reverse("crs-operations"), params).json()
    assert len(listing["candidates"]) >= 2
    assert listing["current"]["pinned"] is False
    choice = listing["candidates"][-1]

    pin = {**params, "pipeline": choice["pipeline"]}
    assert (
        api(members_a[Role.DISTRICT_ADMIN], district_a)
        .put(reverse("crs-operations"), pin, format="json")
        .status_code
        == 403
    )
    assert api(system_admin).put(reverse("crs-operations"), pin, format="json").status_code == 204

    # The pin applies in both directions.
    reverse_params = {"from_crs": "EPSG:4326", "to_crs": "EPSG:2136"}
    current = (
        api(members_a[Role.VIEWER], district_a)
        .get(reverse("crs-operations"), reverse_params)
        .json()["current"]
    )
    assert current["pinned"] is True and current["name"] == choice["name"]

    bad = {**params, "pipeline": "+proj=nonsense"}
    assert api(system_admin).put(reverse("crs-operations"), bad, format="json").status_code == 400

    assert (
        api(system_admin)
        .delete(f"{reverse('crs-operations')}?from_crs=EPSG:4326&to_crs=EPSG:2136")
        .status_code
        == 204
    )
    assert not PreferredTransformation.objects.exists()


def test_crs_changes_are_audited(api, system_admin):
    from core.models import AuditLog

    api(system_admin).put(
        reverse("crs-default-system"), {"crs": system("EPSG:25000").id}, format="json"
    )
    entry = AuditLog.objects.filter(table_name="crs_systemcrssettings", action="UPDATE").latest(
        "id"
    )
    assert entry.user_id == system_admin.id


@pytest.mark.parametrize(
    "code", ["EPSG:2136", "EPSG:25000", "EPSG:4168", "EPSG:2137", "EPSG:32630"]
)
def test_web_proj4_puts_data_where_the_server_does(code):
    """The web map (proj4js) must agree with server transforms. pyproj's own
    PROJ strings drop the datum shift and are ~300 m out for Accra systems."""
    crs = system(code)
    web = Transformer.from_crs("EPSG:4326", CRS.from_proj4(services.web_proj4(crs)), always_xy=True)
    lonlat = GHANA_LONLAT[::3]
    server, _ = transform_points(lonlat, system("EPSG:4326"), crs)
    for (lon, lat), expected in zip(lonlat, server, strict=True):
        assert metres(crs, web.transform(lon, lat), expected) < 0.01, code


def test_web_proj4_follows_a_pinned_operation(system_admin):
    grid, wgs = system("EPSG:2136"), system("EPSG:4326")
    default_web = services.web_proj4(grid)
    alternative = services.candidate_operations(grid, wgs)[1]
    PreferredTransformation.objects.create(
        source=wgs,
        target=grid,
        name=alternative.name,
        accuracy_m=alternative.accuracy_m,
        pipeline=services.candidate_operations(wgs, grid)[1].pipeline,
    )
    pinned_web = services.web_proj4(grid)
    assert pinned_web != default_web
    web = Transformer.from_crs("EPSG:4326", CRS.from_proj4(pinned_web), always_xy=True)
    server, _ = transform_points([(-0.2, 5.6)], wgs, grid)
    assert metres(grid, web.transform(-0.2, 5.6), server[0]) < 0.01

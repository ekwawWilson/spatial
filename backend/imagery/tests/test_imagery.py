# ruff: noqa: E501 - long assertions read better on one line
"""Phase 11: drone orthophotos, elevation models, tiles, offline basemaps."""

import sqlite3
import struct
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from osgeo import gdal, osr
from pyproj import Transformer

from basemaps.models import BasemapSource
from core.models import AuditLog, Role
from core.tenancy import tenant_context
from field import mbtiles
from imagery import raster, services
from imagery.models import Imagery
from projects.models import Feature

pytestmark = pytest.mark.django_db
gdal.UseExceptions()

# The fixture orthophoto (fixtures/README.md): 200 m square, 1 m pixels, UTM 30N.
ORIGIN_E, ORIGIN_N = 806_000.0, 617_000.0
BUILDING = (
    523.0,
    1013.0,
    547.0,
    1037.0,
)  # a light square: west, south, east, north (m from origin)
TOLERANCE_M = 1.0  # one pixel of the source image
ZOOM = 20
TO_WGS = Transformer.from_crs(32630, 4326, always_xy=True)
TO_NATIVE = Transformer.from_crs(4326, 2136, always_xy=True)


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def project(planner):
    return planner.post(reverse("project-list"), {"name": "Imagery plan"}, format="json").json()


@pytest.fixture
def ortho_file(fixtures_dir) -> Path:
    return Path(fixtures_dir) / "generated" / "drone_ortho.tif"


def upload(client, project_id, path, capture, **extra):
    with open(path, "rb") as fh, capture(execute=True):
        response = client.post(
            reverse("imagery-list"),
            {"project": project_id, "file": fh, **extra},
            format="multipart",
        )
    return response


def ready(client, response):
    assert response.status_code == 201, response.content
    item = client.get(reverse("imagery-detail", args=[response.json()["id"]])).json()
    assert item["status"] == "ready", item["error"]
    return item


def write_raster(path, *, epsg=32630, bands=1, georeferenced=True, data_type=gdal.GDT_Float32):
    """A 100 x 100 raster, 1 m pixels. One band: a slope rising 0.5 per metre eastwards."""
    ds = gdal.GetDriverByName("GTiff").Create(str(path), 100, 100, bands, data_type)
    if georeferenced:
        ds.SetGeoTransform((ORIGIN_E, 1.0, 0.0, ORIGIN_N + 100.0, 0.0, -1.0))
    if epsg:
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(epsg)
        ds.SetProjection(ref.ExportToWkt())
    row = struct.pack("100f", *[(col + 0.5) * 0.5 for col in range(100)])
    for b in range(bands):
        band = ds.GetRasterBand(b + 1)
        for y in range(100):
            band.WriteRaster(0, y, 100, 1, row, buf_type=gdal.GDT_Float32)
    ds.Close()
    return path


class Tiles:
    """Reads colours from the tile API at ground positions."""

    def __init__(self, client, imagery_id):
        self.client, self.imagery_id, self.cache = client, imagery_id, {}

    def colour(self, easting, northing):
        lon, lat = TO_WGS.transform(easting, northing)
        mx, my = raster.lonlat_to_mercator(lon, lat)
        size = 2 * raster.WEB_MERCATOR_HALF / 2**ZOOM
        x = int((mx + raster.WEB_MERCATOR_HALF) / size)
        y = int((raster.WEB_MERCATOR_HALF - my) / size)
        if (x, y) not in self.cache:
            url = reverse("imagery-tile", args=[self.imagery_id, ZOOM, x, y])
            response = self.client.get(url)
            assert response.status_code == 200, (response.status_code, url)
            name = f"/vsimem/test-{x}-{y}.png"
            gdal.FileFromMemBuffer(name, response.content)
            self.cache[(x, y)] = gdal.Open(name)
        ds = self.cache[(x, y)]
        west, south, east, north = raster.tile_bounds(ZOOM, x, y)
        col = min(255, int((mx - west) / (east - west) * 256))
        row = min(255, int((north - my) / (north - south) * 256))
        return tuple(ds.GetRasterBand(b).ReadRaster(col, row, 1, 1)[0] for b in (1, 2, 3, 4))


# --- Orthophoto ------------------------------------------------------------------------------------


def test_orthophoto_becomes_a_basemap_with_its_metadata(
    planner, project, ortho_file, district_a, django_capture_on_commit_callbacks
):
    item = ready(
        planner, upload(planner, project["id"], ortho_file, django_capture_on_commit_callbacks)
    )
    assert item["crs"].startswith("EPSG:32630")
    assert (item["width"], item["height"], item["bands"]) == (200, 200, 3)
    assert item["resolution_m"] == pytest.approx(1.0)
    assert (
        item["capture_date"] == "2026-09-01" and "synthetic" in item["source"]
    )  # from the file's tags
    west, south, east, north = item["bounds"]
    lon, lat = TO_WGS.transform(ORIGIN_E + 550, ORIGIN_N + 1000)
    assert west < lon < east and south < lat < north
    assert (
        item["max_zoom"] >= 17
        and item["tile_url"] == f"/api/imagery/{item['id']}/tiles/{{z}}/{{x}}/{{y}}.png"
    )

    # Stored as a cloud-optimised GeoTIFF in its own CRS; the upload itself is not kept twice.
    imagery = Imagery.objects.get(pk=item["id"])
    cog = gdal.Open(str(services.cog_path(imagery)))
    assert cog.GetMetadataItem("LAYOUT", "IMAGE_STRUCTURE") == "COG"
    assert cog.GetSpatialRef().GetAuthorityCode(None) == "32630"
    assert cog.GetGeoTransform() == (ORIGIN_E + 450.0, 1.0, 0.0, ORIGIN_N + 1100.0, 0.0, -1.0)
    assert not services.source_path(imagery).exists()

    # It is in the basemap list, the district's own, and may be stored offline.
    basemap = BasemapSource.objects.get(pk=item["basemap"])
    assert basemap.district_id == district_a.id and basemap.offline_cache_allowed is True
    listed = planner.get(reverse("basemap-list")).json()
    assert any(b["id"] == basemap.pk and b["url"] == item["tile_url"] for b in listed)
    assert AuditLog.objects.filter(table_name="imagery_imagery", row_id=str(item["id"])).exists()


def test_tiles_line_up_with_the_ground(
    planner, project, ortho_file, django_capture_on_commit_callbacks
):
    """Gate: the fixture image displays aligned with the vector data. The
    edges of a building in the tiles are within one source pixel (1 m) of
    where the building is."""
    item = ready(
        planner, upload(planner, project["id"], ortho_file, django_capture_on_commit_callbacks)
    )
    tiles = Tiles(planner, item["id"])
    west, south, east, north = BUILDING
    mid_e, mid_n = (west + east) / 2, (south + north) / 2

    def is_building(e, n):
        r, g, b, a = tiles.colour(ORIGIN_E + e, ORIGIN_N + n)
        return a == 255 and r > 160  # building 210, ground 110

    assert is_building(mid_e, mid_n) and not is_building(west - 4, mid_n)
    steps = [i * 0.1 for i in range(-50, 51)]
    found_west = next(west + d for d in steps if is_building(west + d, mid_n))
    found_east = next(east - d for d in steps if is_building(east - d, mid_n))
    found_south = next(south + d for d in steps if is_building(mid_e, south + d))
    found_north = next(north - d for d in steps if is_building(mid_e, north - d))
    for found, truth in (
        (found_west, west),
        (found_east, east),
        (found_south, south),
        (found_north, north),
    ):
        assert abs(found - truth) < TOLERANCE_M, (found, truth)

    # The road strip, and transparency outside the image.
    r, g, b, a = tiles.colour(ORIGIN_E + 600, ORIGIN_N + 1000)
    assert (a, r < 90) == (255, True)
    outside = planner.get(reverse("imagery-tile", args=[item["id"], ZOOM, 0, 0]))
    assert outside.status_code == 204


def test_files_that_cannot_be_placed_are_refused_with_a_reason(
    planner, project, tmp_path, django_capture_on_commit_callbacks
):
    capture = django_capture_on_commit_callbacks
    text = tmp_path / "notes.txt"
    text.write_text("not an image")
    assert upload(planner, project["id"], text, capture).status_code == 400  # not a GeoTIFF

    plain = write_raster(tmp_path / "plain.tif", georeferenced=False, epsg=None)
    response = upload(planner, project["id"], plain, capture)
    failed = planner.get(reverse("imagery-detail", args=[response.json()["id"]])).json()
    assert failed["status"] == "failed" and "isn't georeferenced" in failed["error"]
    assert failed["basemap"] is None and failed["tile_url"] is None

    no_crs = write_raster(tmp_path / "nocrs.tif", epsg=None, bands=3)
    response = upload(planner, project["id"], no_crs, capture)
    failed = planner.get(reverse("imagery-detail", args=[response.json()["id"]])).json()
    assert failed["status"] == "failed" and "which coordinate system" in failed["error"]
    # The same file with the CRS given at upload is accepted.
    item = ready(planner, upload(planner, project["id"], no_crs, capture, crs="EPSG:32630"))
    assert item["crs"].startswith("EPSG:32630")

    many_bands = write_raster(tmp_path / "rgb.tif", bands=3)
    response = upload(planner, project["id"], many_bands, capture, kind="dem")
    failed = planner.get(reverse("imagery-detail", args=[response.json()["id"]])).json()
    assert failed["status"] == "failed" and "one band" in failed["error"]


def test_editing_and_deleting(planner, project, ortho_file, django_capture_on_commit_callbacks):
    item = ready(
        planner, upload(planner, project["id"], ortho_file, django_capture_on_commit_callbacks)
    )
    url = reverse("imagery-detail", args=[item["id"]])
    patched = planner.patch(
        url, {"name": "June flight", "capture_date": "2026-06-15"}, format="json"
    )
    assert patched.status_code == 200 and patched.json()["capture_date"] == "2026-06-15"
    assert BasemapSource.objects.get(pk=item["basemap"]).name == "June flight (imagery)"
    assert (
        planner.patch(url, {"status": "queued"}, format="json").json()["status"] == "ready"
    )  # read-only

    directory = services.folder(Imagery.objects.get(pk=item["id"]))
    assert directory.exists()
    assert planner.delete(url).status_code == 204
    assert not directory.exists()
    assert not BasemapSource.objects.filter(pk=item["basemap"]).exists()


# --- Offline in the field --------------------------------------------------------------------------


def test_drone_imagery_goes_to_the_field_as_mbtiles(
    planner,
    api,
    members_a,
    district_a,
    project,
    ortho_file,
    tmp_path,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    """Gate: an MBTiles file of the planning area, built from the district's
    own imagery on this server (no outside tile service is contacted)."""
    item = ready(
        planner, upload(planner, project["id"], ortho_file, django_capture_on_commit_callbacks)
    )
    # A planning area over the image: 60 m around the first building, in the project's CRS.
    corners = [(500, 990), (570, 990), (570, 1060), (500, 1060), (500, 990)]
    ring = [
        list(TO_NATIVE.transform(*TO_WGS.transform(ORIGIN_E + e, ORIGIN_N + n))) for e, n in corners
    ]
    area = planner.put(
        reverse("project-boundary", args=[project["id"]]),
        {"geometry": {"type": "Polygon", "coordinates": [ring]}, "method": "coordinates"},
        format="json",
    )
    assert area.status_code == 200, area.content

    officer = api(members_a[Role.FIELD_OFFICER], district_a)
    offered = officer.get(reverse("project-field-package", args=[project["id"]])).json()[
        "offline_basemaps"
    ]
    assert [b["id"] for b in offered] == [item["basemap"]]

    def no_network(url):
        raise AssertionError(f"fetched {url}")

    monkeypatch.setattr(mbtiles, "fetch_tile", no_network)
    response = officer.get(
        reverse("project-field-basemap", args=[project["id"]]),
        {"source": item["basemap"], "max_zoom": 17},
    )
    assert response.status_code == 200, getattr(response, "content", b"")
    path = tmp_path / "field.mbtiles"
    path.write_bytes(b"".join(response.streaming_content))
    db = sqlite3.connect(path)
    metadata = dict(db.execute("SELECT name, value FROM metadata").fetchall())
    assert metadata["format"] == "png" and metadata["maxzoom"] == "17"
    count, top = db.execute("SELECT count(*), max(zoom_level) FROM tiles").fetchone()
    assert count >= 1 and top == 17
    (tile,) = db.execute("SELECT tile_data FROM tiles WHERE zoom_level = 17 LIMIT 1").fetchone()
    assert bytes(tile).startswith(b"\x89PNG")


# --- Elevation models and contours ---------------------------------------------------------------


def test_contours_from_an_elevation_model(
    planner, project, tmp_path, django_capture_on_commit_callbacks
):
    dem = write_raster(tmp_path / "dem.tif")
    item = ready(
        planner, upload(planner, project["id"], dem, django_capture_on_commit_callbacks, kind="dem")
    )
    assert item["basemap"] is None  # an elevation model isn't a basemap
    low, high = item["value_range"]
    assert low == pytest.approx(0.25) and high == pytest.approx(49.75)
    assert planner.get(reverse("imagery-tile", args=[item["id"], 17, 0, 0])).status_code == 204

    url = reverse("imagery-contours", args=[item["id"]])
    made = planner.post(url, {"interval": 10}, format="json")
    assert made.status_code == 201, made.content
    result = made.json()
    assert result["contours"] == 4 and result["layer_name"] == "Topography (contours)"
    assert result["converted_from"] == "EPSG:32630"

    features = planner.get(
        reverse("layer-features", args=[result["layer"]]) + "?geometry=native"
    ).json()["features"]
    assert sorted(f["properties"]["elevation"] for f in features) == [10, 20, 30, 40]
    # The slope rises 0.5 per metre, so the 10 line runs 20 m east of the image's edge.
    ten = next(f for f in features if f["properties"]["elevation"] == 10)
    back = planner.post(
        reverse("crs-transform"),
        {
            "from_crs": "EPSG:2136",
            "to_crs": "EPSG:32630",
            "points": ten["geometry"]["coordinates"][:1],
        },
        format="json",
    ).json()["points"][0]
    assert abs(back[0] - (ORIGIN_E + 20.0)) < TOLERANCE_M
    assert features[0]["meta"]["origin"] == "derived"

    # Making them again replaces the old lines; a finer interval gives more.
    again = planner.post(url, {"interval": 5}, format="json").json()
    assert (again["replaced"], again["contours"]) == (4, 9)
    assert Feature.objects.filter(layer_id=result["layer"]).count() == 9
    assert planner.post(url, {"interval": 0}, format="json").status_code == 400

    # The checklist's topography item picks the layer up by its name.
    checklist = planner.get(reverse("project-checklist", args=[project["id"]])).json()
    topography = next(i for i in checklist["items"] if i["key"] == "topography")
    assert (
        topography["linked_layer"] == result["layer"]
        and topography["metrics"]["feature_count"] == 9
    )


def test_contours_need_an_elevation_model(
    planner, project, ortho_file, django_capture_on_commit_callbacks
):
    item = ready(
        planner, upload(planner, project["id"], ortho_file, django_capture_on_commit_callbacks)
    )
    response = planner.post(
        reverse("imagery-contours", args=[item["id"]]), {"interval": 5}, format="json"
    )
    assert response.status_code == 400 and "elevation model" in str(response.json())


# --- Checklist: base map recency ---------------------------------------------------------------------


def imagery_item(client, project_id):
    data = client.get(reverse("project-checklist", args=[project_id])).json()
    return next(i for i in data["items"] if i["key"] == "imagery")


def test_checklist_measures_how_recent_the_imagery_is(
    planner, project, ortho_file, django_capture_on_commit_callbacks
):
    item = imagery_item(planner, project["id"])
    assert item["rules"] == {"imagery_max_age_days": 365}
    assert item["metrics"]["imagery_count"] == 0 and item["rules_met"] is False
    url = reverse("checklist-item-detail", args=[item["id"]])
    refused = planner.patch(url, {"status": "ready"}, format="json")
    assert refused.status_code == 400 and "No imagery" in str(refused.json())

    old = (date.today() - timedelta(days=500)).isoformat()
    uploaded = ready(
        planner,
        upload(
            planner, project["id"], ortho_file, django_capture_on_commit_callbacks, capture_date=old
        ),
    )
    item = imagery_item(planner, project["id"])
    assert item["metrics"]["age_days"] == 500 and item["metrics"][
        "best_resolution_m"
    ] == pytest.approx(1.0)
    assert any("500 days old" in c["problem"] for c in item["checks"] if not c["ok"])

    recent = (date.today() - timedelta(days=30)).isoformat()
    planner.patch(
        reverse("imagery-detail", args=[uploaded["id"]]), {"capture_date": recent}, format="json"
    )
    item = imagery_item(planner, project["id"])
    assert item["metrics"]["age_days"] == 30 and item["rules_met"] is True
    assert planner.patch(url, {"status": "ready"}, format="json").status_code == 200


# --- Roles and tenancy -----------------------------------------------------------------------------


def test_roles_and_tenancy(
    planner,
    api,
    members_a,
    district_a,
    district_b,
    make_member,
    project,
    ortho_file,
    django_capture_on_commit_callbacks,
):
    capture = django_capture_on_commit_callbacks
    viewer = api(members_a[Role.VIEWER], district_a)
    assert upload(viewer, project["id"], ortho_file, capture).status_code == 403
    item = ready(planner, upload(planner, project["id"], ortho_file, capture))
    detail = reverse("imagery-detail", args=[item["id"]])
    lon, lat = TO_WGS.transform(ORIGIN_E + 535, ORIGIN_N + 1025)
    x, y = mbtiles.tile_xy(lon, lat, 18)
    tile = reverse("imagery-tile", args=[item["id"], 18, x, y])

    assert viewer.get(detail).status_code == 200 and viewer.get(tile).status_code == 200
    assert viewer.delete(detail).status_code == 403
    assert (
        viewer.post(
            reverse("imagery-contours", args=[item["id"]]), {"interval": 1}, format="json"
        ).status_code
        == 403
    )

    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(detail).status_code == 404 and other.get(tile).status_code == 404
    assert other.get(reverse("imagery-list")).json() == []
    assert upload(other, project["id"], ortho_file, capture).status_code == 404
    with tenant_context(district_b.id):
        assert Imagery.objects.count() == 0
    assert (
        planner.get(reverse("imagery-list"), {"project": project["id"]}).json()[0]["id"]
        == item["id"]
    )

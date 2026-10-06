"""Phase 9 (server side): the field package and its offline basemap."""

import sqlite3

import pytest
from django.urls import reverse

from basemaps.models import BasemapSource
from core.models import Role
from field import mbtiles, services

pytestmark = pytest.mark.django_db

X0, Y0, SIDE = 1190000.0, 337000.0, 1000.0


def ring(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


AREA = ring(X0, Y0, X0 + SIDE, Y0 + SIDE)
INSIDE = ring(X0 + 100, Y0 + 100, X0 + 200, Y0 + 200)
STRADDLING = ring(X0 + 900, Y0 + 900, X0 + 1100, Y0 + 1100)
OUTSIDE = ring(X0 + 5000, Y0 + 5000, X0 + 5100, Y0 + 5100)
PNG = b"\x89PNG\r\n\x1a\n" + b"tile"


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def officer(api, members_a, district_a):
    return api(members_a[Role.FIELD_OFFICER], district_a)


@pytest.fixture
def project(planner):
    project = planner.post(reverse("project-list"), {"name": "Field plan"}, format="json").json()
    layer = planner.post(
        reverse("layer-list"),
        {
            "project": project["id"],
            "name": "Buildings",
            "domain": "C",
            "geometry_type": "polygon",
            "schema": [
                {"name": "use", "type": "choice", "choices": ["house", "shop"], "required": True},
                {"name": "storeys", "type": "integer", "default": 1},
            ],
        },
        format="json",
    ).json()
    for name, coords in (("in", INSIDE), ("edge", STRADDLING), ("out", OUTSIDE)):
        response = planner.post(
            reverse("layer-features", args=[layer["id"]]),
            {
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {"use": "house", "storeys": len(name)},
            },
            format="json",
        )
        assert response.status_code == 201, response.content
    return {"id": project["id"], "layer": layer["id"]}


def set_area(client, project_id):
    response = client.put(
        reverse("project-boundary", args=[project_id]),
        {"geometry": {"type": "Polygon", "coordinates": [AREA]}, "method": "coordinates"},
        format="json",
    )
    assert response.status_code == 200, response.content


def package(client, project_id, **params):
    return client.get(reverse("project-field-package", args=[project_id]), params)


def offline_source(district, **extra) -> BasemapSource:
    return BasemapSource.objects.create(
        district=district,
        name="Assembly drone tiles",
        kind="xyz",
        url="https://tiles.example.org/{z}/{x}/{y}.png",
        min_zoom=14,
        max_zoom=16,
        offline_cache_allowed=True,
        **extra,
    )


# --- The package -----------------------------------------------------------------------


def test_package_has_forms_and_features_inside_the_planning_area(officer, planner, project):
    set_area(planner, project["id"])
    response = package(officer, project["id"])
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["format"] == services.PACKAGE_FORMAT and data["clipped_to_boundary"] is True
    assert data["project"]["boundary"]["type"] == "Polygon"
    west, south, east, north = data["project"]["bbox"]
    assert west < east and south < north

    # The project's coordinate system, with the definition the web map uses.
    crs = data["project"]["crs"]
    assert crs["code"] == "EPSG:2136" and "+towgs84" in crs["proj4"]
    assert crs["unit_to_metre"] == pytest.approx(0.3047997, rel=1e-6)

    layers = {layer["name"]: layer for layer in data["layers"]}
    buildings = layers["Buildings"]
    assert [f["name"] for f in buildings["schema"]] == ["use", "storeys"]  # the form
    assert buildings["schema"][0]["choices"] == ["house", "shop"]
    rows = data["features"][str(buildings["id"])]
    # Inside and straddling the edge come whole; the one outside stays at the office.
    assert sorted(r["properties"]["storeys"] for r in rows) == [2, 4]
    assert buildings["feature_count"] == 2
    for row in rows:
        assert row["version"] == 1 and len(row["uuid"]) == 36
        lon, lat = row["geometry"]["coordinates"][0][0]
        assert -4 < lon < 2 and 4 < lat < 12  # WGS 84 degrees, in Ghana
    straddler = next(r for r in rows if r["properties"]["storeys"] == 4)
    assert len(straddler["geometry"]["coordinates"][0]) == 5  # not cut at the boundary


def test_without_a_planning_area_every_feature_comes(officer, project):
    data = package(officer, project["id"]).json()
    assert data["clipped_to_boundary"] is False and data["project"]["boundary"] is None
    assert data["feature_total"] == 3


def test_chosen_layers_only(officer, planner, project):
    other = planner.post(
        reverse("layer-list"),
        {
            "project": project["id"],
            "name": "Pegs",
            "geometry_type": "point",
            "schema": [{"name": "pid", "type": "text"}],
        },
        format="json",
    ).json()
    data = package(officer, project["id"], layers=str(other["id"])).json()
    assert [layer["name"] for layer in data["layers"]] == ["Pegs"]
    assert list(data["features"]) == [str(other["id"])]

    assert package(officer, project["id"], layers="x").status_code == 400
    elsewhere = planner.post(reverse("project-list"), {"name": "Other"}, format="json").json()
    foreign = planner.post(
        reverse("layer-list"),
        {
            "project": elsewhere["id"],
            "name": "Foreign",
            "geometry_type": "point",
            "schema": [{"name": "pid", "type": "text"}],
        },
        format="json",
    ).json()
    refused = package(officer, project["id"], layers=str(foreign["id"]))
    assert refused.status_code == 400 and "Not layers of this project" in str(refused.json())


def test_too_many_features_asks_for_fewer_layers(officer, project, monkeypatch):
    monkeypatch.setattr(services, "MAX_FEATURES", 2)
    response = package(officer, project["id"])
    assert response.status_code == 400 and "Choose fewer layers" in str(response.json())


def test_roles_and_tenancy(api, members_a, district_a, district_b, make_member, project):
    assert package(api(members_a[Role.VIEWER], district_a), project["id"]).status_code == 403
    for role in (Role.FIELD_OFFICER, Role.PLANNER, Role.DISTRICT_ADMIN):
        assert package(api(members_a[role], district_a), project["id"]).status_code == 200
    other = api(make_member(district_b, Role.FIELD_OFFICER, "b.officer@example.test"), district_b)
    assert package(other, project["id"]).status_code == 404


# --- Offline basemap -------------------------------------------------------------------


def test_only_cache_allowed_basemaps_are_offered(officer, project, district_a):
    assert package(officer, project["id"]).json()["offline_basemaps"] == []  # no preset allows it
    source = offline_source(district_a)
    offered = package(officer, project["id"]).json()["offline_basemaps"]
    assert [b["id"] for b in offered] == [source.pk]


def test_no_cache_basemaps_are_never_packaged(officer, planner, project):
    """Gate (Phase 4, enforced here): a source whose terms forbid offline use is refused."""
    set_area(planner, project["id"])
    osm = BasemapSource.objects.get(preset="osm")
    response = officer.get(
        reverse("project-field-basemap", args=[project["id"]]), {"source": osm.pk}
    )
    assert response.status_code == 400
    assert "don't allow storing tiles for offline use" in str(response.json())


def test_offline_basemap_is_an_mbtiles_file(
    officer, planner, project, district_a, monkeypatch, tmp_path
):
    set_area(planner, project["id"])
    source = offline_source(district_a)
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return PNG

    monkeypatch.setattr(mbtiles, "fetch_tile", fake_fetch)
    monkeypatch.setattr(mbtiles, "check_public_url", lambda url: None)
    response = officer.get(
        reverse("project-field-basemap", args=[project["id"]]),
        {"source": source.pk, "max_zoom": 15},
    )
    assert response.status_code == 200, getattr(response, "content", b"")
    assert response["Content-Disposition"].endswith('.mbtiles"')
    path = tmp_path / "basemap.mbtiles"
    path.write_bytes(b"".join(response.streaming_content))

    db = sqlite3.connect(path)
    metadata = dict(db.execute("SELECT name, value FROM metadata").fetchall())
    assert metadata["format"] == "png" and metadata["name"] == "Assembly drone tiles"
    assert (metadata["minzoom"], metadata["maxzoom"]) == ("14", "15")  # capped by max_zoom
    tiles = db.execute("SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles").fetchall()
    assert tiles and all(row[3] == PNG for row in tiles)
    assert {row[0] for row in tiles} == {14, 15}
    assert len(tiles) == len(fetched)
    # Rows are stored south-up (TMS): the XYZ row is the mirror image.
    zoom, column, row, _ = tiles[0]
    assert f"/{zoom}/{column}/{(2**zoom - 1) - row}.png" in fetched[0]
    assert all(url.startswith("https://tiles.example.org/") for url in fetched)


def test_offline_basemap_limits(officer, planner, project, district_a, monkeypatch):
    source = offline_source(district_a)
    url = reverse("project-field-basemap", args=[project["id"]])
    no_area = officer.get(url, {"source": source.pk})
    assert no_area.status_code == 400 and "planning area first" in str(no_area.json())

    set_area(planner, project["id"])
    monkeypatch.setattr(mbtiles, "MAX_TILES", 1)
    monkeypatch.setattr(mbtiles, "check_public_url", lambda url: None)
    too_many = officer.get(url, {"source": source.pk})
    assert too_many.status_code == 400 and "lower maximum zoom" in str(too_many.json())
    assert officer.get(url, {"source": "abc"}).status_code == 400


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/{z}/{x}/{y}.png",
        "http://localhost/{z}/{x}/{y}.png",
        "http://10.0.0.5/{z}/{x}/{y}.png",
        "http://169.254.169.254/latest/{z}/{x}/{y}",
        "file:///etc/{z}/{x}/{y}",
    ],
)
def test_tile_addresses_inside_the_servers_network_are_refused(
    officer, planner, project, district_a, url
):
    set_area(planner, project["id"])
    source = offline_source(
        district_a,
    )
    BasemapSource.objects.filter(pk=source.pk).update(url=url)
    response = officer.get(
        reverse("project-field-basemap", args=[project["id"]]), {"source": source.pk}
    )
    assert response.status_code == 400
    assert "private network" in str(response.json()) or "http://" in str(response.json())


def test_tile_maths():
    # Zoom 0 is one tile; central Accra at zoom 12 is tile 2045/1984.
    assert mbtiles.tile_xy(0, 0, 0) == (0, 0)
    assert mbtiles.tile_xy(-0.187, 5.603, 12) == (2045, 1984)
    ranges = mbtiles.tile_ranges([-0.2, 5.5, -0.1, 5.6], 12, 13)
    assert [r[0] for r in ranges] == [12, 13]
    assert mbtiles.count_tiles(ranges) == sum(
        (x1 - x0 + 1) * (y1 - y0 + 1) for _, x0, x1, y0, y1 in ranges
    )

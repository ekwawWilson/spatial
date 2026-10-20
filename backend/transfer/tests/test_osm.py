# ruff: noqa: E501 - long assertions read better on one line
"""OpenStreetMap features inside a marked area, brought in as project layers.
OpenStreetMap is never asked: transfer.osm.fetch is replaced by a canned answer."""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import Role
from core.tenancy import tenant_context
from projects.models import Feature, Layer, PlanProject
from transfer import osm
from transfer.models import DataJob

pytestmark = pytest.mark.django_db

# About 1.1 km square near Kasoa (WGS 84).
W, S, E, N = -0.430, 5.520, -0.420, 5.530
RING = [(W, S), (E, S), (E, N), (W, N), (W, S)]
AREA = {"type": "Polygon", "coordinates": [[list(p) for p in RING]]}


def way(id_: int, tags: dict[str, str], points: list[tuple[float, float]]) -> dict[str, Any]:
    return {
        "type": "way",
        "id": id_,
        "tags": tags,
        "geometry": [{"lon": x, "lat": y} for x, y in points],
    }


def square(x: float, y: float, d: float = 0.0002) -> list[tuple[float, float]]:
    return [(x, y), (x + d, y), (x + d, y + d), (x, y + d), (x, y)]


ANSWER = {
    "elements": [
        # Runs from inside the area to well outside it: cut at the edge.
        way(
            1,
            {"highway": "residential", "name": "Station Road", "surface": "asphalt"},
            [(-0.425, 5.525), (-0.415, 5.525)],
        ),
        way(
            2, {"highway": "construction"}, [(-0.428, 5.522), (-0.426, 5.522)]
        ),  # not a kind of street we bring in
        way(3, {"building": "yes", "addr:housenumber": "14"}, square(-0.426, 5.526)),
        way(4, {"building": "house"}, square(-0.300, 5.600)),  # outside the area
        way(5, {"building": "yes"}, [(-0.427, 5.527), (-0.4269, 5.527)]),  # not closed: no building
        {
            "type": "node",
            "id": 6,
            "lat": 5.524,
            "lon": -0.424,
            "tags": {"amenity": "school", "name": "Kasoa M/A Basic"},
        },
        way(7, {"amenity": "marketplace", "name": "Kasoa market"}, square(-0.422, 5.528, 0.0004)),
    ]
}


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def project(planner):
    made = planner.post(reverse("project-list"), {"name": "OSM tests"}, format="json")
    return PlanProject.objects.get(pk=made.json()["id"])


@pytest.fixture
def answered(monkeypatch):
    asked: list[str] = []

    def fake(ql: str) -> dict[str, Any]:
        asked.append(ql)
        return ANSWER

    monkeypatch.setattr(osm, "fetch", fake)
    return asked


def start(client, project, capture, **body):
    with capture(execute=True):
        return client.post(
            reverse("datajob-openstreetmap"),
            {
                "project": project.id,
                "kinds": ["streets", "buildings", "places"],
                "area": AREA,
                **body,
            },
            format="json",
        )


def test_the_query_asks_for_each_kind_inside_the_box():
    ql = osm.query([osm.KIND_BY_CODE["streets"], osm.KIND_BY_CODE["places"]], AREA)
    assert ql.startswith("[out:json][timeout:110];(") and ql.endswith(");out tags geom;")
    assert 'way["highway"~"^(motorway|' in ql and "(5.520000,-0.430000,5.530000,-0.420000)" in ql
    assert 'node["amenity"~"^(school|' in ql and 'way["shop"]' in ql


def test_features_in_the_area_become_layers_to_edit(
    planner, project, answered, district_a, django_capture_on_commit_callbacks
):
    """Gate: what lies in the area arrives, in the project's coordinate system, once."""
    made = start(planner, project, django_capture_on_commit_callbacks)
    assert made.status_code == 201, made.content
    with tenant_context(district_a.id):
        job = DataJob.objects.get(pk=made.json()["id"])
        assert job.status == DataJob.Status.DONE, job.error
        assert job.report["osm"]["found"] == {"streets": 1, "buildings": 1, "places": 2}
        assert job.report["osm"]["attribution"] == "© OpenStreetMap contributors (ODbL)"
        layers = {layer.name: layer for layer in Layer.objects.filter(project=project)}
        streets = layers["Streets (OpenStreetMap)"]
        assert (
            streets.geometry_type,
            streets.domain,
            streets.crs_id,
            streets.style["label_field"],
        ) == ("line", "D", project.crs_id, "name")
        assert [f["name"] for f in streets.schema][:3] == ["osm_id", "name", "road_class"]
        road = Feature.objects.get(layer=streets)
        assert {k: v for k, v in road.properties.items() if v} == {
            "osm_id": "way/1",
            "name": "Station Road",
            "road_class": "residential",
            "surface": "asphalt",
        }
        assert road.origin == Feature.Origin.IMPORT
        building = Feature.objects.get(layer=layers["Buildings (OpenStreetMap)"])
        assert (building.properties["osm_id"], building.properties["house_no"]) == ("way/3", "14")
        places = Feature.objects.filter(layer=layers["Places (OpenStreetMap)"]).order_by(
            "properties__osm_id"
        )
        assert [(p.properties["osm_id"], p.properties["name"]) for p in places] == [
            ("node/6", "Kasoa M/A Basic"),
            ("way/7", "Kasoa market"),
        ]
    assert len(answered) == 1

    # Asked again: nothing comes in twice, and the layers are the same ones.
    again = start(planner, project, django_capture_on_commit_callbacks)
    with tenant_context(district_a.id):
        job = DataJob.objects.get(pk=again.json()["id"])
        assert job.status == DataJob.Status.DONE, job.error
        assert job.report["osm"]["found"] == {"streets": 0, "buildings": 0, "places": 0}
        assert job.report["osm"]["already_in_project"] == {
            "streets": 1,
            "buildings": 1,
            "places": 2,
        }
        assert Layer.objects.filter(project=project).count() == 3
        assert Feature.objects.filter(layer__project=project).count() == 4


def test_the_street_is_cut_at_the_edge_of_the_area(
    planner, project, answered, district_a, django_capture_on_commit_callbacks
):
    start(planner, project, django_capture_on_commit_callbacks, kinds=["streets"])
    url = reverse(
        "layer-features",
        args=[Layer.objects.get(project=project, name="Streets (OpenStreetMap)").pk],
    )
    [road] = planner.get(url).json()["features"]  # WGS 84 by default
    xs = (
        [x for line in road["geometry"]["coordinates"] for x, _ in line]
        if road["geometry"]["type"] == "MultiLineString"
        else [x for x, _ in road["geometry"]["coordinates"]]
    )
    assert max(xs) == pytest.approx(E, abs=1e-6) and min(xs) == pytest.approx(-0.425, abs=1e-6)


def test_what_is_refused(
    planner,
    api,
    members_a,
    district_a,
    project,
    answered,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    url = reverse("datajob-openstreetmap")
    big = {
        "type": "Polygon",
        "coordinates": [[[-0.5, 5.4], [-0.3, 5.4], [-0.3, 5.6], [-0.5, 5.6], [-0.5, 5.4]]],
    }
    assert "at most 60 km²" in str(
        planner.post(
            url, {"project": project.id, "kinds": ["streets"], "area": big}, format="json"
        ).json()
    )
    assert (
        planner.post(
            url, {"project": project.id, "kinds": ["rivers"], "area": AREA}, format="json"
        ).status_code
        == 400
    )
    assert (
        planner.post(
            url, {"project": project.id, "kinds": ["streets"], "use_boundary": True}, format="json"
        ).status_code
        == 400
    )  # no planning area yet
    assert (
        planner.post(
            url,
            {
                "project": project.id,
                "kinds": ["streets"],
                "area": {"type": "Point", "coordinates": [0, 0]},
            },
            format="json",
        ).status_code
        == 400
    )
    viewer = api(members_a[Role.VIEWER], district_a)
    assert (
        viewer.post(
            url, {"project": project.id, "kinds": ["streets"], "area": AREA}, format="json"
        ).status_code
        == 403
    )

    # OpenStreetMap unreachable: the job says so, and no layer is left behind.
    def down(ql: str) -> dict[str, Any]:
        raise ValidationError(
            "OpenStreetMap could not be reached just now (test). Try again later."
        )

    monkeypatch.setattr(osm, "fetch", down)
    made = start(planner, project, django_capture_on_commit_callbacks)
    with tenant_context(district_a.id):
        job = DataJob.objects.get(pk=made.json()["id"])
        assert job.status == DataJob.Status.FAILED and "could not be reached" in job.error
        assert not Layer.objects.filter(project=project).exists()


def test_an_area_in_the_map_s_own_coordinates_is_accepted(
    planner, project, answered, district_a, django_capture_on_commit_callbacks
):
    # The same square in Web Mercator, as the map draws it.
    import math

    def merc(lon: float, lat: float) -> list[float]:
        return [
            lon * 20037508.34 / 180,
            math.log(math.tan((90 + lat) * math.pi / 360)) * 20037508.34 / math.pi,
        ]

    area = {"type": "Polygon", "coordinates": [[merc(x, y) for x, y in RING]]}
    made = start(
        planner, project, django_capture_on_commit_callbacks, area=area, area_crs="EPSG:3857"
    )
    assert made.status_code == 201, made.content
    assert made.json()["plan"]["osm"]["area_km2"] == pytest.approx(1.23, abs=0.05)

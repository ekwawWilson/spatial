"""Phase 13 gate: a large district. 500,000 features in one layer, then the
operations people wait on are timed against targets.

Targets (seconds), on the CI machine:
  map tile at street zooms (15-17)         0.5
  map tile at zoom 14 (about 17,000        1.0
    buildings in the one tile)
  a page of 1,000 features in a map view   1.5
  field package for a planning area        5
  incremental pull after one edit          2
  relationship run (flood risk + totals)   30
"""

import time
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.urls import reverse

from core.models import Role
from field import mbtiles

pytestmark = pytest.mark.django_db

FEATURES = 500_000
# A grid of 40 ft buildings on 60 ft centres, about 707 across, near Accra.
ACROSS = 707
X0, Y0, STEP = 1150000, 310000, 60
TARGETS = {"tile": 0.5, "tile_14": 1.0, "page": 1.5, "package": 5.0, "pull": 2.0, "relations": 30.0}


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


def timed(call: Callable[[], Any]) -> tuple[Any, float]:
    start = time.perf_counter()
    result = call()
    return result, round(time.perf_counter() - start, 3)


@pytest.mark.slow
def test_a_district_with_half_a_million_features(planner, district_a):
    project = planner.post(reverse("project-list"), {"name": "Load"}, format="json").json()
    schema = [{"name": "property_id", "type": "text"}]
    body = {
        "project": project["id"],
        "name": "Buildings",
        "geometry_type": "polygon",
        "schema": schema,
    }
    layer = planner.post(reverse("layer-list"), body, format="json").json()
    with connection.cursor() as cursor:
        # Bulk load without one audit row per feature (an import of this size
        # would be audited; loading it isn't what is being timed).
        # A table can't be altered while it has checks waiting for the end of
        # the transaction, so they run as each statement finishes.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE projects_feature DISABLE TRIGGER projects_feature_audit")
        cursor.execute(
            """
            INSERT INTO projects_feature
                (district_id, layer_id, uuid, properties, version, origin, verified,
                 created_at, updated_at, geom_native, geom_4326)
            SELECT %(district)s, %(layer)s, gen_random_uuid(),
                   jsonb_build_object('property_id', 'B-' || i),
                   1, 'import', false, now() - interval '1 day', now() - interval '1 day',
                   ST_SetSRID(ST_MakeEnvelope(x, y, x + 40, y + 40), 2136),
                   ST_Transform(ST_SetSRID(ST_MakeEnvelope(x, y, x + 40, y + 40), 2136), 4326)
            FROM (SELECT i, %(x0)s + (i %% %(across)s) * %(step)s AS x,
                         %(y0)s + (i / %(across)s) * %(step)s AS y
                  FROM generate_series(1, %(n)s) AS i) g
            """,
            {
                "district": district_a.id,
                "layer": layer["id"],
                "x0": X0,
                "y0": Y0,
                "across": ACROSS,
                "step": STEP,
                "n": FEATURES,
            },
        )
        cursor.execute("ALTER TABLE projects_feature ENABLE TRIGGER projects_feature_audit")
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        cursor.execute("ANALYZE projects_feature")
        # The middle of the grid, in degrees.
        cursor.execute(
            "SELECT ST_X(c), ST_Y(c) FROM (SELECT ST_Transform("
            "ST_SetSRID(ST_MakePoint(%s, %s), 2136), 4326) c) s",
            [X0 + ACROSS * STEP / 2, Y0 + ACROSS * STEP / 2],
        )
        lon, lat = cursor.fetchone()
    timings: dict[str, float] = {}

    # Map tiles where planners work.
    def tile(zoom: int) -> float:
        x, y = mbtiles.tile_xy(lon, lat, zoom)
        response, seconds = timed(
            lambda: planner.get(reverse("layer-tile", args=[layer["id"], zoom, x, y]))
        )
        assert response.status_code == 200
        return seconds

    timings["tile_14"] = tile(14)
    timings["tile"] = max(tile(zoom) for zoom in (15, 16, 17))

    # A page of features inside a map view about 600 m across.
    d = 0.003
    url = reverse("layer-features", args=[layer["id"]])
    params = {"bbox": f"{lon - d},{lat - d},{lon + d},{lat + d}", "limit": 1000}
    response, timings["page"] = timed(lambda: planner.get(url, params))
    page = response.json()
    assert 500 < page["numberMatched"] < 5000 and page["numberReturned"] == 1000

    # A planning area about 1 km across: what a field officer downloads.
    side = 3300  # feet
    cx, cy = X0 + ACROSS * STEP / 2, Y0 + ACROSS * STEP / 2
    ring = [[cx, cy], [cx + side, cy], [cx + side, cy + side], [cx, cy + side], [cx, cy]]
    area = planner.put(
        reverse("project-boundary", args=[project["id"]]),
        {"geometry": {"type": "Polygon", "coordinates": [ring]}, "method": "coordinates"},
        format="json",
    )
    assert area.status_code == 200, area.content
    response, timings["package"] = timed(
        lambda: planner.get(reverse("project-field-package", args=[project["id"]]))
    )
    package = response.json()
    assert 2500 < package["feature_total"] < 4000  # only the planning area, not the district

    # One edit, then what a device pulls.
    first = package["features"][str(layer["id"])][0]
    edited = planner.patch(
        reverse("feature-detail", args=[first["id"]]),
        {"version": 1, "properties": {"property_id": "edited"}},
        format="json",
    )
    assert edited.status_code == 200
    since = package["generated_at"]
    response, timings["pull"] = timed(
        lambda: planner.get(reverse("sync-pull"), {"project": project["id"], "since": since})
    )
    # The pull looks a few seconds further back than asked, so the planning
    # area drawn just before the package comes too; of the buildings, only the edit.
    pulled = [f for f in response.json()["features"] if f["layer"] == layer["id"]]
    assert [f["properties"]["property_id"] for f in pulled] == ["edited"]

    # Relationships: a flood-prone area over part of the district.
    flood = planner.post(
        reverse("layer-list"),
        {"project": project["id"], "name": "Flood zones", "geometry_type": "polygon", "schema": []},
        format="json",
    ).json()
    planner.post(
        reverse("layer-features", args=[flood["id"]]),
        {"geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {}},
        format="json",
    )
    roles = [
        {"role": "properties", "layer": layer["id"]},
        {"role": "flood_risk", "layer": flood["id"]},
    ]
    planner.put(
        reverse("project-layer-roles", args=[project["id"]]), {"roles": roles}, format="json"
    )
    response, timings["relations"] = timed(
        lambda: planner.post(reverse("project-relations-run", args=[project["id"]]))
    )
    assert response.status_code == 201, response.content
    totals = response.json()["summary"]["project"]
    assert totals["properties"] == FEATURES and 2500 < totals["in_flood_area"] < 4000

    print("load timings (s):", timings, "targets:", TARGETS)
    slow = {
        name: (seconds, TARGETS[name])
        for name, seconds in timings.items()
        if seconds > TARGETS[name]
    }
    assert not slow, f"over target (measured, target): {slow}"

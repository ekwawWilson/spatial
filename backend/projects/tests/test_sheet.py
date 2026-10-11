# ruff: noqa: E501 - long assertions read better on one line
"""Plan sheets: the project drawn to a true scale in its own grid."""

import pytest
from django.urls import reverse

from core.models import Role
from projects import sheet
from relations.tests.test_relations import admin, planner, world  # noqa: F401

pytestmark = pytest.mark.django_db


def test_scales_and_intervals_are_round():
    # A3 landscape: the frame is the page less the margins and the panel.
    assert sheet.frame_mm("A3") == (324.0, 277.0)
    # 2 km square, in metres: 1:5,000 needs 400 mm; 1:10,000 fits.
    assert sheet.fit_scale((0, 0, 2000, 2000), 1.0, "A3") == 10000
    # The same ground in Gold Coast feet picks the same scale.
    foot = 0.3047997101815088
    assert sheet.fit_scale((0, 0, 2000 / foot, 2000 / foot), foot, "A3") == 10000
    assert sheet.fit_scale((0, 0, 200, 150), 1.0, "A1") == 500
    assert [sheet._round_interval(v) for v in (0.7, 3, 40, 130, 600)] == [
        1.0,
        5.0,
        50.0,
        200.0,
        1000.0,
    ]
    assert [
        kind
        for kind, _parts in sheet._rings(
            {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "Point", "coordinates": [1, 2]},
                    {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]},
                ],
            }
        )
    ] == ["point", "area"]


def test_a_plan_sheet_of_the_project(world, api, members_a, district_a, district_b, make_member):  # noqa: F811
    """Gate: the sheet prints at the scale that fits, or the one asked for."""
    planner = world.client  # noqa: F811
    url = reverse("project-sheet", args=[world.project])
    printed = planner.get(url)
    assert printed.status_code == 200, printed.content
    assert printed["Content-Type"] == "application/pdf" and printed.content.startswith(b"%PDF")
    # The fixture community spans 2 km: 1:10,000 is the largest standard scale that fits A3.
    assert printed["X-Sheet-Scale"] == "10000" and len(printed.content) > 3000
    assert planner.get(url, {"paper": "a1"})["X-Sheet-Scale"] == "5000"

    asked = planner.get(url, {"scale": "2500", "title": "Kasoa Local Plan: base map"})
    assert asked.status_code == 200 and asked["X-Sheet-Scale"] == "2500"
    assert b"Kasoa Local Plan" in asked.content  # the document's title
    assert planner.get(url, {"paper": "B5"}).status_code == 400
    assert planner.get(url, {"scale": "big"}).status_code == 400
    assert planner.get(url, {"scale": "10"}).status_code == 400

    # Everyone who may see the project may print it; other districts may not.
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(url).status_code == 200
    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert other.get(url).status_code == 404

    # An empty project has nothing to print, and says so.
    empty = planner.post(reverse("project-list"), {"name": "Empty"}, format="json").json()
    nothing = planner.get(reverse("project-sheet", args=[empty["id"]]))
    assert nothing.status_code == 400 and "nothing to draw" in str(nothing.json())

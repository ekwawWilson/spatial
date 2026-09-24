"""Traverse computation (gate: closure error on a known survey example)."""

import math

import pytest
from django.core.exceptions import ValidationError

from projects.traverse import compute, parse_bearing, to_polygon


@pytest.mark.parametrize(
    "text,degrees",
    [
        (45, 45.0),
        ("123.5", 123.5),
        ("123 30 00", 123.5),
        ("123°30'00\"", 123.5),
        ("N 45 30 00 E", 45.5),
        ("S 45 30 00 E", 134.5),
        ("S 45 30 00 W", 225.5),
        ("N 45 30 00 W", 314.5),
        ("n 10 e", 10.0),
        ("360", 0.0),
    ],
)
def test_bearing_formats(text, degrees):
    assert parse_bearing(text) == pytest.approx(degrees)


@pytest.mark.parametrize("bad", ["N 95 E", "12 75 00", "abc", "400"])
def test_bad_bearings(bad):
    with pytest.raises(ValueError):
        parse_bearing(bad)


def test_perfect_square_closes_exactly():
    result = compute((1000.0, 2000.0), [(0, 100), (90, 100), (180, 100), (270, 100)])
    assert result.misclosure == pytest.approx(0, abs=1e-9)
    assert result.accuracy_ratio is None
    assert result.perimeter == pytest.approx(400)


# A closed five-leg survey of a parcel (grid bearings, distances in feet),
# built from a known polygon so the true misclosure is known exactly: the
# distance of the fourth leg was booked 0.30 ft too long.
TRUE_CORNERS = [(0.0, 0.0), (0.0, 500.0), (400.0, 800.0), (800.0, 500.0), (800.0, 0.0)]


def legs_of(corners, error_on_leg=None, error=0.0):
    legs = []
    for i, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1], strict=True)):
        de, dn = b[0] - a[0], b[1] - a[1]
        bearing = math.degrees(math.atan2(de, dn)) % 360
        distance = math.hypot(de, dn) + (error if i == error_on_leg else 0.0)
        legs.append((bearing, distance))
    return legs


def test_known_survey_misclosure_and_accuracy_ratio():
    legs = legs_of(TRUE_CORNERS, error_on_leg=3, error=0.30)  # leg 4 runs due south
    result = compute(TRUE_CORNERS[0], legs)
    perimeter = 500 + 500 + 500 + 500 + 800 + 0.30
    assert result.perimeter == pytest.approx(perimeter)
    # Leg 4 bears 180°, so the extra 0.30 ft shows up entirely as -0.30 N.
    assert result.misclosure_e == pytest.approx(0.0, abs=1e-9)
    assert result.misclosure_n == pytest.approx(-0.30, abs=1e-9)
    assert result.misclosure == pytest.approx(0.30, abs=1e-9)
    assert result.accuracy_ratio == pytest.approx(perimeter / 0.30)  # about 1 in 9,334


def test_bowditch_closes_and_distributes_by_distance():
    legs = legs_of(TRUE_CORNERS, error_on_leg=3, error=0.30)
    result = compute(TRUE_CORNERS[0], legs, adjust=True)
    assert result.adjusted
    assert result.stations[-1] == TRUE_CORNERS[0]  # closes exactly
    perimeter = result.perimeter
    # Correction at each station = misclosure x (distance so far / perimeter).
    travelled = 0.0
    for (_, distance), (ce, cn) in zip(legs, result.corrections[1:], strict=True):
        travelled += distance
        assert ce == pytest.approx(0.0, abs=1e-9)
        assert cn == pytest.approx(0.30 * travelled / perimeter, abs=1e-9)
    # Adjusted corners move towards the truth.
    for adjusted, true in zip(result.stations[1:4], TRUE_CORNERS[1:4], strict=True):
        assert math.dist(adjusted, true) < 0.30


def test_scale_factor_converts_ground_to_grid():
    ground = compute(
        (0.0, 0.0), [(0, 1000), (90, 1000), (180, 1000), (270, 1000)], scale_factor=0.99975
    )
    assert ground.perimeter == pytest.approx(4000 * 0.99975)


def test_polygon_output_is_closed():
    result = compute((0.0, 0.0), [(0, 10), (90, 10), (180, 10), (270, 10)])
    ring = to_polygon(result)["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5


@pytest.mark.parametrize(
    "legs,message",
    [
        ([(0, 10), (90, 10)], "at least three legs"),
        ([(0, 10), (90, -1), (180, 10)], "Leg 2: the distance"),
        ([(0, 10), ("N 95 E", 10), (180, 10)], "Leg 2"),
    ],
)
def test_bad_traverses_explain_themselves(legs, message):
    with pytest.raises(ValidationError, match=message):
        compute((0.0, 0.0), legs)

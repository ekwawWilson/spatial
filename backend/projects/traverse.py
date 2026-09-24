"""Bearing-and-distance traverses (how surveyors record boundaries).

Computes the stations of a closed traverse from a starting point, reports its
misclosure and accuracy ratio, and optionally applies the Bowditch (compass
rule) adjustment, which distributes the misclosure in proportion to distance.

Bearings are grid bearings clockwise from north, in any of these forms:
    123.5            decimal degrees (whole-circle bearing)
    "123 30 00"      degrees minutes seconds
    "123°30'00\\""    degrees minutes seconds with symbols
    "N 56 30 E"      quadrant bearing (N/S, angle, E/W)
Distances are in the units of the project's coordinate system (e.g. Gold
Coast feet for EPSG:2136). Survey distances measured on the ground can be
reduced to grid distances with `scale_factor` (grid = ground x factor).
"""

import math
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_ALLOWED = re.compile(r"^[\d.\s°'′\"″dms]+$")
_QUADRANT = re.compile(r"^\s*(?P<ns>[NS])\s*(?P<angle>.+?)\s*(?P<ew>[EW])\s*$", re.IGNORECASE)


def parse_angle(text: str) -> float:
    """Degrees from '123.5', '123 30 15' or '123°30'15"'."""
    parts = _NUMBER.findall(text)
    if not text.strip() or not _ALLOWED.match(text.strip()) or not 1 <= len(parts) <= 3:
        raise ValueError(f"can't read the angle {text!r}")
    degrees, minutes, seconds = (float(p) for p in [*parts, "0", "0"][:3])
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"minutes and seconds must be under 60 in {text!r}")
    return degrees + minutes / 60 + seconds / 3600


def parse_bearing(value: str | float) -> float:
    """Whole-circle bearing in degrees [0, 360) from any supported form."""
    if isinstance(value, int | float):
        bearing = float(value)
    else:
        quadrant = _QUADRANT.match(value)
        if quadrant:
            angle = parse_angle(quadrant["angle"])
            if angle > 90:
                raise ValueError(f"a quadrant bearing's angle can't exceed 90° ({value!r})")
            ns, ew = quadrant["ns"].upper(), quadrant["ew"].upper()
            bearing = {
                ("N", "E"): angle,
                ("S", "E"): 180 - angle,
                ("S", "W"): 180 + angle,
                ("N", "W"): 360 - angle,
            }[(ns, ew)]
        else:
            bearing = parse_angle(value)
    if not 0 <= bearing <= 360:
        raise ValueError(f"a bearing must be between 0 and 360 degrees, got {bearing}")
    return bearing % 360


@dataclass
class TraverseResult:
    stations: list[tuple[float, float]]  # first == start; closed traverses end at the start
    raw_end: tuple[float, float]  # where the unadjusted traverse ended
    misclosure_e: float
    misclosure_n: float
    misclosure: float  # linear, in CRS units
    perimeter: float  # sum of leg lengths, CRS units
    accuracy_ratio: float | None  # 1 : ratio (None when the misclosure is zero)
    adjusted: bool
    corrections: list[tuple[float, float]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "stations": [list(s) for s in self.stations],
            "raw_end": list(self.raw_end),
            "misclosure_e": self.misclosure_e,
            "misclosure_n": self.misclosure_n,
            "misclosure": self.misclosure,
            "perimeter": self.perimeter,
            "accuracy_ratio": self.accuracy_ratio,
            "adjusted": self.adjusted,
            "corrections": [list(c) for c in self.corrections],
        }


def compute(
    start: tuple[float, float],
    legs: list[tuple[str | float, float]],
    *,
    adjust: bool = False,
    scale_factor: float = 1.0,
) -> TraverseResult:
    """Runs a closed traverse: legs should return to `start`.

    Each leg is (bearing, distance). Returns the stations (adjusted when
    `adjust`) plus the misclosure, which is how far the last leg ends from the
    start, and the accuracy ratio perimeter / misclosure (surveyors quote
    "1 in 10,000" and better for boundary work).
    """
    if len(legs) < 3:
        raise ValidationError("A closed boundary needs at least three legs.")
    if not 0.9 <= scale_factor <= 1.1:
        raise ValidationError("The scale factor must be close to 1 (between 0.9 and 1.1).")
    e, n = float(start[0]), float(start[1])
    raw = [(e, n)]
    deltas = []
    perimeter = 0.0
    for i, (bearing_text, distance) in enumerate(legs, start=1):
        try:
            bearing = math.radians(parse_bearing(bearing_text))
        except ValueError as exc:
            raise ValidationError(f"Leg {i}: {exc}.") from exc
        if not (isinstance(distance, int | float) and distance > 0):
            raise ValidationError(f"Leg {i}: the distance must be a positive number.")
        grid = float(distance) * scale_factor
        de, dn = grid * math.sin(bearing), grid * math.cos(bearing)
        deltas.append((de, dn, grid))
        perimeter += grid
        e, n = e + de, n + dn
        raw.append((e, n))
    misclosure_e = raw[-1][0] - raw[0][0]
    misclosure_n = raw[-1][1] - raw[0][1]
    misclosure = math.hypot(misclosure_e, misclosure_n)
    ratio = perimeter / misclosure if misclosure > 1e-9 else None

    stations = raw
    corrections: list[tuple[float, float]] = []
    if adjust and misclosure > 0:
        # Bowditch: correction at each station proportional to the distance
        # travelled so far, so the last station lands exactly on the start.
        stations = [raw[0]]
        corrections = [(0.0, 0.0)]
        e, n = raw[0]
        travelled = 0.0
        for de, dn, length in deltas:
            travelled += length
            ce = -misclosure_e * travelled / perimeter
            cn = -misclosure_n * travelled / perimeter
            corrections.append((ce, cn))
            e, n = e + de, n + dn
            stations.append((e + ce, n + cn))
        stations[-1] = raw[0]  # exact closure (removes floating-point residue)
    return TraverseResult(
        stations=stations,
        raw_end=raw[-1],
        misclosure_e=misclosure_e,
        misclosure_n=misclosure_n,
        misclosure=misclosure,
        perimeter=perimeter,
        accuracy_ratio=ratio,
        adjusted=adjust and misclosure > 0,
        corrections=corrections,
    )


def to_polygon(result: TraverseResult) -> dict[str, object]:
    """GeoJSON polygon of a traverse (closing it to the start if needed)."""
    ring = [list(p) for p in result.stations]
    # A traverse that closes within floating-point noise ends on its start.
    if math.dist(ring[0], ring[-1]) <= 1e-9 * max(1.0, result.perimeter):
        ring[-1] = ring[0]
    else:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}

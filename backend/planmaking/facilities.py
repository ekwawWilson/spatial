# ruff: noqa: E501 - the standards read better one to a line
"""The facilities a planning area has against what the national planning
standards ask for its population: how many of each, and how many buildings
lie beyond the walking distance to the nearest. Revised Zoning Guidelines
and Planning Standards (LUSPA, 2025); L.I. 2384 r.24(1)(b), the "basic
social services requirements" a local plan specifies.

Facilities are the features of the project's "facilities" layer, sorted by
the words in their type field (school, clinic, market...). The population
is given, or summed from the "population" layer, or estimated from the
number of buildings."""

import math
import re
from dataclasses import dataclass
from typing import Any

from django.db import connection

from projects.models import PlanProject
from relations import procedures
from relations import services as relations

M2_PER_ACRE = 4046.86
PERSONS_PER_BUILDING = 5.0  # the default estimate, when no population is known


@dataclass(frozen=True)
class Standard:
    code: str
    label: str
    section: str
    # One facility for this many people (None: no number set).
    per: int | None
    # The farthest a home should be from one, in metres (None: no distance set).
    walk_m: int | None
    # Land for it, in acres per 1,000 people (None: no area set).
    acres_per_1000: float | None
    # Words in a facility's type that make it one of these. The first matching
    # standard wins, so the specific come before the general.
    words: tuple[str, ...]


STANDARDS: tuple[Standard, ...] = (
    Standard(
        "nursery",
        "Nursery or kindergarten",
        "3.1.1.2(a)",
        None,
        1250,
        None,
        ("nursery", "kindergarten", "kg", "pre-school", "preschool"),
    ),
    Standard("jhs", "Junior High School", "3.1.1.2(c)", 10_000, 3200, None, ("jhs", "junior high")),
    Standard(
        "shs",
        "Senior High or Technical School",
        "3.2",
        20_000,
        None,
        None,
        ("shs", "senior high", "secondary", "technical", "vocational", "college"),
    ),
    Standard(
        "primary", "Primary school", "3.1.1.2(b)", 5_000, 2500, None, ("primary", "basic", "school")
    ),
    Standard("chps", "CHPS compound", "5.9", 5_000, None, None, ("chps",)),
    Standard("polyclinic", "Polyclinic", "5.9", 50_000, None, None, ("polyclinic",)),
    Standard("hospital", "District hospital", "5.9", 200_000, None, None, ("hospital",)),
    Standard(
        "health_centre",
        "Health centre or clinic",
        "5.9",
        15_000,
        None,
        None,
        ("health", "clinic", "maternity", "doctors"),
    ),
    Standard("market", "Local market", "6.5.1", 30_000, None, None, ("market", "marketplace")),
    Standard(
        "shopping",
        "Neighbourhood shopping centre",
        "6.5.4",
        15_000,
        None,
        None,
        ("shopping", "mall"),
    ),
    Standard(
        "sports",
        "Local sports field",
        "7.1.1.2",
        5_000,
        None,
        1.0,
        ("sport", "pitch", "football", "stadium", "playing field"),
    ),
    Standard(
        "park",
        "Park or public garden",
        "7.1.2.1",
        None,
        None,
        1.2,
        ("park", "garden", "open space"),
    ),
    Standard("borehole", "Borehole", "13.3.5", 300, None, None, ("borehole", "well")),
    Standard(
        "standpipe",
        "Public standpipe",
        "13.3.3",
        100,
        400,
        None,
        ("standpipe", "stand pipe", "tap", "water point"),
    ),
    Standard("fire", "Fire station or post", "14.3.2", 35_000, None, None, ("fire",)),
    Standard(
        "waste",
        "Waste collection point",
        "13.2.3.1",
        1_000,
        500,
        None,
        ("waste", "refuse", "collection point", "dump", "skip"),
    ),
)
STANDARD_BY_CODE = {s.code: s for s in STANDARDS}
SOURCE = "Revised Zoning Guidelines and Planning Standards (LUSPA, 2025)"


def classify(text: Any) -> str | None:
    """Which standard a facility's type is, if any."""
    value = str(text or "").lower()
    if not value:
        return None
    for standard in STANDARDS:
        for word in standard.words:
            if re.search(rf"\b{re.escape(word)}", value):
                return standard.code
    return None


def _rows(sql: str, params: list[Any]) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def population(
    project: PlanProject, given: float | None, per_building: float | None
) -> dict[str, Any]:
    """The people the facilities serve, and where the figure came from."""
    if given is not None:
        return {"value": round(given), "source": "given"}
    roles = relations.roles_of(project)
    if "population" in roles:
        role = roles["population"]
        field = str(role.config.get("population_field", "population"))
        total = 0.0
        found = False
        for (props,) in _rows(
            "SELECT properties FROM projects_feature WHERE layer_id = %s", [role.layer_id]
        ):
            value = procedures._obj(props).get(field)
            if value in (None, ""):
                continue
            try:
                total += float(str(value))
                found = True
            except (TypeError, ValueError):
                continue
        if found:
            return {"value": round(total), "source": f"the {role.layer.name} layer"}
    if "properties" in roles:
        per = per_building if per_building is not None else PERSONS_PER_BUILDING
        count = roles["properties"].layer.features.count()
        return {
            "value": round(count * per),
            "source": f"estimated: {count} buildings × {per:g} people",
            "estimate": True,
        }
    return {"value": None, "source": "unknown"}


def check(
    project: PlanProject, given: float | None = None, per_building: float | None = None
) -> dict[str, Any]:
    roles = relations.roles_of(project)
    people = population(project, given, per_building)
    if "facilities" not in roles:
        return {
            "population": people,
            "facilities_layer": None,
            "results": [],
            "unclassified": [],
            "source": SOURCE,
        }
    role = roles["facilities"]
    type_field = str(role.config.get("type_field", "type"))
    by_code: dict[str, list[tuple[int, float]]] = {s.code: [] for s in STANDARDS}
    unclassified: dict[str, int] = {}
    for pk, props, area in _rows(
        "SELECT id, properties, CASE WHEN ST_Dimension(geom_4326) = 2"
        " THEN ST_Area(geom_4326::geography) ELSE 0 END"
        " FROM projects_feature WHERE layer_id = %s AND geom_4326 IS NOT NULL",
        [role.layer_id],
    ):
        value = procedures._obj(props).get(type_field)
        code = classify(value)
        if code is None:
            label = str(value or "(no type)")
            unclassified[label] = unclassified.get(label, 0) + 1
        else:
            by_code[code].append((pk, float(area or 0)))

    homes = roles.get("properties")
    total_homes = homes.layer.features.count() if homes else 0
    pop = people["value"]
    results = []
    for standard in STANDARDS:
        have = by_code[standard.code]
        need = math.ceil(pop / standard.per) if pop and standard.per else None
        row: dict[str, Any] = {
            "code": standard.code,
            "label": standard.label,
            "section": standard.section,
            "per": standard.per,
            "have": len(have),
            "need": need,
            "short": max(0, need - len(have)) if need is not None else None,
            "walk_m": standard.walk_m,
            "beyond": None,
            "acres_need": None,
            "acres_have": None,
        }
        if standard.acres_per_1000 is not None and pop:
            row["acres_need"] = round(pop / 1000 * standard.acres_per_1000, 1)
            row["acres_have"] = round(sum(a for _, a in have) / M2_PER_ACRE, 1)
        if standard.walk_m is not None and homes is not None and total_homes:
            ids = [pk for pk, _ in have]
            if not ids:
                row["beyond"] = total_homes
            else:
                reach = float(standard.walk_m)
                (beyond,) = _rows(
                    "SELECT count(*) FROM projects_feature p WHERE p.layer_id = %s"
                    " AND p.geom_4326 IS NOT NULL AND NOT EXISTS ("
                    " SELECT 1 FROM projects_feature f WHERE f.id = ANY(%s)"
                    " AND f.geom_4326 && ST_Expand(p.geom_4326, %s)"
                    " AND ST_DWithin(p.geom_4326::geography, f.geom_4326::geography, %s))",
                    [homes.layer_id, ids, procedures._degrees(reach), reach],
                )[0]
                row["beyond"] = int(beyond)
        short = (
            bool(row["short"])
            or bool(row["beyond"])
            or (row["acres_need"] is not None and row["acres_have"] < row["acres_need"])
        )
        row["status"] = (
            "short"
            if short
            else ("met" if need or row["walk_m"] or row["acres_need"] else "unknown")
        )
        results.append(row)
    return {
        "population": people,
        "facilities_layer": {
            "id": role.layer_id,
            "name": role.layer.name,
            "type_field": type_field,
        },
        "homes": total_homes,
        "results": results,
        "unclassified": [{"type": k, "count": v} for k, v in sorted(unclassified.items())],
        "source": SOURCE,
    }

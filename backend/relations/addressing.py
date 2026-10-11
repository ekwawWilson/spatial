"""Street addressing: a code for every street, and a number for every
property from where it stands along its street. L.I. 2384 r.28 has Assemblies
follow the National Street Naming and Property Numbering Operational Manual.

The numbering here is the distance convention street-addressing programmes
use: a property's number comes from its distance from the start of the
street, odd on one side and even on the other, so a number says roughly how
far along the street the property is and new buildings fit in between
without renumbering. The interval (ten metres, one metre, or simply one after
another), which side is odd, and where each street starts are settings, to be
set to the national manual's rules for the district.

Nothing changes on the map until a proposal is applied.
"""

import json
import math
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction

from core.models import User
from projects import schema as schema_rules
from projects.models import Layer, PlanProject

from . import procedures

METHODS = {
    "decametric": ("By distance, every 10 m", 10.0),
    "metric": ("By distance, every metre", 1.0),
    "sequential": ("One after another along the street", None),
}
NUMBER_FIELD = {"name": "house_no", "label": "Property number", "type": "text", "required": False}
STREET_FIELD = {"name": "street", "label": "Street", "type": "text", "required": False}
CODE_FIELD = {"name": "street_code", "label": "Street code", "type": "text", "required": False}
MAX_ROWS = 20_000


def _letters(n: int) -> str:
    """0 -> "", 1 -> "A", 2 -> "B", ... for properties that share a number."""
    out = ""
    while n > 0:
        n, rest = divmod(n - 1, 26)
        out = chr(65 + rest) + out
    return out


def number_for(distance_m: float, odd: bool, interval_m: float) -> int:
    """The number at a distance along the street: about distance / interval,
    with the parity of the property's side."""
    pair = math.floor(max(0.0, distance_m) / interval_m / 2)
    return 2 * pair + (1 if odd else 2)


def _placed(roles: procedures.Roles) -> list[dict[str, Any]]:
    """Each property with the street it is on: how far along the street it
    stands (from the end the street was drawn from), on which side, and the
    street's length."""
    properties, streets = roles["properties"], roles["streets"]
    reach = procedures._number(streets.config, "located_on_max_m", procedures.LOCATED_ON_MAX_M)
    sql = (
        "WITH nearest AS ("
        " SELECT s.id AS pid, s.properties AS pprops, ST_Centroid(s.geom_4326) AS centre,"
        "  n.id AS sid, n.properties AS sprops, n.line, n.dist"
        " FROM projects_feature s CROSS JOIN LATERAL ("
        "  SELECT o.id, o.properties, ST_GeometryN(ST_LineMerge(o.geom_4326), 1) AS line,"
        "   ST_Distance(s.geom_4326::geography, o.geom_4326::geography) AS dist"
        "  FROM projects_feature o WHERE o.layer_id = %s"
        "  AND o.geom_4326 && ST_Expand(s.geom_4326, %s)"
        "  AND ST_DWithin(s.geom_4326::geography, o.geom_4326::geography, %s)"
        "  ORDER BY dist, o.id LIMIT 1) n"
        " WHERE s.layer_id = %s AND s.geom_4326 IS NOT NULL),"
        " along AS ("
        " SELECT *, ST_LineLocatePoint(line, centre) AS fraction FROM nearest"
        " WHERE GeometryType(line) = 'LINESTRING')"
        " SELECT pid, pprops, sid, sprops, dist, fraction, ST_Length(line::geography),"
        "  ST_Azimuth(ST_LineInterpolatePoint(line, GREATEST(fraction - 0.001, 0)),"
        "             ST_LineInterpolatePoint(line, LEAST(fraction + 0.001, 1))),"
        "  ST_Azimuth(ST_LineInterpolatePoint(line, fraction), centre),"
        "  ST_X(ST_StartPoint(line)), ST_Y(ST_StartPoint(line)),"
        "  ST_X(ST_EndPoint(line)), ST_Y(ST_EndPoint(line))"
        " FROM along ORDER BY sid, fraction, pid LIMIT %s"
    )
    params = [
        streets.layer_id,
        procedures._degrees(reach),
        reach,
        properties.layer_id,
        MAX_ROWS + 1,
    ]
    out: list[dict[str, Any]] = []
    for row in procedures._rows(sql, params):
        pid, pprops, sid, sprops, dist, fraction, length, heading, bearing, x0, y0, x1, y1 = row
        # Bearings run clockwise from north: a property to the right of the
        # direction of travel bears between 0 and 180 degrees more than the street.
        turn = ((bearing or 0.0) - (heading or 0.0)) % (2 * math.pi)
        out.append(
            {
                "property": pid,
                "pprops": procedures._obj(pprops),
                "street": sid,
                "sprops": procedures._obj(sprops),
                "off_street_m": float(dist),
                "along_m": float(fraction) * float(length),
                "length_m": float(length),
                "right": 0 < turn < math.pi,
                "start": (x0, y0),
                "end": (x1, y1),
            }
        )
    return out


def propose(
    project: PlanProject,
    roles: procedures.Roles,
    *,
    method: str = "decametric",
    odd_side: str = "left",
    start_near: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Street codes and property numbers, as they would be: nothing is saved.

    `start_near` (longitude, latitude): each street is numbered from the end
    nearer that place (the town centre, say). Without it, from the end the
    street was drawn from."""
    if method not in METHODS:
        raise ValidationError({"method": [f"One of {', '.join(METHODS)}."]})
    if odd_side not in ("left", "right"):
        raise ValidationError({"odd_side": ["left or right."]})
    missing = [r for r in ("properties", "streets") if r not in roles]
    if missing:
        raise ValidationError(
            "Say which layers hold the properties and the streets first (Relationships, Layers)."
        )
    properties, streets = roles["properties"], roles["streets"]
    name_field = streets.config.get("name_field", "name")
    code_field = streets.config.get("code_field", CODE_FIELD["name"])
    id_field = properties.config.get("id_field", "property_id")
    number_field = properties.config.get("number_field", NUMBER_FIELD["name"])
    interval = METHODS[method][1]

    # --- Street codes: kept where a street has one, the next free numbers for the rest --------
    street_rows = list(
        streets.layer.features.order_by("id").values_list("id", "properties")[:MAX_ROWS]
    )
    prefix = project.district.code
    taken = {str(p.get(code_field)) for _id, p in street_rows if p.get(code_field)}
    n = 0
    codes: dict[int, str] = {}
    new_codes: dict[int, str] = {}
    for sid, props in sorted(street_rows, key=lambda r: (str(r[1].get(name_field) or "~"), r[0])):
        code = props.get(code_field)
        if not code:
            while True:
                n += 1
                code = f"{prefix}-{n:03d}"
                if code not in taken:
                    break
            taken.add(code)
            new_codes[sid] = code
        codes[sid] = str(code)

    # --- Property numbers ----------------------------------------------------------------------
    placed = _placed(roles)
    truncated = len(placed) > MAX_ROWS
    by_street: dict[int, list[dict[str, Any]]] = {}
    for row in placed[:MAX_ROWS]:
        by_street.setdefault(row["street"], []).append(row)
    rows: list[dict[str, Any]] = []
    for sid, members in by_street.items():
        first = members[0]
        reverse = False
        if start_near is not None:
            lon, lat = start_near
            to_start = math.hypot(first["start"][0] - lon, first["start"][1] - lat)
            to_end = math.hypot(first["end"][0] - lon, first["end"][1] - lat)
            reverse = to_end < to_start
        for row in members:
            row["distance_m"] = row["length_m"] - row["along_m"] if reverse else row["along_m"]
            # Turned round, left and right swap.
            right = (not row["right"]) if reverse else row["right"]
            row["side"] = "right" if right else "left"
            row["odd"] = row["side"] == odd_side
        members.sort(key=lambda r: (r["distance_m"], r["property"]))
        used: dict[int, int] = {}
        rank = {True: 0, False: 0}
        for row in members:
            if interval is None:
                rank[row["odd"]] += 1
                number = 2 * rank[row["odd"]] - (1 if row["odd"] else 0)
            else:
                number = number_for(row["distance_m"], row["odd"], interval)
            used[number] = used.get(number, 0) + 1
            suffix = _letters(used[number] - 1)
            street_name = str(row["sprops"].get(name_field) or "")
            text = f"{number}{suffix}"
            rows.append(
                {
                    "property": row["property"],
                    "label": str(row["pprops"].get(id_field) or f"#{row['property']}"),
                    "street": sid,
                    "street_name": street_name,
                    "street_code": codes.get(sid, ""),
                    "side": row["side"],
                    "distance_m": round(row["distance_m"], 1),
                    "off_street_m": round(row["off_street_m"], 1),
                    "number": text,
                    "address": f"{text} {street_name}".strip(),
                    "current": str(row["pprops"].get(number_field) or ""),
                }
            )
    rows.sort(key=lambda r: (r["street_name"], r["street"], r["distance_m"], r["property"]))
    total = properties.layer.features.count()
    return {
        "method": method,
        "method_label": METHODS[method][0],
        "odd_side": odd_side,
        "start_near": list(start_near) if start_near else None,
        "streets": len(street_rows),
        "streets_without_a_name": sum(1 for _id, p in street_rows if not p.get(name_field)),
        "new_street_codes": [
            {"street": sid, "code": code}
            for sid, code in sorted(new_codes.items(), key=lambda i: i[1])
        ],
        "properties": total,
        "numbered": len(rows),
        # Too far from any street to be given an address on it.
        "without_a_street": max(0, total - len(rows)) if not truncated else None,
        "changes": sum(1 for r in rows if r["current"] != r["number"]),
        "truncated": truncated,
        "rows": rows,
    }


def _ensure_field(layer: Layer, field: dict[str, Any]) -> None:
    if any(f.get("name") == field["name"] for f in layer.schema):
        return
    layer.schema = schema_rules.validate_schema([*layer.schema, field])
    layer.save(update_fields=["schema"])


def apply(
    project: PlanProject, roles: procedures.Roles, proposal: dict[str, Any], user: User
) -> dict[str, int]:
    """Writes a proposal to the map: each street's code, and each property's
    number and street. Only values that change are written (one audited
    change each)."""
    properties, streets = roles["properties"], roles["streets"]
    code_field = streets.config.get("code_field", CODE_FIELD["name"])
    number_field = properties.config.get("number_field", NUMBER_FIELD["name"])
    street_field = properties.config.get("street_field", STREET_FIELD["name"])
    with transaction.atomic():
        _ensure_field(streets.layer, {**CODE_FIELD, "name": code_field})
        _ensure_field(properties.layer, {**NUMBER_FIELD, "name": number_field})
        _ensure_field(properties.layer, {**STREET_FIELD, "name": street_field})
        sql = (
            "UPDATE projects_feature SET properties = properties || %s::jsonb,"
            " version = version + 1, updated_at = now(), updated_by_id = %s"
            " WHERE id = %s AND layer_id = %s AND NOT properties @> %s::jsonb"
        )
        counts = {"streets": 0, "properties": 0}
        with connection.cursor() as cursor:
            for item in proposal["new_street_codes"]:
                values = json.dumps({code_field: item["code"]})
                cursor.execute(sql, [values, user.pk, item["street"], streets.layer_id, values])
                counts["streets"] += cursor.rowcount
            for row in proposal["rows"]:
                values = json.dumps({number_field: row["number"], street_field: row["street_name"]})
                cursor.execute(sql, [values, user.pk, row["property"], properties.layer_id, values])
                counts["properties"] += cursor.rowcount
    return counts

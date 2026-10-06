"""The procedures that work out links between features.

Each returns candidate links for one or more link types; relations.services
reconciles them with what is stored. Measurements (distances, areas, shares)
are made on the WGS 84 copy of each geometry as geography, so they are in
metres whatever CRS each layer is in. They are analysis values, not survey
quantities.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from django.db import connection

from projects.models import Feature

from .models import DevelopmentStandard, LayerRole, Relationship

# Defaults a role's config can override.
LOCATED_ON_MAX_M = 100.0
ACCESS_MAX_M = 30.0
DRAIN_MAX_M = 15.0
CATCHMENT_M = 1000.0
NEED_MATCH_M = 500.0
MIN_SHARE = 0.5  # a property "falls within" an area that covers at least half of it
SETBACK_TOLERANCE_M = 0.05

# Platform defaults, used where a district has set no standard at all.
PLATFORM_STANDARD = {"min_setback_m": 3.0, "max_floors": None, "max_coverage_pct": None}


@dataclass
class Candidate:
    type: str
    subject: int
    object: int | None
    method: str = Relationship.Method.CALCULATED
    confidence: float = 1.0
    rule: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, int, int | None, str]:
        return (self.type, self.subject, self.object, self.rule)


Roles = dict[str, LayerRole]
Scope = list[int] | None


def _rows(sql: str, params: list[Any]) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _obj(value: Any) -> dict[str, Any]:
    """A JSON column from a raw query: psycopg may hand it over as text."""
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def _scope(alias: str, scope: Scope, params: list[Any]) -> str:
    if scope is None:
        return ""
    params.append(scope)
    return f" AND {alias}.id = ANY(%s)"


def _degrees(metres: float) -> float:
    """A generous bounding-box margin in degrees for an index pre-filter."""
    return metres / 111_000 * 1.5


def _number(config: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# Share of the subject covered by the object: 1 for points and lines that touch it.
SHARE = (
    "CASE WHEN ST_Dimension(s.geom_4326) = 2 AND ST_Area(s.geom_4326::geography) > 0"
    " THEN ST_Area(ST_Intersection(s.geom_4326, o.geom_4326)::geography)"
    " / ST_Area(s.geom_4326::geography) ELSE 1 END"
)


def _best_container(
    subject_layer: int, object_layer: int, scope: Scope
) -> list[tuple[int, int, float]]:
    """For each subject, the object that covers most of it: (subject, object, share)."""
    params: list[Any] = [subject_layer, object_layer]
    scoped = _scope("s", scope, params)
    # Only constant fragments are joined; values are bound parameters.
    sql = (
        f"SELECT DISTINCT ON (s.id) s.id, o.id, {SHARE} AS share"  # noqa: S608
        " FROM projects_feature s JOIN projects_feature o"
        " ON ST_Intersects(s.geom_4326, o.geom_4326)"
        f" WHERE s.layer_id = %s AND o.layer_id = %s{scoped}"
        " ORDER BY s.id, share DESC, o.id"
    )
    return [(s, o, float(share)) for s, o, share in _rows(sql, params)]


def _nearest(
    subject_layer: int, object_layer: int, max_m: float, scope: Scope
) -> list[tuple[int, int, float]]:
    """For each subject, the nearest object within max_m: (subject, object, metres)."""
    params: list[Any] = [object_layer, _degrees(max_m), max_m, subject_layer]
    scoped = _scope("s", scope, params)
    sql = (
        "SELECT s.id, n.id, n.dist FROM projects_feature s CROSS JOIN LATERAL ("  # noqa: S608
        " SELECT o.id, ST_Distance(s.geom_4326::geography, o.geom_4326::geography) AS dist"
        " FROM projects_feature o WHERE o.layer_id = %s"
        " AND o.geom_4326 && ST_Expand(s.geom_4326, %s)"
        " AND ST_DWithin(s.geom_4326::geography, o.geom_4326::geography, %s)"
        " ORDER BY dist, o.id LIMIT 1) n"
        f" WHERE s.layer_id = %s AND s.geom_4326 IS NOT NULL{scoped}"
    )
    return [(s, o, float(dist)) for s, o, dist in _rows(sql, params)]


def _within_distance(
    subject_layer: int, object_layer: int, max_m: float, scope: Scope
) -> list[tuple[int, int, float]]:
    """Every (subject, object, metres) pair within max_m."""
    params: list[Any] = [_degrees(max_m), max_m, subject_layer, object_layer]
    scoped = _scope("s", scope, params)
    sql = (
        "SELECT s.id, o.id, ST_Distance(s.geom_4326::geography, o.geom_4326::geography)"  # noqa: S608
        " FROM projects_feature s JOIN projects_feature o"
        " ON o.geom_4326 && ST_Expand(s.geom_4326, %s)"
        " AND ST_DWithin(s.geom_4326::geography, o.geom_4326::geography, %s)"
        f" WHERE s.layer_id = %s AND o.layer_id = %s{scoped} ORDER BY s.id, o.id"
    )
    return [(s, o, float(dist)) for s, o, dist in _rows(sql, params)]


def _properties(layer_id: int, ids: set[int] | None = None) -> dict[int, dict[str, Any]]:
    qs = Feature.objects.filter(layer_id=layer_id)
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    return dict(qs.values_list("id", "properties"))


# --- 1. Containment ------------------------------------------------------------------------------


def containment(roles: Roles, scope: Scope) -> dict[str, list[Candidate]]:
    """Property belongs to community, falls within local and structure plans;
    community contains infrastructure."""
    result: dict[str, list[Candidate]] = {}
    properties = roles.get("properties")
    for link, role in (
        ("belongs_to", "communities"),
        ("within_local_plan", "local_plans"),
        ("within_structure_plan", "structure_plans"),
    ):
        if properties is None or role not in roles:
            continue
        result[link] = [
            Candidate(
                link, s, o, confidence=round(min(share, 1.0), 3), details={"share": round(share, 4)}
            )
            for s, o, share in _best_container(properties.layer_id, roles[role].layer_id, scope)
            if share >= MIN_SHARE or link == "belongs_to"
        ]
    if "communities" in roles and "facilities" in roles:
        # Worked out from the facility's side (which community it is in), stored
        # from the community's side. Not narrowed by scope: scope names properties.
        pairs = _best_container(roles["facilities"].layer_id, roles["communities"].layer_id, None)
        result["contains_infrastructure"] = [
            Candidate(
                "contains_infrastructure", community, facility, details={"share": round(share, 4)}
            )
            for facility, community, share in pairs
        ]
    return result


# --- 2. Streets -----------------------------------------------------------------------------------


def access(roles: Roles, scope: Scope) -> dict[str, list[Candidate]]:
    """The street a property is on (the nearest within 100 m), and whether a
    road serves it (one within 30 m)."""
    properties, streets = roles["properties"], roles["streets"]
    frontage = _number(streets.config, "located_on_max_m", LOCATED_ON_MAX_M)
    reach = _number(streets.config, "access_max_m", ACCESS_MAX_M)
    nearest = _nearest(properties.layer_id, streets.layer_id, frontage, scope)
    return {
        "located_on": [
            Candidate("located_on", s, o, confidence=1.0, details={"distance_m": round(d, 2)})
            for s, o, d in nearest
        ],
        "served_by": [
            Candidate("served_by", s, o, details={"distance_m": round(d, 2), "within_m": reach})
            for s, o, d in nearest
            if d <= reach
        ],
    }


# --- 3. Flood risk --------------------------------------------------------------------------------


def flood(roles: Roles, scope: Scope) -> dict[str, list[Candidate]]:
    properties, zones = roles["properties"], roles["flood_risk"]
    params: list[Any] = [properties.layer_id, zones.layer_id]
    scoped = _scope("s", scope, params)
    sql = (
        f"SELECT s.id, o.id, {SHARE}, o.properties FROM projects_feature s"  # noqa: S608
        " JOIN projects_feature o ON ST_Intersects(s.geom_4326, o.geom_4326)"
        f" WHERE s.layer_id = %s AND o.layer_id = %s{scoped} ORDER BY s.id, o.id"
    )
    risk_field = zones.config.get("risk_field", "risk")
    return {
        "affected_by": [
            Candidate(
                "affected_by",
                s,
                o,
                details={"share": round(float(share), 4), "risk": _obj(props).get(risk_field)},
            )
            for s, o, share, props in _rows(sql, params)
        ]
    }


# --- 4. Drainage ----------------------------------------------------------------------------------


def drainage(roles: Roles, scope: Scope) -> dict[str, list[Candidate]]:
    """The nearest drain within reach is probably the one a property uses.
    This is a guess from distance: it is recorded as inferred, for a person
    to confirm or reject (usually in the field)."""
    properties, drains = roles["properties"], roles["drains"]
    reach = _number(drains.config, "max_m", DRAIN_MAX_M)
    return {
        "connected_to": [
            Candidate(
                "connected_to",
                s,
                o,
                method=Relationship.Method.INFERRED,
                confidence=round(0.9 - 0.4 * d / reach, 2),
                details={"distance_m": round(d, 2), "within_m": reach},
            )
            for s, o, d in _nearest(properties.layer_id, drains.layer_id, reach, scope)
        ]
    }


# --- 5. Permits -----------------------------------------------------------------------------------


def permits(roles: Roles, scope: Scope) -> dict[str, list[Candidate]]:
    """A permit belongs to a property when it names the property's id
    (calculated), or when it lies on the property (inferred)."""
    properties, layer = roles["properties"], roles["permits"]
    id_field = properties.config.get("id_field", "property_id")
    ref_field = layer.config.get("property_field", "property_id")
    status_field = layer.config.get("status_field", "status")
    wanted = set(scope) if scope is not None else None
    by_ref: dict[str, int] = {}
    for pid, props in _properties(properties.layer_id, wanted).items():
        ref = (props or {}).get(id_field)
        if ref not in (None, ""):
            by_ref[str(ref)] = pid
    permit_props = _properties(layer.layer_id)
    found: dict[tuple[int, int], Candidate] = {}
    for permit_id, props in permit_props.items():
        ref = (props or {}).get(ref_field)
        subject = by_ref.get(str(ref)) if ref not in (None, "") else None
        if subject is not None:
            found[(subject, permit_id)] = Candidate(
                "has_permit",
                subject,
                permit_id,
                details={"matched_by": "id", "status": (props or {}).get(status_field)},
            )
    params: list[Any] = [properties.layer_id, layer.layer_id]
    scoped = _scope("s", scope, params)
    sql = (
        "SELECT s.id, o.id FROM projects_feature s JOIN projects_feature o"  # noqa: S608
        " ON ST_Intersects(s.geom_4326, o.geom_4326)"
        f" WHERE s.layer_id = %s AND o.layer_id = %s{scoped} ORDER BY s.id, o.id"
    )
    for subject, permit_id in _rows(sql, params):
        if (subject, permit_id) in found:
            continue
        # A permit that names another property isn't this one's, wherever it sits.
        ref = (permit_props.get(permit_id) or {}).get(ref_field)
        if ref not in (None, "") and str(ref) in by_ref:
            continue
        found[(subject, permit_id)] = Candidate(
            "has_permit",
            subject,
            permit_id,
            method=Relationship.Method.INFERRED,
            confidence=0.8,
            details={
                "matched_by": "location",
                "status": (permit_props.get(permit_id) or {}).get(status_field),
            },
        )
    return {"has_permit": list(found.values())}


# --- 6. Rules: developments that break the standards ---------------------------------------------


def standard_for(district_id: int, zone: str | None) -> dict[str, Any]:
    """The standard that applies to a zone: the zone's own, else the
    district's default (zone ""), else the platform's."""
    rows = {s.zone.lower(): s for s in DevelopmentStandard.objects.filter(district_id=district_id)}
    chosen = rows.get(str(zone).lower()) if zone not in (None, "") else None
    chosen = chosen or rows.get("")
    if chosen is None:
        return {
            "id": None,
            "zone": "",
            "permit_required": False,
            "build_in_flood_area": True,
            "min_plot_m2": None,
            **PLATFORM_STANDARD,
        }
    return {
        "id": chosen.pk,
        "zone": chosen.zone,
        "min_setback_m": chosen.min_setback_m,
        "max_floors": chosen.max_floors,
        "max_coverage_pct": chosen.max_coverage_pct,
        "min_plot_m2": chosen.min_plot_m2,
        "permit_required": chosen.permit_required,
        "build_in_flood_area": chosen.build_in_flood_area,
    }


def rules(
    roles: Roles, scope: Scope, district_id: int, project_id: int
) -> dict[str, list[Candidate]]:
    """Checks each property against the standard for its zone: setback from
    the parcel boundary, floors, plot coverage, plot size, permit, building
    in a flood-prone area."""
    properties, parcels = roles["properties"], roles["parcels"]
    zone_field = parcels.config.get("zone_field", "land_use")
    floors_field = properties.config.get("floors_field", "floors")

    # Each property with its parcel (the one covering most of it), the gap to
    # the parcel's boundary, and both areas.
    params: list[Any] = [properties.layer_id, parcels.layer_id]
    scoped = _scope("s", scope, params)
    sql = (
        f"SELECT DISTINCT ON (s.id) s.id, o.id, {SHARE} AS share,"  # noqa: S608
        " ST_Distance(ST_Boundary(o.geom_4326)::geography, s.geom_4326::geography),"
        " ST_Area(s.geom_4326::geography), ST_Area(o.geom_4326::geography),"
        " s.properties, o.properties"
        " FROM projects_feature s JOIN projects_feature o"
        " ON ST_Intersects(s.geom_4326, o.geom_4326)"
        f" WHERE s.layer_id = %s AND o.layer_id = %s{scoped}"
        " ORDER BY s.id, share DESC, o.id"
    )
    rows = _rows(sql, params)

    # Zone from a zoning layer where there is one, else from the parcel.
    zone_of: dict[int, Any] = {}
    if "zoning" in roles:
        zoning = roles["zoning"]
        field_name = zoning.config.get("zone_field", "zone")
        zone_props = _properties(zoning.layer_id)
        for subject, zone_id, share in _best_container(properties.layer_id, zoning.layer_id, scope):
            if share >= MIN_SHARE:
                zone_of[subject] = (zone_props.get(zone_id) or {}).get(field_name)

    # Built area per parcel, for coverage (all properties on the parcel, not only those in scope).
    coverage_sql = (
        "SELECT o.id, sum(ST_Area(ST_Intersection(s.geom_4326, o.geom_4326)::geography))"
        " FROM projects_feature s JOIN projects_feature o"
        " ON ST_Intersects(s.geom_4326, o.geom_4326)"
        " WHERE s.layer_id = %s AND o.layer_id = %s AND ST_Dimension(s.geom_4326) = 2 GROUP BY o.id"
    )
    built = {
        pid: float(a or 0)
        for pid, a in _rows(coverage_sql, [properties.layer_id, parcels.layer_id])
    }

    linked = Relationship.objects.filter(project_id=project_id, status=Relationship.Status.ACTIVE)
    has_permit = set(linked.filter(type="has_permit").values_list("subject_id", flat=True))
    in_flood = set(linked.filter(type="affected_by").values_list("subject_id", flat=True))
    standards: dict[str, dict[str, Any]] = {}
    found: list[Candidate] = []

    def breach(subject: int, rule: str, standard: dict[str, Any], **details: Any) -> None:
        found.append(
            Candidate(
                "violates",
                subject,
                None,
                rule=rule,
                details={
                    "standard": standard["id"],
                    "zone": standard["zone"] or "default",
                    **details,
                },
            )
        )

    for subject, parcel, share, gap, _area, parcel_area, props, parcel_props in rows:
        if float(share) < MIN_SHARE:
            continue  # not really on this parcel
        zone = zone_of.get(subject, _obj(parcel_props).get(zone_field))
        key = str(zone or "").lower()
        if key not in standards:
            standards[key] = standard_for(district_id, zone)
        standard = standards[key]
        base = {"parcel": parcel}
        setback = standard["min_setback_m"]
        if setback is not None and float(gap) < setback - SETBACK_TOLERANCE_M:
            breach(
                subject,
                "setback",
                standard,
                measured_m=round(float(gap), 2),
                required_m=setback,
                **base,
            )
        floors = _obj(props).get(floors_field)
        limit = standard["max_floors"]
        if limit is not None and isinstance(floors, int | float) and floors > limit:
            breach(subject, "floors", standard, measured=floors, allowed=limit, **base)
        max_cover = standard["max_coverage_pct"]
        if max_cover is not None and parcel_area:
            cover = 100.0 * built.get(parcel, 0.0) / float(parcel_area)
            if cover > max_cover + 0.5:
                breach(
                    subject,
                    "coverage",
                    standard,
                    measured_pct=round(cover, 1),
                    allowed_pct=max_cover,
                    **base,
                )
        min_plot = standard["min_plot_m2"]
        if min_plot is not None and float(parcel_area) < min_plot - 0.5:
            breach(
                subject,
                "plot_size",
                standard,
                measured_m2=round(float(parcel_area), 1),
                required_m2=min_plot,
                **base,
            )
        if standard["permit_required"] and "permits" in roles and subject not in has_permit:
            breach(subject, "no_permit", standard, **base)
        if not standard["build_in_flood_area"] and subject in in_flood:
            breach(subject, "flood_area", standard, **base)
    return {"violates": found}


# --- 7. Catchments --------------------------------------------------------------------------------


def catchments(roles: Roles, scope: Scope) -> dict[str, list[Candidate]]:
    """The population units within reach of each facility."""
    facilities, population = roles["facilities"], roles["population"]
    reach = _number(facilities.config, "radius_m", CATCHMENT_M)
    field_name = population.config.get("population_field", "population")
    people = _properties(population.layer_id)
    return {
        "serves": [
            Candidate(
                "serves",
                s,
                o,
                details={
                    "distance_m": round(d, 1),
                    "within_m": reach,
                    "population": (people.get(o) or {}).get(field_name),
                },
            )
            # Not narrowed by scope: scope names properties.
            for s, o, d in _within_distance(facilities.layer_id, population.layer_id, reach, None)
        ]
    }


# --- 8. Needs and projects ------------------------------------------------------------------------


def needs(roles: Roles, scope: Scope) -> dict[str, list[Candidate]]:
    """A project probably addresses the needs near it; more likely when they
    are of the same kind. Inferred: a person confirms."""
    projects, need_layer = roles["projects"], roles["needs"]
    reach = _number(projects.config, "match_m", NEED_MATCH_M)
    project_type = projects.config.get("type_field", "type")
    need_type = need_layer.config.get("type_field", "type")
    project_props = _properties(projects.layer_id)
    need_props = _properties(need_layer.layer_id)
    found = []
    for s, o, d in _within_distance(projects.layer_id, need_layer.layer_id, reach, None):
        a = (project_props.get(s) or {}).get(project_type)
        b = (need_props.get(o) or {}).get(need_type)
        both = a not in (None, "") and b not in (None, "")
        if both and str(a).strip().lower() != str(b).strip().lower():
            continue  # a road project doesn't address a need for a clinic
        found.append(
            Candidate(
                "addresses",
                s,
                o,
                method=Relationship.Method.INFERRED,
                confidence=0.8 if both else 0.5,
                details={"distance_m": round(d, 1), "same_kind": both, "kind": b},
            )
        )
    return {"addresses": found}


# Procedure name -> (roles it needs, function). "rules" takes extra arguments.
REQUIRES: dict[str, tuple[str, ...]] = {
    "containment": (),  # works with whichever of its layers are mapped
    "access": ("properties", "streets"),
    "flood": ("properties", "flood_risk"),
    "drainage": ("properties", "drains"),
    "permits": ("properties", "permits"),
    "rules": ("properties", "parcels"),
    "catchments": ("facilities", "population"),
    "needs": ("projects", "needs"),
}

"""The automatic checks on an application's site: the "initial zoning checks"
of L.I. 2384 r.44(7)(a), made from the map. They are advice to the Technical
Sub-Committee and the Spatial Planning Committee, never the decision.

Each result is pass, fail, warn (look into it) or unknown (the map can't say),
with the measurement and the rule it was compared with.
"""

from typing import Any

from django.db import connection
from django.utils import timezone

from projects.models import PlanProject
from relations import procedures, zoning
from relations import services as relations

from .models import Application

ACCESS_MAX_M = 30.0
PASS, FAIL, WARN, UNKNOWN = "pass", "fail", "warn", "unknown"


def _rows(sql: str, params: list[Any]) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _covering(site_id: int, layer_id: int) -> tuple[int, dict[str, Any], float] | None:
    """The feature of a layer covering most of the site: (id, properties, share of the site)."""
    rows = _rows(
        "SELECT o.id, o.properties,"
        " ST_Area(ST_Intersection(s.geom_4326, o.geom_4326)::geography)"
        " / NULLIF(ST_Area(s.geom_4326::geography), 0) AS share"
        " FROM projects_feature s JOIN projects_feature o"
        " ON ST_Intersects(s.geom_4326, o.geom_4326)"
        " WHERE s.id = %s AND o.layer_id = %s AND ST_Dimension(o.geom_4326) = 2"
        " ORDER BY share DESC NULLS LAST, o.id LIMIT 1",
        [site_id, layer_id],
    )
    if not rows or rows[0][2] is None:
        return None
    feature_id, properties, share = rows[0]
    return feature_id, procedures._obj(properties), float(share)


def _zone(site_id: int, roles: procedures.Roles) -> tuple[str | None, str]:
    """The site's zone and where it was read from."""
    if "zoning" in roles:
        role = roles["zoning"]
        found = _covering(site_id, role.layer_id)
        if found and found[2] >= procedures.MIN_SHARE:
            return found[1].get(role.config.get("zone_field", "zone")), "the zoning layer"
    if "parcels" in roles:
        role = roles["parcels"]
        found = _covering(site_id, role.layer_id)
        if found and found[2] >= procedures.MIN_SHARE:
            return found[1].get(role.config.get("zone_field", "land_use")), "the parcel's land use"
    return None, ""


def run(application: Application) -> dict[str, Any]:
    """Runs every check the map allows and returns the results (also stored
    on the application)."""
    project: PlanProject = application.project
    results: list[dict[str, Any]] = []

    def add(code: str, label: str, outcome: str, detail: str, **numbers: Any) -> None:
        results.append(
            {"code": code, "label": label, "outcome": outcome, "detail": detail, **numbers}
        )

    out: dict[str, Any] = {"ran_at": timezone.now().isoformat(), "zone": None, "standard": None}
    site_id = application.site_id
    if site_id is None:
        add("site", "The site", UNKNOWN, "The application has no site on the map yet.")
        out["results"] = results
        return _store(application, out)

    roles = relations.roles_of(project)
    (area, is_area) = _rows(
        "SELECT ST_Area(geom_4326::geography), ST_Dimension(geom_4326) = 2"
        " FROM projects_feature WHERE id = %s",
        [site_id],
    )[0]
    area = float(area or 0)

    # --- Zone and the standard that applies ---------------------------------------------------
    zone_value, zone_from = _zone(site_id, roles)
    national = zoning.match(zone_value)
    standard = procedures.standard_for(application.district_id, zone_value)
    out["zone"] = {
        "value": zone_value,
        "from": zone_from,
        "national": national.code if national else None,
        "name": national.name if national else None,
    }
    out["standard"] = {k: standard[k] for k in ("id", "zone", *procedures.STANDARD_FIELDS)}
    if zone_value in (None, ""):
        add("zone", "Zone", UNKNOWN, "No zoning layer or parcel land use covers the site.")
    else:
        named = f"{national.code}, {national.name}" if national else str(zone_value)
        add("zone", "Zone", PASS, f"{named} (from {zone_from}).")
    if standard["id"] is None:
        add(
            "standard",
            "Standard",
            WARN,
            "The district has set no development standards: only the platform's default applies.",
        )
    elif zone_value not in (None, "") and not standard["zone"]:
        add(
            "standard",
            "Standard",
            WARN,
            "No standard for this zone: the district's default applies.",
        )

    # --- Land use ---------------------------------------------------------------------------------
    use = application.proposed_use.strip()
    if not use:
        add("use", "Proposed use", UNKNOWN, "The application doesn't say what the use will be.")
    else:
        word = next((w for w in standard["prohibited_uses"] if w in use.lower()), None)
        if word:
            add(
                "use",
                "Proposed use",
                FAIL,
                f'"{use}" looks like a use the zone prohibits ("{word}"). To be confirmed.',
            )
        elif standard["prohibited_uses"]:
            add(
                "use", "Proposed use", PASS, f'"{use}" matches none of the zone\'s prohibited uses.'
            )
        else:
            add("use", "Proposed use", UNKNOWN, "The standard lists no prohibited uses.")

    # --- Plot size and width --------------------------------------------------------------------
    if not is_area:
        add("plot_size", "Plot size", UNKNOWN, "The site is a point: draw its boundary to check.")
    elif standard["min_plot_m2"] is None:
        add(
            "plot_size",
            "Plot size",
            UNKNOWN,
            f"{area:,.0f} m². The standard sets no minimum.",
            measured_m2=round(area, 1),
        )
    else:
        need = float(standard["min_plot_m2"])
        add(
            "plot_size",
            "Plot size",
            PASS if area >= need - 0.5 else FAIL,
            f"{area:,.0f} m²; the standard asks for at least {need:,.0f} m².",
            measured_m2=round(area, 1),
            required_m2=need,
        )
    width = None
    if is_area and "streets" in roles:
        edges = procedures.plot_edges([(site_id, site_id)], roles["streets"].layer_id).get(site_id)
        width = edges.width_m if edges else None
    if standard["min_width_m"] is not None:
        need = float(standard["min_width_m"])
        if width is None:
            add(
                "plot_width",
                "Plot width",
                UNKNOWN,
                "No street near the site: its front isn't known.",
            )
        else:
            add(
                "plot_width",
                "Plot width",
                PASS if width >= need - procedures.WIDTH_TOLERANCE_M else FAIL,
                f"{width:.1f} m at the street; the standard asks for at least {need:.1f} m.",
                measured_m=round(width, 1),
                required_m=need,
            )

    # --- Height ----------------------------------------------------------------------------------
    floors = application.proposed_floors
    low, high = standard["min_floors"], standard["max_floors"]
    if floors is None:
        if low is not None or high is not None:
            add("floors", "Storeys", UNKNOWN, "The application doesn't give the number of storeys.")
    elif high is not None and floors > high:
        add("floors", "Storeys", FAIL, f"{floors} storeys; the zone allows up to {high}.")
    elif low is not None and floors < low:
        add("floors", "Storeys", FAIL, f"{floors} storeys; the zone asks for at least {low}.")
    elif low is not None or high is not None:
        add("floors", "Storeys", PASS, f"{floors} storeys is within the zone's limits.")

    # --- Building lines, setbacks and coverage: from the drawings ---------------------------
    sides = [standard[f"{name}_setback_m"] for name in ("front", "side", "rear")]
    if any(v is not None for v in sides) or standard["max_coverage_pct"] is not None:
        wanted = []
        if any(v is not None for v in sides):
            front, side, rear = (("—" if v is None else f"{v:g} m") for v in sides)
            wanted.append(
                f"setbacks of {front} at the front, {side} at the sides and {rear} at the back"
            )
        if standard["max_coverage_pct"] is not None:
            limit = float(standard["max_coverage_pct"])
            allowed = f" ({area * limit / 100:,.0f} m² of this plot)" if is_area else ""
            wanted.append(f"coverage up to {limit:g}%{allowed}")
        add(
            "drawings",
            "Building lines, setbacks and coverage",
            UNKNOWN,
            f"Check on the block plan: {'; '.join(wanted)}.",
        )

    # --- Flood-prone land ------------------------------------------------------------------------
    if "flood_risk" in roles:
        found = _covering(site_id, roles["flood_risk"].layer_id) if is_area else None
        touches = _rows(
            "SELECT count(*) FROM projects_feature s JOIN projects_feature o"
            " ON ST_Intersects(s.geom_4326, o.geom_4326) WHERE s.id = %s AND o.layer_id = %s",
            [site_id, roles["flood_risk"].layer_id],
        )[0][0]
        if not touches:
            add(
                "flood",
                "Flood-prone land",
                PASS,
                "The site is outside the flood-prone areas on the map.",
            )
        else:
            share = f"{found[2] * 100:.0f}% of the site" if found else "The site"
            blocked = not standard["build_in_flood_area"]
            add(
                "flood",
                "Flood-prone land",
                FAIL if blocked else WARN,
                f"{share} is in a flood-prone area."
                + (" The zone's standard allows no building there." if blocked else ""),
            )
    else:
        add("flood", "Flood-prone land", UNKNOWN, "The project has no flood-prone areas layer.")

    # --- Access ----------------------------------------------------------------------------------
    if "streets" in roles:
        nearest = _rows(
            "SELECT min(ST_Distance(s.geom_4326::geography, o.geom_4326::geography))"
            " FROM projects_feature s, projects_feature o WHERE s.id = %s AND o.layer_id = %s"
            " AND o.geom_4326 && ST_Expand(s.geom_4326, %s)",
            [site_id, roles["streets"].layer_id, procedures.FRONT_SEARCH_DEG],
        )[0][0]
        if nearest is None:
            add("access", "Access", FAIL, "No street on the map within about 200 m of the site.")
        else:
            near = float(nearest)
            add(
                "access",
                "Access",
                PASS if near <= ACCESS_MAX_M else WARN,
                f"The nearest street is {near:.0f} m from the site.",
                distance_m=round(near, 1),
            )
    else:
        add("access", "Access", UNKNOWN, "The project has no streets layer.")

    # --- Local plan ------------------------------------------------------------------------------
    if "local_plans" in roles and is_area:
        role = roles["local_plans"]
        found = _covering(site_id, role.layer_id)
        if found and found[2] >= procedures.MIN_SHARE:
            name = found[1].get(role.config.get("name_field", "name")) or "a local plan"
            add("local_plan", "Local plan", PASS, f"The site is within {name}.")
        else:
            add("local_plan", "Local plan", WARN, "The site is outside the local plans on the map.")

    # --- Other applications on the same land ------------------------------------------------
    others = _rows(
        "SELECT a.number, a.status FROM permits_application a"
        " JOIN projects_feature o ON o.id = a.site_id JOIN projects_feature s ON s.id = %s"
        " WHERE a.id <> %s AND a.status <> 'withdrawn' AND ST_Intersects(s.geom_4326, o.geom_4326)"
        " AND (ST_Dimension(ST_Intersection(s.geom_4326, o.geom_4326)) = 2"
        "      OR ST_Dimension(s.geom_4326) < 2 OR ST_Dimension(o.geom_4326) < 2)"
        " ORDER BY a.id",
        [site_id, application.pk],
    )
    if others:
        listed = ", ".join(f"{number} ({status})" for number, status in others)
        add("overlap", "Other applications on this land", WARN, f"Overlaps {listed}.")
    else:
        add("overlap", "Other applications on this land", PASS, "None on the map.")

    out["results"] = results
    return _store(application, out)


def _store(application: Application, out: dict[str, Any]) -> dict[str, Any]:
    counts = {outcome: 0 for outcome in (PASS, FAIL, WARN, UNKNOWN)}
    for result in out["results"]:
        counts[result["outcome"]] += 1
    out["counts"] = counts
    application.checks = out
    application.checked_at = timezone.now()
    application.save(update_fields=["checks", "checked_at", "updated_at"])
    return out

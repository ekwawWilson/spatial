"""A project's planning area: creation, status, and the validation report
(validity, area and perimeter, overlaps and gaps with neighbouring planning
areas, and fit inside the district boundary)."""

from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection

from core.models import User

from . import geometry as geo
from . import styles
from .models import Domain, Feature, GeometryType, Layer, PlanProject

LAYER_NAME = "Planning area"
NEAR_METRES = 2.0  # neighbours this close without touching are reported as gaps
METRES_PER_ACRE = 4046.8564224


def boundary_layer(project: PlanProject, user: User | None) -> Layer:
    layer = project.layers.filter(name=LAYER_NAME).first()
    if layer:
        return layer
    top = max((layer.order for layer in project.layers.all()), default=0)
    return Layer.objects.create(
        district_id=project.district_id,
        project=project,
        name=LAYER_NAME,
        domain=Domain.TERRITORY,
        geometry_type=GeometryType.POLYGON,
        crs=project.crs,
        schema=[
            {"name": "name", "label": "Name", "type": "text", "required": False},
            {"name": "method", "label": "How it was made", "type": "text", "required": False},
        ],
        style={
            **styles.default_style(),
            "fill": "#e4572e",
            "stroke": "#a33a1c",
            "fill_opacity": 0.1,
            "stroke_width": 3,
        },
        order=top + 1,
        created_by=user,
    )


def set_boundary(
    project: PlanProject, geometry: dict[str, Any], method: str, user: User
) -> Feature:
    """Creates or replaces the planning area (geometry in the project's CRS)."""
    if project.boundary_status != PlanProject.BoundaryStatus.DRAFT:
        raise ValidationError("The boundary is agreed or approved: reopen it before changing it.")
    layer = boundary_layer(project, user)
    geo.check_geometry(geometry, layer)
    feature = project.boundary_feature
    if feature is None:
        feature = Feature.objects.create(
            district_id=project.district_id,
            layer=layer,
            properties={"name": project.community or project.name, "method": method},
            created_by=user,
            updated_by=user,
        )
        project.boundary_feature = feature
        project.save(update_fields=["boundary_feature", "updated_at"])
    else:
        feature.properties = {**feature.properties, "method": method}
        feature.version += 1
        feature.updated_by = user
        feature.save(update_fields=["properties", "version", "updated_by", "updated_at"])
    geo.write_geometry(feature, geometry)
    return feature


TRANSITIONS = {
    ("draft", "agreed"): "project.edit",
    ("agreed", "approved"): "boundary.approve",
    ("agreed", "draft"): "project.edit",
    ("approved", "draft"): "boundary.approve",  # reopening an approved boundary
}


def required_permission(current: str, target: str) -> str:
    code = TRANSITIONS.get((current, target))
    if code is None:
        raise ValidationError(f"A boundary can't go from {current} to {target}.")
    return code


def report(project: PlanProject) -> dict[str, Any]:
    feature = project.boundary_feature
    if feature is None:
        return {"exists": False}
    unit = project.crs.unit_to_metre
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_IsValid(geom_native), ST_IsValidReason(geom_native),"
            " ST_Area(geom_4326::geography), ST_Perimeter(geom_4326::geography),"
            " ST_Area(geom_native), ST_Perimeter(geom_native), ST_NPoints(geom_native)"
            " FROM projects_feature WHERE id = %s",
            [feature.pk],
        )
        valid, reason, area_m2, perimeter_m, area_native, perimeter_native, vertices = (
            cursor.fetchone()
        )

        # Other projects' planning areas in the district (row-level security
        # already limits this to the district).
        cursor.execute(
            """
            SELECT p.id, p.name,
                   ST_Area(ST_Intersection(mine.geom_4326, theirs.geom_4326)::geography)
                       AS overlap_m2,
                   ST_Distance(mine.geom_4326::geography, theirs.geom_4326::geography) AS distance_m
            FROM projects_planproject p
            JOIN projects_feature theirs ON theirs.id = p.boundary_feature_id
            JOIN projects_feature mine ON mine.id = %s
            WHERE p.id <> %s AND p.status <> 'archived'
              AND ST_DWithin(mine.geom_4326::geography, theirs.geom_4326::geography, %s)
            ORDER BY p.name
            """,
            [feature.pk, project.pk, NEAR_METRES],
        )
        neighbours = []
        for pid, name, overlap_m2, distance_m in cursor.fetchall():
            if overlap_m2 and overlap_m2 > 0.01:
                neighbours.append(
                    {"project": pid, "name": name, "kind": "overlap", "area_m2": overlap_m2}
                )
            elif distance_m > 0:
                neighbours.append(
                    {"project": pid, "name": name, "kind": "gap", "distance_m": distance_m}
                )

        outside_district = None
        cursor.execute(
            "SELECT ST_Area(ST_Difference(f.geom_4326, d.boundary)::geography)"
            " FROM projects_feature f, core_district d"
            " WHERE f.id = %s AND d.id = %s AND d.boundary IS NOT NULL",
            [feature.pk, project.district_id],
        )
        row = cursor.fetchone()
        if row is not None:
            outside_district = row[0]

    return {
        "exists": True,
        "feature": feature.pk,
        "status": project.boundary_status,
        "valid": valid,
        "invalid_reason": None if valid else reason,
        "vertices": vertices,
        "area_m2": area_m2,
        "area_ha": area_m2 / 10_000,
        "area_acres": area_m2 / METRES_PER_ACRE,
        "perimeter_m": perimeter_m,
        # In the project's own units, for projected systems (e.g. Gold Coast feet).
        "area_native": area_native if unit else None,
        "perimeter_native": perimeter_native if unit else None,
        "native_units": project.crs.units,
        "neighbours": neighbours,
        "district_boundary_loaded": outside_district is not None,
        "outside_district_m2": outside_district,
    }


def geometry_of(feature: Feature) -> dict[str, Any] | None:
    return geo.read_geometries([feature.pk], native=True).get(feature.pk)

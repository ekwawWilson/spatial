# ruff: noqa: E501 - the steps read better unbroken
"""Drawing an approved subdivision or consolidation on the map.

A subdivision's parcel is cut into the approved number of plots of equal
area, across its long side, so each plot keeps a share of the frontage.
A consolidation's parcels are joined into one. The plots go into their own
layer, "Approved subdivisions", so the cadastral parcels are never changed
by this: copy the plots into the parcels layer once the Lands Commission has
endorsed them (r.54(13)).

The cutting is done in the parcel's own coordinates (no reprojection), with
the plot lines found by bisection to within a millionth of the area."""

import json
import math
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from osgeo import ogr

from core.models import User
from projects import geometry as geo
from projects import styles
from projects.models import Feature, Layer, PlanProject

from .models import Application

ogr.UseExceptions()

LAYER_NAME = "Approved subdivisions"
SCHEMA: list[dict[str, Any]] = [
    {"name": "application_no", "label": "Application", "type": "text", "required": False},
    {"name": "plot_no", "label": "Plot", "type": "text", "required": False},
    {"name": "parent", "label": "From parcel", "type": "text", "required": False},
    {"name": "area_m2", "label": "Area (m²)", "type": "decimal", "required": False},
]
MAX_PLOTS = 200


def _layer(project: PlanProject, crs_id: int, user: User) -> Layer:
    found = project.layers.filter(name=LAYER_NAME).first()
    if found is not None:
        return found
    top = max((x.order for x in project.layers.all()), default=0)
    return Layer.objects.create(
        district_id=project.district_id,
        project=project,
        name=LAYER_NAME,
        domain="B",
        geometry_type="polygon",
        crs_id=crs_id,
        schema=SCHEMA,
        style={
            **styles.default_style(),
            "fill": "#f2c94c",
            "stroke": "#8a6d00",
            "fill_opacity": 0.35,
            "label_field": "plot_no",
        },
        order=top + 1,
        source=Layer.Source.DERIVED,
        created_by=user,
    )


def _rotate(geom: ogr.Geometry, angle: float, cx: float, cy: float) -> ogr.Geometry:
    """The geometry turned by angle (radians) about (cx, cy)."""
    cos, sin = math.cos(angle), math.sin(angle)
    data = json.loads(geom.ExportToJson())

    def turn(coords: Any) -> Any:
        if isinstance(coords[0], (int, float)):
            x, y = coords[0] - cx, coords[1] - cy
            return [cx + x * cos - y * sin, cy + x * sin + y * cos]
        return [turn(c) for c in coords]

    data["coordinates"] = turn(data["coordinates"])
    return ogr.CreateGeometryFromJson(json.dumps(data))


def _long_side_angle(geom: ogr.Geometry) -> float:
    """The direction of the long side of the smallest rectangle around the
    shape (rotating calipers over the convex hull's edges)."""
    ring = geom.ConvexHull().GetGeometryRef(0)
    points = [ring.GetPoint_2D(i) for i in range(ring.GetPointCount())]
    best: tuple[float, float] | None = None  # (area, angle)
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if (x0, y0) == (x1, y1):
            continue
        angle = math.atan2(y1 - y0, x1 - x0)
        xmin, xmax, ymin, ymax = _rotate(geom, -angle, 0, 0).GetEnvelope()
        area = (xmax - xmin) * (ymax - ymin)
        # Turn so the long side runs along x.
        long_angle = angle if (xmax - xmin) >= (ymax - ymin) else angle + math.pi / 2
        if best is None or area < best[0] - 1e-9:
            best = (area, long_angle)
    return best[1] if best else 0.0


def _box(xmin: float, xmax: float, ymin: float, ymax: float) -> ogr.Geometry:
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)):
        ring.AddPoint_2D(x, y)
    box = ogr.Geometry(ogr.wkbPolygon)
    box.AddGeometry(ring)
    return box


def split(geom: ogr.Geometry, parts: int) -> list[ogr.Geometry]:
    """The shape cut into parts of equal area, by lines across its long side."""
    centroid = geom.Centroid()
    cx, cy = centroid.GetX(), centroid.GetY()
    angle = _long_side_angle(geom)
    flat = _rotate(geom, -angle, cx, cy)
    xmin, xmax, ymin, ymax = flat.GetEnvelope()
    pad = (ymax - ymin) + 1.0
    total = flat.GetArea()

    def left_of(x: float) -> float:
        return float(flat.Intersection(_box(xmin - 1, x, ymin - pad, ymax + pad)).GetArea())

    cuts = [xmin - 1]
    for k in range(1, parts):
        target, lo, hi = total * k / parts, xmin, xmax
        for _ in range(60):
            mid = (lo + hi) / 2
            if left_of(mid) < target:
                lo = mid
            else:
                hi = mid
        cuts.append((lo + hi) / 2)
    cuts.append(xmax + 1)
    out = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        piece = flat.Intersection(_box(a, b, ymin - pad, ymax + pad))
        out.append(_rotate(piece, angle, cx, cy))
    return out


def draw(application: Application, user: User) -> dict[str, Any]:
    """The approved plots on the map; drawn again from scratch if asked twice."""
    if application.kind not in ("subdivision", "consolidation"):
        raise ValidationError("Only a subdivision or a consolidation is drawn.")
    if application.status != Application.Status.APPROVED:
        raise ValidationError("Only an approved application is drawn.")
    ids = [int(i) for i in application.parcels]
    parents = list(Feature.objects.filter(pk__in=ids).select_related("layer", "layer__crs"))
    if not parents:
        raise ValidationError("The application's parcels are no longer on the map.")
    crs_ids = {p.layer.crs_id for p in parents}
    if len(crs_ids) != 1:
        raise ValidationError("The parcels are in different coordinate systems.")
    shapes = geo.read_geometries(ids, native=True)
    geoms = [
        ogr.CreateGeometryFromJson(json.dumps(shapes[p.pk])) for p in parents if shapes.get(p.pk)
    ]
    if application.kind == "subdivision":
        lots = application.lots or 0
        if not 2 <= lots <= MAX_PLOTS:
            raise ValidationError({"lots": [f"Say into how many plots (2 to {MAX_PLOTS})."]})
        if len(geoms) != 1:
            raise ValidationError("A subdivision divides one parcel.")
        pieces = split(geoms[0], lots)
    else:
        union = geoms[0]
        for g in geoms[1:]:
            union = union.Union(g)
        pieces = [union]

    id_field = "parcel_id"
    parent_label = ", ".join(str(p.properties.get(id_field) or f"#{p.pk}") for p in parents)
    with transaction.atomic():
        layer = _layer(application.project, parents[0].layer.crs_id, user)
        Feature.objects.filter(layer=layer, properties__application_no=application.number).delete()
        made = []
        for n, piece in enumerate(pieces, start=1):
            gj = json.loads(piece.ExportToJson())
            if gj["type"] not in ("Polygon", "MultiPolygon"):
                continue
            feature = Feature.objects.create(
                district_id=application.district_id,
                layer=layer,
                properties={
                    "application_no": application.number,
                    "plot_no": f"{application.number.split('/')[-1]}-{n}"
                    if len(pieces) > 1
                    else application.number.split("/")[-1],
                    "parent": parent_label,
                },
                origin=Feature.Origin.DERIVED,
                created_by=user,
                updated_by=user,
            )
            geo.write_geometry(feature, geo.check_geometry(gj, layer))
            made.append(feature.pk)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, ST_Area(geom_4326::geography) FROM projects_feature WHERE id = ANY(%s) ORDER BY id",
                [made],
            )
            areas = cursor.fetchall()
        for pk, area in areas:
            Feature.objects.filter(pk=pk).update(
                properties=_with_area(Feature.objects.get(pk=pk).properties, float(area or 0))
            )
    return {
        "layer": layer.pk,
        "plots": [{"id": pk, "area_m2": round(float(a or 0), 1)} for pk, a in areas],
    }


def _with_area(props: dict[str, Any], area: float) -> dict[str, Any]:
    return {**props, "area_m2": round(area, 1)}

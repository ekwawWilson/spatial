"""Features from OpenStreetMap: the streets, buildings, waterways, land use
and places inside an area the user marks, brought into the project as
ordinary layers that can be edited and named like any other.

The data comes from an Overpass server (the OpenStreetMap query service) as
JSON, is written to a GeoPackage, and goes through the same import as an
uploaded file: same checks, same audit, same report. Each kind gets its own
layer in the project's coordinate system; a feature already brought in (same
OpenStreetMap id) is not brought in twice.

OpenStreetMap data is © OpenStreetMap contributors, under the Open Database
Licence: each layer records that, and it should be checked on the ground
before it is relied on.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from osgeo import ogr, osr

from projects import styles
from projects.models import Layer, PlanProject

ogr.UseExceptions()

ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
MAX_AREA_KM2 = 60.0
TIMEOUT_S = 120


@dataclass(frozen=True)
class Kind:
    code: str
    label: str
    layer_name: str
    geometry: str  # point, line or polygon
    domain: str
    # Overpass selectors: each a key, or key=regex of values.
    selectors: tuple[str, ...]
    # Our field: the OSM tag it is read from.
    fields: tuple[tuple[str, str], ...]
    fill: str
    stroke: str
    stroke_width: float = 1.5
    # Lines are cut at the edge of the area; buildings and places are kept whole.
    clip: bool = False


KINDS: tuple[Kind, ...] = (
    Kind(
        "streets",
        "Streets and roads",
        "Streets (OpenStreetMap)",
        "line",
        "D",
        (
            'highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|road|pedestrian|footway|path|steps)(_link)?$"',
        ),
        (
            ("name", "name"),
            ("road_class", "highway"),
            ("surface", "surface"),
            ("lanes", "lanes"),
            ("oneway", "oneway"),
            ("ref", "ref"),
        ),
        "#d9822b",
        "#b85c00",
        2.5,
        clip=True,
    ),
    Kind(
        "buildings",
        "Buildings",
        "Buildings (OpenStreetMap)",
        "polygon",
        "C",
        ("building",),
        (
            ("name", "name"),
            ("building", "building"),
            ("levels", "building:levels"),
            ("house_no", "addr:housenumber"),
            ("street", "addr:street"),
        ),
        "#c9a27e",
        "#7a5534",
        1.0,
    ),
    Kind(
        "waterways",
        "Rivers, streams and drains",
        "Waterways (OpenStreetMap)",
        "line",
        "F",
        ('waterway~"^(river|stream|canal|drain|ditch)$"',),
        (("name", "name"), ("waterway", "waterway"), ("width", "width")),
        "#3b82c4",
        "#1f5f9e",
        2.0,
        clip=True,
    ),
    Kind(
        "landuse",
        "Land use, parks and open spaces",
        "Land use (OpenStreetMap)",
        "polygon",
        "B",
        (
            "landuse",
            'leisure~"^(park|pitch|playground|sports_centre|stadium|garden)$"',
            'natural~"^(wood|wetland|water|scrub|grassland)$"',
        ),
        (("name", "name"), ("landuse", "landuse"), ("leisure", "leisure"), ("natural", "natural")),
        "#9cc48a",
        "#5f8c4e",
        1.0,
        clip=True,
    ),
    Kind(
        "places",
        "Schools, clinics, markets and other places",
        "Places (OpenStreetMap)",
        "point",
        "E",
        (
            'amenity~"^(school|college|university|kindergarten|clinic|hospital|doctors|pharmacy|marketplace|place_of_worship|police|fire_station|post_office|bank|fuel|townhall|community_centre|toilets|bus_station|library)$"',
            "shop",
        ),
        (("name", "name"), ("amenity", "amenity"), ("shop", "shop")),
        "#c0352b",
        "#7f1d1d",
        1.0,
    ),
)
KIND_BY_CODE = {k.code: k for k in KINDS}
FIELD_NAMES = ("osm_id",)


def area_km2(geometry: dict[str, Any]) -> float:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_Area(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)::geography) / 1e6",
            [json.dumps(geometry)],
        )
        row = cursor.fetchone()
    return float(row[0] or 0) if row else 0.0


def check_area(geometry: dict[str, Any]) -> float:
    if geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValidationError({"area": ["Mark an area: a polygon."]})
    km2 = area_km2(geometry)
    if km2 <= 0:
        raise ValidationError({"area": ["The area is empty."]})
    if km2 > MAX_AREA_KM2:
        raise ValidationError(
            {
                "area": [
                    f"The area is {km2:,.0f} km²; bring in at most {MAX_AREA_KM2:,.0f} km² at a"
                    " time (a town or a few communities). Mark a smaller area and repeat."
                ]
            }
        )
    return km2


def _bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    """(south, west, north, east), as Overpass wants it."""
    xmin, xmax, ymin, ymax = ogr.CreateGeometryFromJson(json.dumps(geometry)).GetEnvelope()
    return ymin, xmin, ymax, xmax


def query(kinds: list[Kind], geometry: dict[str, Any]) -> str:
    s, w, n, e = _bbox(geometry)
    box = f"({s:.6f},{w:.6f},{n:.6f},{e:.6f})"
    parts = []
    for kind in kinds:
        for selector in kind.selectors:
            key, _, rest = selector.partition("~")
            tag = f'["{key}"~{rest}]' if rest else f'["{key}"]'
            if kind.geometry == "point":
                parts.append(f"node{tag}{box};")
                parts.append(f"way{tag}{box};")  # places drawn as outlines become points
            else:
                parts.append(f"way{tag}{box};")
    return f"[out:json][timeout:{TIMEOUT_S - 10}];({''.join(parts)});out tags geom;"


def fetch(ql: str) -> dict[str, Any]:
    """Asks the Overpass servers in turn; the first to answer wins."""
    errors = []
    for url in settings.OSM_OVERPASS_URLS:
        if not url.startswith("https://"):
            errors.append(f"{url}: only https servers are used")
            continue
        request = urllib.request.Request(  # noqa: S310 - https only, checked above
            url,
            data=urllib.parse.urlencode({"data": ql}).encode(),
            headers={"User-Agent": settings.OSM_USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 - fixed https URLs from settings
                body: dict[str, Any] = json.loads(response.read())
                return body
        except Exception as exc:  # noqa: BLE001 - try the next server
            errors.append(f"{urllib.parse.urlparse(url).netloc}: {exc}")
    raise ValidationError(
        "OpenStreetMap could not be reached just now (" + "; ".join(errors) + "). Try again later."
    )


def _matches(tags: dict[str, str], kind: Kind) -> bool:
    import re

    for selector in kind.selectors:
        key, _, rest = selector.partition("~")
        if key in tags and (not rest or re.search(rest.strip('"'), tags[key])):
            return True
    return False


def _geometry(element: dict[str, Any], kind: Kind) -> ogr.Geometry | None:
    if element["type"] == "node":
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint_2D(element["lon"], element["lat"])
        return point
    nodes = element.get("geometry") or []
    if len(nodes) < 2:
        return None
    line = ogr.Geometry(ogr.wkbLineString)
    for node in nodes:
        line.AddPoint_2D(node["lon"], node["lat"])
    if kind.geometry == "line":
        return line
    closed = nodes[0]["lat"] == nodes[-1]["lat"] and nodes[0]["lon"] == nodes[-1]["lon"]
    if len(nodes) < 4 or not closed:
        return None
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for node in nodes:
        ring.AddPoint_2D(node["lon"], node["lat"])
    polygon = ogr.Geometry(ogr.wkbPolygon)
    polygon.AddGeometry(ring)
    if kind.geometry == "point":
        return polygon.Centroid()
    return polygon


def write_geopackage(
    data: dict[str, Any],
    kinds: list[Kind],
    area: dict[str, Any],
    skip_ids: dict[str, set[str]],
    path: Path,
) -> dict[str, int]:
    """One layer per kind, inside the area, leaving out ids already brought in."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    mask = ogr.CreateGeometryFromJson(json.dumps(area))
    driver = ogr.GetDriverByName("GPKG")
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    ds = driver.CreateDataSource(str(path))
    family = {"point": ogr.wkbPoint, "line": ogr.wkbMultiLineString, "polygon": ogr.wkbPolygon}
    counts: dict[str, int] = {}
    elements = data.get("elements") or []
    for kind in kinds:
        layer = ds.CreateLayer(kind.code, srs, family[kind.geometry])
        for name in (*FIELD_NAMES, *(f for f, _ in kind.fields)):
            layer.CreateField(ogr.FieldDefn(name, ogr.OFTString))
        seen: set[str] = set()
        count = 0
        for element in elements:
            tags = element.get("tags") or {}
            if not _matches(tags, kind):
                continue
            osm_id = f"{element['type']}/{element['id']}"
            if osm_id in seen or osm_id in skip_ids.get(kind.code, set()):
                continue
            seen.add(osm_id)
            geom = _geometry(element, kind)
            if geom is None or not geom.Intersects(mask):
                continue
            if kind.clip:
                geom = geom.Intersection(mask)
                if geom is None or geom.IsEmpty():
                    continue
            if kind.geometry == "line":
                lines = ogr.ForceToMultiLineString(geom)
                if lines is None or lines.IsEmpty():
                    continue
                geom = lines
            elif kind.geometry == "polygon" and geom.GetGeometryType() != ogr.wkbPolygon:
                # A clip that leaves several pieces keeps the largest.
                pieces = [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
                pieces = [p for p in pieces if p.GetGeometryType() == ogr.wkbPolygon]
                if not pieces:
                    continue
                geom = max(pieces, key=lambda p: p.GetArea()).Clone()
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField("osm_id", osm_id)
            for field, tag in kind.fields:
                if tags.get(tag):
                    feature.SetField(field, str(tags[tag])[:250])
            feature.SetGeometry(geom)
            layer.CreateFeature(feature)
            count += 1
        counts[kind.code] = count
    ds = None  # closes the file
    return counts


def target_layer(project: PlanProject, kind: Kind, user: Any) -> Layer:
    """The project's layer for this kind: reused if it is already there, made otherwise."""
    found = project.layers.filter(name=kind.layer_name).first()
    if found is not None:
        return found
    schema = [
        {"name": "osm_id", "label": "OpenStreetMap id", "type": "text", "required": False},
        *[
            {
                "name": field,
                "label": field.replace("_", " ").capitalize(),
                "type": "text",
                "required": False,
            }
            for field, _ in kind.fields
        ],
    ]
    style = {
        **styles.default_style(),
        "fill": kind.fill,
        "stroke": kind.stroke,
        "stroke_width": kind.stroke_width,
        "fill_opacity": 0.45 if kind.geometry == "polygon" else 0.9,
        "label_field": "name" if kind.code in ("streets", "places") else None,
    }
    top = max((layer.order for layer in project.layers.all()), default=0)
    return Layer.objects.create(
        district_id=project.district_id,
        project=project,
        name=kind.layer_name,
        domain=kind.domain,
        geometry_type=kind.geometry,
        crs=project.crs,
        schema=schema,
        style=style,
        order=top + 1,
        source=Layer.Source.DERIVED,
        created_by=user,
    )


def existing_ids(layer: Layer) -> set[str]:
    return {
        str(v)
        for v in layer.features.values_list("properties__osm_id", flat=True)
        if v not in (None, "")
    }

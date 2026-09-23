"""CRS logic: reading definitions, registering custom systems in PostGIS,
resolving defaults and transforming coordinates.

pyproj (PROJ) is the single source of truth for definitions and coordinate
operations. PostGIS gets the same definitions in spatial_ref_sys so the
database can transform too.
"""

import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Max
from pyproj import CRS, Transformer
from pyproj.enums import TransformDirection, WktVersion
from pyproj.exceptions import CRSError, ProjError
from pyproj.transformer import TransformerGroup

from core.models import District, User

from .models import (
    CUSTOM_SRID_MAX,
    CUSTOM_SRID_MIN,
    CoordinateSystem,
    DistrictCrsSettings,
    PreferredTransformation,
    SystemCrsSettings,
    UserCrsPreference,
)

Coord = Sequence[float]


# --- Reading definitions -------------------------------------------------------


def parse_definition(definition: str) -> CRS:
    """A pyproj CRS from EPSG code, WKT or PROJ string; ValidationError if invalid."""
    text = definition.strip()
    if not text:
        raise ValidationError("Enter a definition (EPSG code, WKT or PROJ string).")
    try:
        crs = CRS.from_user_input(text)
    except CRSError as exc:
        raise ValidationError(f"Not a valid coordinate reference system: {exc}") from exc
    if not (crs.is_projected or crs.is_geographic):
        raise ValidationError("Only 2D projected or geographic systems are supported.")
    return crs


def describe(crs: CRS) -> dict[str, Any]:
    """Registry fields derived from a pyproj CRS."""
    axis = crs.axis_info[0] if crs.axis_info else None
    area = crs.area_of_use
    unit_to_metre = axis.unit_conversion_factor if axis and crs.is_projected else None
    return {
        "name": crs.name,
        "wkt": crs.to_wkt(WktVersion.WKT2_2019),
        "proj4": _base_proj4(crs),
        "kind": CoordinateSystem.Kind.PROJECTED
        if crs.is_projected
        else CoordinateSystem.Kind.GEOGRAPHIC,
        "units": axis.unit_name if axis else "",
        "unit_to_metre": unit_to_metre,
        "area_of_use": area.name if area else "",
        "bounds": list(area.bounds) if area else None,
    }


def _base_proj4(crs: CRS) -> str:
    """PROJ string without datum shift. Use web_proj4() for web maps."""
    with warnings.catch_warnings():
        # "You will likely lose important projection information": yes, the
        # datum shift, which web_proj4() adds back explicitly.
        warnings.simplefilter("ignore", UserWarning)
        return (crs.to_proj4() or "").replace(" +type=crs", "")


def as_pyproj(system: CoordinateSystem) -> CRS:
    return CRS.from_wkt(system.wkt)


# --- Registering ---------------------------------------------------------------


def builtin_from_epsg(code: int, notes: str = "") -> CoordinateSystem:
    """Creates or refreshes a built-in EPSG system (PostGIS already knows it)."""
    info = describe(CRS.from_epsg(code))
    system, _ = CoordinateSystem.objects.update_or_create(
        code=f"EPSG:{code}",
        defaults={**info, "srid": code, "is_builtin": True, "notes": notes, "district": None},
    )
    return system


def _postgis_srtext(crs: CRS) -> str:
    # PostGIS/PROJ read WKT1 most reliably; fall back to WKT2 if a system can't
    # be expressed in WKT1.
    try:
        return crs.to_wkt(WktVersion.WKT1_GDAL)
    except CRSError:
        return crs.to_wkt(WktVersion.WKT2_2019)


def register_custom(
    *, name: str, definition: str, district: District | None, user: User | None, notes: str = ""
) -> CoordinateSystem:
    """Adds a user-defined system to the registry and to PostGIS.

    EPSG codes are refused here: every EPSG system can be added as a built-in,
    and duplicates would give one system two codes.
    """
    crs = parse_definition(definition)
    if crs.to_epsg(min_confidence=100) is not None:
        raise ValidationError(
            f"This is EPSG:{crs.to_epsg()}. Ask a system administrator to enable it instead."
        )
    info = describe(crs)
    info["name"] = name.strip() or info["name"]
    srid = (
        CoordinateSystem.objects.filter(srid__gte=CUSTOM_SRID_MIN).aggregate(m=Max("srid"))["m"]
        or CUSTOM_SRID_MIN - 1
    ) + 1
    if srid > CUSTOM_SRID_MAX:
        raise ValidationError("No custom SRIDs left.")
    with connection.cursor() as cursor:
        # SECURITY DEFINER function: the app role can't write spatial_ref_sys itself.
        cursor.execute(
            "SELECT app_register_srs(%s, %s, %s)", [srid, _postgis_srtext(crs), info["proj4"]]
        )
    return CoordinateSystem.objects.create(
        code=f"CUSTOM:{srid}",
        srid=srid,
        is_builtin=False,
        district=district,
        created_by=user,
        notes=notes,
        **info,
    )


# --- Defaults ------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedDefault:
    crs: CoordinateSystem
    source: str  # "user", "district" or "system"


def system_default() -> CoordinateSystem:
    return SystemCrsSettings.objects.select_related("default_crs").get(pk=1).default_crs


def resolve_default(user: User | None, district_id: int | None) -> ResolvedDefault:
    """The CRS a new project starts with: the user's preference, else the
    district default, else the system default. Existing projects keep theirs."""
    if user is not None:
        pref = UserCrsPreference.objects.filter(user=user, preferred_crs__is_active=True).first()
        if pref:
            return ResolvedDefault(pref.preferred_crs, "user")
    if district_id is not None:
        setting = DistrictCrsSettings.objects.filter(
            district_id=district_id, default_crs__is_active=True
        ).first()
        if setting:
            return ResolvedDefault(setting.default_crs, "district")
    return ResolvedDefault(system_default(), "system")


# --- Transforming --------------------------------------------------------------


@dataclass(frozen=True)
class Operation:
    name: str
    pipeline: str
    accuracy_m: float | None  # None: unknown
    pinned: bool  # chosen by an administrator rather than PROJ's ranking


def _accuracy(value: float | None) -> float | None:
    return None if value is None or value < 0 else float(value)


def candidate_operations(source: CoordinateSystem, target: CoordinateSystem) -> list[Operation]:
    """Every operation PROJ knows between two systems, best first."""
    group = TransformerGroup(as_pyproj(source), as_pyproj(target), always_xy=True)
    return [
        Operation(t.description, t.definition, _accuracy(t.accuracy), pinned=False)
        for t in group.transformers
    ]


def _operation(
    source: CoordinateSystem, target: CoordinateSystem
) -> tuple[Transformer, Operation, bool]:
    """The single operation used between two systems, and whether we apply it
    forwards (True) or backwards.

    Each unordered pair of systems uses exactly one operation: the pinned one if
    an administrator chose it, otherwise PROJ's best for the pair in canonical
    (code-sorted) order. The other direction applies that same operation in
    reverse, so the two directions are exact inverses of each other.
    """
    pinned = PreferredTransformation.objects.filter(source=source, target=target).first()
    forward = True
    if pinned is None:
        pinned = PreferredTransformation.objects.filter(source=target, target=source).first()
        forward = False
    if pinned is not None:
        op = Operation(pinned.name, pinned.pipeline, pinned.accuracy_m, pinned=True)
        return Transformer.from_pipeline(pinned.pipeline), op, forward

    forward = source.code <= target.code
    first, second = (source, target) if forward else (target, source)
    candidates = candidate_operations(first, second)
    if not candidates:
        raise ValidationError(f"PROJ knows no way to transform {source.code} to {target.code}.")
    best = candidates[0]
    return Transformer.from_pipeline(best.pipeline), best, forward


def _exact_inverse(
    transformer: Transformer, xs: list[float], ys: list[float], iterations: int = 4
) -> tuple[list[float], list[float]]:
    """Applies `transformer` backwards so that forward(result) == input.

    PROJ's own inverse of a 2D datum shift is not exact: the ellipsoidal height
    produced on the way forward is discarded, which leaves a round-trip error of
    up to ~3 mm across Ghana. Starting from PROJ's inverse, each iteration removes
    the remaining error (it converges to ~1e-9 of the unit in 2-3 steps).
    """
    guess_x, guess_y = transformer.transform(
        xs, ys, direction=TransformDirection.INVERSE, errcheck=True
    )
    x, y = list(guess_x), list(guess_y)
    for _ in range(iterations):
        fx, fy = transformer.transform(x, y, errcheck=True)
        back_x, back_y = transformer.transform(
            fx, fy, direction=TransformDirection.INVERSE, errcheck=True
        )
        x = [xi + (g - b) for xi, g, b in zip(x, guess_x, back_x, strict=True)]
        y = [yi + (g - b) for yi, g, b in zip(y, guess_y, back_y, strict=True)]
    return x, y


def describe_operation(source: CoordinateSystem, target: CoordinateSystem) -> Operation:
    if source.pk == target.pk:
        return Operation("No change (same system)", "+proj=noop", 0.0, pinned=False)
    return _operation(source, target)[1]


def transform_points(
    points: Sequence[Coord], source: CoordinateSystem, target: CoordinateSystem
) -> tuple[list[tuple[float, float]], Operation]:
    """Transforms x/y (east/north, or lon/lat) points; returns them with the
    operation used, so callers can state its accuracy."""
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    if source.pk == target.pk:
        return list(zip(xs, ys, strict=True)), describe_operation(source, target)
    transformer, op, forward = _operation(source, target)
    try:
        if forward:
            out_x, out_y = transformer.transform(xs, ys, errcheck=True)
        else:
            out_x, out_y = _exact_inverse(transformer, xs, ys)
    except ProjError as exc:
        raise ValidationError(f"Could not transform these coordinates: {exc}") from exc
    return list(zip(out_x, out_y, strict=True)), op


def transform_geojson(
    geometry: dict[str, Any], source: CoordinateSystem, target: CoordinateSystem
) -> tuple[dict[str, Any], Operation]:
    """Transforms every position of a GeoJSON geometry (any type)."""
    flat: list[Coord] = []

    def collect(coords: Any) -> None:
        if coords and isinstance(coords[0], int | float):
            flat.append(coords)
        else:
            for c in coords:
                collect(c)

    def rebuild(coords: Any, it: Any) -> Any:
        if coords and isinstance(coords[0], int | float):
            x, y = next(it)
            return [x, y, *coords[2:]]
        return [rebuild(c, it) for c in coords]

    if geometry.get("type") == "GeometryCollection":
        parts = [transform_geojson(g, source, target) for g in geometry.get("geometries", [])]
        op = parts[0][1] if parts else describe_operation(source, target)
        return {"type": "GeometryCollection", "geometries": [p[0] for p in parts]}, op
    if "coordinates" not in geometry:
        raise ValidationError("Geometry needs 'type' and 'coordinates'.")
    collect(geometry["coordinates"])
    points, op = transform_points(flat, source, target)
    return {
        "type": geometry["type"],
        "coordinates": rebuild(geometry["coordinates"], iter(points)),
    }, op


# --- Web maps ----------------------------------------------------------------------

_HELMERT_KEYS = ("x", "y", "z", "rx", "ry", "rz", "s")


def _towgs84(pipeline: str, forward: bool) -> list[float] | None:
    """+towgs84 parameters (position-vector convention, system -> WGS 84) from
    the Helmert step of an operation pipeline, or None if it has none."""
    for step in pipeline.split("step")[1:]:
        if "proj=helmert" not in step:
            continue
        params = dict(re.findall(r"(\w+)=([-\d.eE]+)", step))
        values = [float(params.get(key, 0)) for key in _HELMERT_KEYS]
        if "convention=coordinate_frame" in step:
            values[3:6] = [-v for v in values[3:6]]
        step_inverted = re.search(r"(^|\s)\+?inv(\s|$)", step) is not None
        if step_inverted == forward:  # applied WGS 84 -> system: flip
            values = [-v for v in values]
        return values
    return None


def web_proj4(system: CoordinateSystem) -> str:
    """PROJ string for web maps (proj4js) that reproduces the server's datum shift.

    pyproj's own PROJ strings drop the datum shift, which would put Accra-datum
    data about 300 m from where the server puts it. This adds +towgs84 from the
    operation the server uses to reach WGS 84 (pinned or best), so the map and
    the server agree.
    """
    wgs84 = CoordinateSystem.objects.filter(code="EPSG:4326").first()
    if wgs84 is None or system.pk == wgs84.pk:
        return system.proj4
    try:
        _, op, forward = _operation(system, wgs84)
    except ValidationError:
        return system.proj4
    values = _towgs84(op.pipeline, forward)
    if values is None or "+towgs84" in system.proj4:
        return system.proj4
    shift = ",".join(f"{v:g}" for v in (values if any(values[3:]) else values[:3]))
    return system.proj4.replace(" +no_defs", "") + f" +towgs84={shift} +no_defs"

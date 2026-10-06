"""Reading, converting and tiling rasters with GDAL."""

import json
import math
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

TILE = 256
WEB_MERCATOR_HALF = 20037508.342789244
MAX_ZOOM = 22
MAX_PIXELS = 60_000 * 60_000


def _srs(text: str) -> osr.SpatialReference:
    ref = osr.SpatialReference()
    try:
        ref.SetFromUserInput(text)
    except RuntimeError as exc:
        raise ValidationError(f"{text!r} isn't a coordinate system GDAL knows.") from exc
    ref.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return ref


def describe_crs(ref: osr.SpatialReference) -> str:
    code = ref.GetAuthorityCode(None)
    name = ref.GetName() or "unnamed"
    return f"{ref.GetAuthorityName(None)}:{code} {name}" if code else name


def inspect(path: Path, assigned_crs: str = "") -> dict[str, Any]:
    """Checks that a file is a georeferenced raster and describes it. Raises
    ValidationError with a message for the user when it can't be used."""
    try:
        ds = gdal.Open(str(path))
    except RuntimeError as exc:
        raise ValidationError(f"The file can't be read as a raster image: {exc}") from exc
    if ds is None or ds.RasterCount == 0:
        raise ValidationError("The file isn't a raster image.")
    if ds.RasterXSize * ds.RasterYSize > MAX_PIXELS:
        raise ValidationError("The image is too large (more than 60,000 by 60,000 pixels).")
    transform = ds.GetGeoTransform(can_return_null=True)
    if transform is None or (transform[1] == 1 and transform[5] == 1 and transform[0] == 0):
        raise ValidationError(
            "The image isn't georeferenced: it doesn't say where on the ground it is."
            " Export it from the drone software as a GeoTIFF."
        )
    if transform[2] != 0 or transform[4] != 0:
        raise ValidationError("The image is rotated. Export it north-up from the drone software.")
    ref = ds.GetSpatialRef()
    if ref is None:
        if not assigned_crs:
            raise ValidationError(
                "The image doesn't say which coordinate system it uses. Choose it and upload again."
            )
        ref = _srs(assigned_crs)
    else:
        ref = ref.Clone()
        ref.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    width, height = ds.RasterXSize, ds.RasterYSize
    x0, y0 = transform[0], transform[3]
    x1, y1 = x0 + width * transform[1], y0 + height * transform[5]
    to_wgs = osr.CoordinateTransformation(ref, _srs("EPSG:4326"))
    corners = [to_wgs.TransformPoint(x, y)[:2] for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    lons, lats = [c[0] for c in corners], [c[1] for c in corners]
    bounds = [min(lons), min(lats), max(lons), max(lats)]
    if not all(math.isfinite(v) for v in bounds) or bounds[1] < -85 or bounds[3] > 85:
        raise ValidationError(
            "The image's position can't be worked out from its coordinate system."
        )

    # Ground size of a pixel: exact for projected systems, from latitude for degrees.
    mid_lat = (bounds[1] + bounds[3]) / 2
    if ref.IsGeographic():
        resolution = abs(transform[1]) * 111_320 * math.cos(math.radians(mid_lat))
    else:
        resolution = abs(transform[1]) * ref.GetLinearUnits()
    max_zoom = min(
        MAX_ZOOM,
        max(
            0,
            math.ceil(math.log2(156543.03392804097 * math.cos(math.radians(mid_lat)) / resolution)),
        ),
    )
    return {
        "srs": ref,
        "crs": describe_crs(ref),
        "width": width,
        "height": height,
        "bands": ds.RasterCount,
        "resolution_m": resolution,
        "bounds": bounds,
        "max_zoom": max_zoom,
        "min_zoom": max(0, max_zoom - 10),
        "has_crs": ds.GetSpatialRef() is not None,
        # Some drone software writes these tags; used when the uploader gave none.
        "capture_date": ds.GetMetadataItem("CAPTURE_DATE") or "",
        "source": ds.GetMetadataItem("SOURCE") or "",
    }


def to_cog(source: Path, target: Path, srs: osr.SpatialReference, *, is_dem: bool) -> None:
    """Writes a cloud-optimised GeoTIFF in the file's own CRS (no resampling
    of the full-resolution pixels), with overviews for fast tiles."""
    options = gdal.TranslateOptions(
        format="COG",
        outputSRS=srs.ExportToWkt(),
        creationOptions=[
            "COMPRESS=DEFLATE",
            "BIGTIFF=IF_SAFER",
            f"RESAMPLING={'BILINEAR' if is_dem else 'AVERAGE'}",
        ],
    )
    try:
        gdal.Translate(str(target), str(source), options=options)
    except RuntimeError as exc:
        raise ValidationError(f"The image couldn't be converted: {exc}") from exc


def value_range(path: Path) -> list[float] | None:
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    try:
        low, high = band.ComputeRasterMinMax(False)
    except RuntimeError:
        return None
    return [float(low), float(high)]


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) of an XYZ tile in Web Mercator metres."""
    size = 2 * WEB_MERCATOR_HALF / (2**z)
    west = -WEB_MERCATOR_HALF + x * size
    north = WEB_MERCATOR_HALF - y * size
    return west, north - size, west + size, north


def lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    x = lon * WEB_MERCATOR_HALF / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) * WEB_MERCATOR_HALF / math.pi
    return x, y


def tile_intersects(bounds: list[float], z: int, x: int, y: int) -> bool:
    west, south, east, north = tile_bounds(z, x, y)
    w, s = lonlat_to_mercator(bounds[0], bounds[1])
    e, n = lonlat_to_mercator(bounds[2], bounds[3])
    return not (east < w or west > e or north < s or south > n)


def render_tile(
    path: Path, z: int, x: int, y: int, *, scale: list[float] | None = None
) -> bytes | None:
    """A 256-pixel PNG tile of the raster (transparent where it has no data),
    or None when the tile is empty. `scale` stretches a single-band raster
    (an elevation model) to grey."""
    west, south, east, north = tile_bounds(z, x, y)
    warped = gdal.Warp(
        "",
        str(path),
        options=gdal.WarpOptions(
            format="MEM",
            dstSRS="EPSG:3857",
            outputBounds=(west, south, east, north),
            width=TILE,
            height=TILE,
            resampleAlg="bilinear",
            dstAlpha=True,
        ),
    )
    if warped is None:
        return None
    alpha = warped.GetRasterBand(warped.RasterCount)
    if alpha.ComputeRasterMinMax(False)[1] == 0:
        return None
    colour_bands = warped.RasterCount - 1
    if colour_bands >= 3:
        band_list = [1, 2, 3, warped.RasterCount]
        scale_params = None
    else:
        band_list = [1, 1, 1, warped.RasterCount]
        low, high = scale or [0.0, 255.0]
        if high <= low:
            high = low + 1
        # Stretch the data bands; leave alpha as it is.
        scale_params = [
            [low, high, 0, 255],
            [low, high, 0, 255],
            [low, high, 0, 255],
            [0, 255, 0, 255],
        ]
    name = f"/vsimem/tile-{id(warped)}-{z}-{x}-{y}.png"
    gdal.Translate(
        name,
        warped,
        options=gdal.TranslateOptions(
            format="PNG", bandList=band_list, outputType=gdal.GDT_Byte, scaleParams=scale_params
        ),
    )
    handle = gdal.VSIFOpenL(name, "rb")
    try:
        gdal.VSIFSeekL(handle, 0, 2)
        size = gdal.VSIFTellL(handle)
        gdal.VSIFSeekL(handle, 0, 0)
        data: bytes = bytes(gdal.VSIFReadL(1, size, handle))
    finally:
        gdal.VSIFCloseL(handle)
        gdal.Unlink(name)
    return data


def contours(
    path: Path, interval: float, limit: int
) -> tuple[list[tuple[float, dict[str, Any]]], str]:
    """Contour lines of an elevation model as (elevation, GeoJSON geometry) in
    the raster's own CRS, and that CRS as WKT."""
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    ref = ds.GetSpatialRef()
    memory = ogr.GetDriverByName(
        "MEM" if ogr.GetDriverByName("MEM") else "Memory"
    ).CreateDataSource("c")
    layer = memory.CreateLayer("contours", ref, ogr.wkbLineString)
    layer.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("elevation", ogr.OFTReal))
    nodata = band.GetNoDataValue()
    gdal.ContourGenerate(
        band, interval, 0, [], 1 if nodata is not None else 0, nodata or 0, layer, 0, 1
    )
    if layer.GetFeatureCount() > limit:
        raise ValidationError(
            f"That interval gives {layer.GetFeatureCount():,} contour lines;"
            f" the limit is {limit:,}. Choose a larger interval."
        )
    lines = []
    for feature in layer:
        geometry = feature.GetGeometryRef()
        if geometry is None or geometry.GetPointCount() < 2:
            continue
        geometry.FlattenTo2D()
        lines.append(
            (
                feature.GetField("elevation"),
                json.loads(geometry.ExportToJson(["SIGNIFICANT_FIGURES=17"])),
            )
        )
    return lines, ref.ExportToWkt()

"""Finds where the ground has changed between two orthophotos of the same
place: the first sign of development nobody applied for.

Both images are brought to one grid (about a metre a cell), turned to
brightness, and compared after taking out the overall difference in light
between the two flights. Cells that changed by more than a threshold, in
patches at least the size of a small structure, come back as shapes.

Light, shadow and season change pictures too, so every shape is only a place
to look: an officer confirms it on the ground.
"""

import json
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

CELL_M = 1.0
MIN_AREA_M2 = 16.0  # a kiosk-sized change; smaller patches are noise
THRESHOLD = 45.0  # brightness (0-255) a cell must change by
MAX_CELLS = 60_000_000  # about 7.7 x 7.7 km at a metre a cell
MAX_SHAPES = 5000


def _open(path: Path) -> gdal.Dataset:
    try:
        return gdal.Open(str(path))
    except RuntimeError as exc:
        raise ValidationError(f"An image couldn't be read: {exc}") from exc


def _brightness(ds: gdal.Dataset) -> tuple[Any, Any]:
    """(brightness 0-255 as float, where the image has data)."""
    import numpy as np

    # Warped with dstAlpha: the last band says where there is data; the rest
    # are the picture (an alpha band the image came with is not part of it).
    bands = [ds.GetRasterBand(i) for i in range(1, ds.RasterCount)]
    picture = [b for b in bands if b.GetColorInterpretation() != gdal.GCI_AlphaBand][:3]
    grey = np.zeros((ds.RasterYSize, ds.RasterXSize), dtype="float32")
    for band in picture:
        grey += band.ReadAsArray().astype("float32")
    grey /= max(1, len(picture))
    valid = ds.GetRasterBand(ds.RasterCount).ReadAsArray() > 0
    return grey, valid


def detect(
    before: Path,
    after: Path,
    *,
    cell_m: float = CELL_M,
    min_area_m2: float = MIN_AREA_M2,
    threshold: float = THRESHOLD,
) -> list[dict[str, Any]]:
    """The changed patches, each as {"geometry": GeoJSON in WGS 84, "area_m2",
    "change": mean brightness change 0-255}, largest first."""
    import numpy as np

    first, second = _open(before), _open(after)
    target = osr.SpatialReference(wkt=second.GetProjection())
    if not target.ExportToWkt():
        raise ValidationError("The later image has no coordinate system.")
    unit_m = target.GetLinearUnits() if target.IsProjected() else 111_320.0
    cell = cell_m / unit_m

    def extent(ds: gdal.Dataset) -> tuple[float, float, float, float]:
        # In the target system, whatever system the image itself is in.
        warped = gdal.Warp("", ds, format="VRT", dstSRS=target.ExportToWkt())
        gt = warped.GetGeoTransform()
        west, north = gt[0], gt[3]
        east, south = west + gt[1] * warped.RasterXSize, north + gt[5] * warped.RasterYSize
        return min(west, east), min(south, north), max(west, east), max(south, north)

    a, b = extent(first), extent(second)
    west, south, east, north = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if east - west < 3 * cell or north - south < 3 * cell:
        raise ValidationError("The two images don't cover the same ground.")
    columns, rows = int((east - west) / cell), int((north - south) / cell)
    if columns * rows > MAX_CELLS:
        raise ValidationError(
            "The area the two images share is too large to compare in one go."
            " Compare images of one neighbourhood at a time."
        )

    def on_grid(ds: gdal.Dataset) -> gdal.Dataset:
        return gdal.Warp(
            "",
            ds,
            format="MEM",
            dstSRS=target.ExportToWkt(),
            outputBounds=(west, south, east, north),
            width=columns,
            height=rows,
            resampleAlg="average",
            dstAlpha=True,
        )

    grey_a, valid_a = _brightness(on_grid(first))
    grey_b, valid_b = _brightness(on_grid(second))
    valid = valid_a & valid_b
    if not valid.any():
        raise ValidationError("The two images don't cover the same ground.")
    # The flights differ in light: compare each image with its own typical brightness.
    shift = float(np.median(grey_b[valid]) - np.median(grey_a[valid]))
    difference = np.abs(grey_b - grey_a - shift)
    changed = ((difference > threshold) & valid).astype("uint8")

    driver = gdal.GetDriverByName("MEM")
    mask = driver.Create("", columns, rows, 1, gdal.GDT_Byte)
    mask.SetGeoTransform((west, cell, 0.0, north, 0.0, -cell))
    mask.SetProjection(target.ExportToWkt())
    band = mask.GetRasterBand(1)
    band.WriteArray(changed)
    # Drop specks: patches smaller than the smallest structure worth a visit.
    smallest = max(2, int(min_area_m2 / (cell_m * cell_m)))
    gdal.SieveFilter(band, None, band, smallest, 8)

    vector = ogr.GetDriverByName("Memory").CreateDataSource("changes")
    layer = vector.CreateLayer("changes", srs=target, geom_type=ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("changed", ogr.OFTInteger))
    gdal.Polygonize(band, band, layer, 0, ["8CONNECTED=8"])

    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_wgs = osr.CoordinateTransformation(target, wgs)
    found: list[dict[str, Any]] = []
    for feature in layer:
        shape = feature.GetGeometryRef()
        area = shape.GetArea() * unit_m * unit_m
        if area < min_area_m2:
            continue
        # Mean change inside the patch's box: how strong the signal is.
        x0, x1, y0, y1 = shape.GetEnvelope()
        c0, c1 = max(0, int((x0 - west) / cell)), min(columns, int((x1 - west) / cell) + 1)
        r0, r1 = max(0, int((north - y1) / cell)), min(rows, int((north - y0) / cell) + 1)
        window = difference[r0:r1, c0:c1]
        inside = changed[r0:r1, c0:c1] > 0
        strength = float(window[inside].mean()) if inside.any() else 0.0
        outline = shape.SimplifyPreserveTopology(cell / 2).Clone()
        outline.Transform(to_wgs)
        found.append(
            {
                "geometry": json.loads(outline.ExportToJson()),
                "area_m2": round(area, 1),
                "change": round(strength, 1),
            }
        )
    found.sort(key=lambda item: -item["area_m2"])
    return found[:MAX_SHAPES]

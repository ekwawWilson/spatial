"""Checks that the shared test datasets exist and still contain the seeded
conditions later phases depend on. Geometry checks run in the native CRS."""

import csv
from pathlib import Path

import pytest
from osgeo import ogr, osr

ogr.UseExceptions()
osr.UseExceptions()
pytestmark = pytest.mark.fixtures

FT_PER_M = 1 / 0.3047997101815088  # Gold Coast foot, as used by EPSG:2136


def features(path: Path, layer: str | None = None) -> list[ogr.Feature]:
    ds = ogr.Open(str(path))
    lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
    items = [f.Clone() for f in lyr]
    ds = None
    return items


def by(feats: list[ogr.Feature], field: str, value: str) -> ogr.Feature:
    return next(f for f in feats if f.GetField(field) == value)


def test_every_format_has_every_layer(fixtures_dir, fixture_manifest):
    gen = fixtures_dir / "generated"
    for name, count in fixture_manifest["layers"].items():
        assert len(features(gen / "sample.gpkg", name)) == count
        for sub, ext in (("geojson", "geojson"), ("shp", "shp"), ("kml", "kml")):
            assert len(features(gen / sub / f"{name}.{ext}")) == count, f"{sub}/{name}"
        assert (gen / "shp" / f"{name}.zip").exists()


def best_epsg_match(ref: osr.SpatialReference) -> tuple[str | None, int]:
    """EPSG code and confidence (0-100) of the closest match. Shapefile .prj
    files hold ESRI WKT, which carries no EPSG code of its own."""
    matches = ref.FindMatches()
    if not matches:
        return None, 0
    match, confidence = matches[0]
    return match.GetAuthorityCode(None), confidence


def test_native_files_carry_ghana_national_grid(fixtures_dir):
    gen = fixtures_dir / "generated"
    for path in (gen / "sample.gpkg", gen / "shp" / "parcels.shp"):
        ds = ogr.Open(str(path))
        code, confidence = best_epsg_match(ds.GetLayer(0).GetSpatialRef())
        assert code == "2136", path
        assert confidence >= 70, (path, confidence)


def test_no_crs_shapefile_really_has_no_crs(fixtures_dir):
    folder = fixtures_dir / "generated" / "shp_no_crs"
    assert not (folder / "parcels.prj").exists()
    ds = ogr.Open(str(folder / "parcels.shp"))
    assert ds.GetLayer(0).GetSpatialRef() is None


def test_seeded_community_overlap(fixtures_dir, fixture_manifest):
    seed = fixture_manifest["seeded"]["community_overlap"]
    comms = features(fixtures_dir / "generated" / "sample.gpkg", "communities")
    a, b = by(comms, "code", seed["a"]), by(comms, "code", seed["b"])
    overlap = a.GetGeometryRef().Intersection(b.GetGeometryRef())
    # The strip is axis-aligned in UTM but rotated ~0.2 deg in the national grid,
    # so measure width as area / length rather than from the bounding box.
    width_m = overlap.GetArea() / FT_PER_M**2 / seed["length_m"]
    assert width_m == pytest.approx(seed["width_m"], rel=0.01)


def test_seeded_building_in_flood_zone(fixtures_dir, fixture_manifest):
    seed = fixture_manifest["seeded"]["building_in_flood_zone"]
    gpkg = fixtures_dir / "generated" / "sample.gpkg"
    zone = by(features(gpkg, "flood_zones"), "zone_id", seed["zone_id"]).GetGeometryRef()
    hits = [
        b.GetField("property_id")
        for b in features(gpkg, "buildings")
        if b.GetGeometryRef().Intersects(zone)
    ]
    assert hits == [seed["property_id"]]


def test_seeded_setback_breach(fixtures_dir, fixture_manifest):
    seed = fixture_manifest["seeded"]["setback_breach"]
    gpkg = fixtures_dir / "generated" / "sample.gpkg"
    parcels = features(gpkg, "parcels")
    min_setbacks = {}
    for b in features(gpkg, "buildings"):
        pid = "P-" + b.GetField("property_id")[2:]
        boundary = by(parcels, "parcel_id", pid).GetGeometryRef().GetBoundary()
        min_setbacks[b.GetField("property_id")] = b.GetGeometryRef().Distance(boundary) / FT_PER_M
    breaches = sorted(k for k, v in min_setbacks.items() if v < seed["normal_setback_m"] - 0.01)
    assert breaches == [seed["property_id"]]
    assert min_setbacks[seed["property_id"]] == pytest.approx(seed["setback_m"], abs=0.01)


def test_dxf_keeps_layers_as_cad_layers(fixtures_dir, fixture_manifest):
    names = {f.GetField("Layer") for f in features(fixtures_dir / "generated" / "sample.dxf")}
    assert names == set(fixture_manifest["layers"])


def test_drone_orthophoto_is_georeferenced(fixtures_dir):
    from osgeo import gdal

    ds = gdal.Open(str(fixtures_dir / "generated" / "drone_ortho.tif"))
    assert (ds.RasterXSize, ds.RasterYSize, ds.RasterCount) == (200, 200, 3)
    assert ds.GetGeoTransform()[1] == 1.0
    assert ds.GetMetadataItem("CAPTURE_DATE") == "2026-09-01"


def test_control_points_file_has_expected_columns(fixtures_dir):
    with open(fixtures_dir / "source" / "control_points.csv", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == [
            "point_id",
            "description",
            "easting_ft_2136",
            "northing_ft_2136",
            "lon_wgs84",
            "lat_wgs84",
            "height_m",
            "source",
            "accuracy_m",
        ]
        rows = list(reader)
    if not rows:
        pytest.skip("Official control points not provided yet (see fixtures/README.md)")

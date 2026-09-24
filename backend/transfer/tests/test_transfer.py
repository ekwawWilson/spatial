"""Phase 5: import and export."""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from django.urls import reverse
from osgeo import ogr

from core.models import Role
from crs.models import CoordinateSystem
from projects.models import Feature, Layer, PlanProject
from transfer import gdal_io
from transfer.models import DataJob

ogr.UseExceptions()
pytestmark = pytest.mark.django_db


# --- Helpers ----------------------------------------------------------------------------


@pytest.fixture
def planner_client(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def project(planner_client):
    response = planner_client.post(reverse("project-list"), {"name": "Import tests"}, format="json")
    return PlanProject.objects.get(pk=response.json()["id"])


@pytest.fixture
def gen(fixtures_dir) -> Path:
    return Path(fixtures_dir) / "generated"


def upload(client, project, path: Path, **extra: Any):
    with open(path, "rb") as fh:
        return client.post(
            reverse("datajob-upload"),
            {"project": project.id, "file": fh, **extra},
            format="multipart",
        )


def run(client, job_id, layers, capture):
    with capture(execute=True):
        response = client.post(
            reverse("datajob-run", args=[job_id]), {"layers": layers}, format="json"
        )
    return response


def new_layer_item(
    inspected: dict[str, Any], source: str, geometry_type: str, crs: str, **extra: Any
) -> dict[str, Any]:
    layer = next(item for item in inspected["layers"] if item["name"] == source)
    return {
        "source": source,
        "crs": crs,
        "crs_confirmed": True,
        "new_layer": {
            "name": f"{source} ({inspected['format']})",
            "domain": "B",
            "geometry_type": geometry_type,
        },
        "fields": [
            {"source": f["name"], "target": f["suggested_name"], "type": f["type"]}
            for f in layer["fields"]
        ],
        **extra,
    }


def export(client, project, layer_ids, fmt, capture, **extra):
    with capture(execute=True):
        response = client.post(
            reverse("datajob-export"),
            {"project": project.id, "layer_ids": layer_ids, "format": fmt, **extra},
            format="json",
        )
    job = DataJob.objects.get(pk=response.json()["id"])
    assert job.status == "done", job.error
    return job


def read_all(path: str, layer: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    """(exact geometry JSON, attributes) per feature, sorted, for comparisons."""
    ds = ogr.Open(path)
    lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
    out = []
    for feature in lyr:
        geom = feature.GetGeometryRef()
        attrs = {
            feature.GetFieldDefnRef(i).GetName(): feature.GetField(i)
            for i in range(feature.GetFieldCount())
        }
        out.append((geom.ExportToJson(["SIGNIFICANT_FIGURES=17"]) if geom else "", attrs))
    return sorted(out, key=lambda item: item[0])


def coords(geometry_json: str) -> list[float]:
    flat: list[float] = []

    def walk(c: Any) -> None:
        if isinstance(c[0], int | float):
            flat.extend(c[:2])
        else:
            for part in c:
                walk(part)

    walk(json.loads(geometry_json)["coordinates"])
    return flat


def unzip(job: DataJob, tmp_path: Path) -> Path:
    from transfer.tasks import job_dir

    target = tmp_path / f"out-{job.pk}"
    with zipfile.ZipFile(job_dir(job) / "result" / job.result_name) as zf:
        zf.extractall(target)
    return target


# --- Inspection ----------------------------------------------------------------------------


def test_inspection_reports_layers_fields_and_crs(planner_client, project, gen):
    response = upload(planner_client, project, gen / "shp" / "buildings.zip")
    assert response.status_code == 201, response.data
    [layer] = response.json()["inspection"]["layers"]
    assert layer["feature_count"] == 6
    assert layer["crs"]["found"] and layer["crs"]["epsg"] == 2136
    assert "property_i" in [f["name"] for f in layer["fields"]]  # shapefile's 10-char limit
    assert layer["geometry_types"] == {"Polygon": 6}


def test_unsupported_file_type(planner_client, project, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    response = upload(planner_client, project, path)
    assert response.status_code == 400 and "Unsupported file type" in json.dumps(response.json())


# --- CRS must be chosen when the file has none (gate) -----------------------------------------


def test_a_file_without_crs_cannot_run_until_one_is_confirmed(
    planner_client, project, gen, tmp_path, django_capture_on_commit_callbacks
):
    archive = tmp_path / "no_crs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for part in (gen / "shp_no_crs").iterdir():
            zf.write(part, part.name)
    inspected = upload(planner_client, project, archive).json()
    layer = inspected["inspection"]["layers"][0]
    assert layer["crs"]["found"] is False

    item = new_layer_item(inspected["inspection"], "parcels", "polygon", "EPSG:2136")
    unconfirmed = {**item, "crs_confirmed": False}
    refused = run(
        planner_client, inspected["id"], [unconfirmed], django_capture_on_commit_callbacks
    )
    assert refused.status_code == 400
    assert "has no coordinate system" in json.dumps(refused.json())

    ok = run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    assert ok.status_code == 202
    job = DataJob.objects.get(pk=inspected["id"])
    assert job.status == "done", job.error
    assert job.report["layers"][0]["imported"] == 6


def test_cad_files_always_need_crs_confirmation(
    planner_client, project, gen, django_capture_on_commit_callbacks
):
    inspected = upload(planner_client, project, gen / "sample.dxf").json()
    assert inspected["inspection"]["crs_confirmation_required"] is True
    item = {
        **new_layer_item(inspected["inspection"], "entities", "polygon", "EPSG:2136"),
        "crs_confirmed": False,
    }
    assert (
        run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks).status_code
        == 400
    )


# --- Round trips per format (gate) -------------------------------------------------------------

ROUND_TRIPS = [
    # (fixture, format, source layer, geometry type, CRS, export format, tolerance in CRS units)
    ("sample.gpkg", "gpkg", "parcels", "polygon", "EPSG:2136", "gpkg", 0.0),
    ("shp/parcels.zip", "shp_zip", "parcels", "polygon", "EPSG:2136", "shp", 0.0),
    ("geojson/parcels.geojson", "geojson", "parcels", "polygon", "EPSG:4326", "geojson", 0.0),
    ("geojson/streets.geojson", "geojson", "streets", "line", "EPSG:4326", "geojson", 0.0),
    ("geojson/drains.geojson", "geojson", "drains", "line", "EPSG:4326", "geojson", 0.0),
    ("kml/parcels.kml", "kml", "parcels", "polygon", "EPSG:4326", "kml", 1e-9),  # ~0.1 mm
]


@pytest.mark.parametrize("fixture,fmt,source,geometry_type,crs,export_fmt,tolerance", ROUND_TRIPS)
def test_round_trip(
    planner_client,
    project,
    gen,
    tmp_path,
    django_capture_on_commit_callbacks,
    fixture,
    fmt,
    source,
    geometry_type,
    crs,
    export_fmt,
    tolerance,
):
    inspected = upload(planner_client, project, gen / fixture).json()
    item = new_layer_item(inspected["inspection"], source, geometry_type, crs)
    run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    job = DataJob.objects.get(pk=inspected["id"])
    assert job.status == "done", job.error
    report = job.report["layers"][0]
    assert report["skipped"] == 0, report

    exported = export(
        planner_client,
        project,
        [report["target_layer"]],
        export_fmt,
        django_capture_on_commit_callbacks,
    )
    folder = unzip(exported, tmp_path)
    ext = {"gpkg": ".gpkg", "shp": ".shp", "geojson": ".geojson", "kml": ".kml"}[export_fmt]
    [out_file] = list(folder.glob(f"*{ext}"))

    original_path = f"/vsizip/{gen / fixture}" if fmt == "shp_zip" else str(gen / fixture)
    original = read_all(original_path, source if fmt == "gpkg" else None)
    result = read_all(str(out_file), report["target_name"] if export_fmt == "gpkg" else None)
    assert len(original) == len(result)
    for (g_in, attrs_in), (g_out, attrs_out) in zip(original, result, strict=True):
        a, b = coords(g_in), coords(g_out)
        assert len(a) == len(b)
        assert max(abs(x - y) for x, y in zip(a, b, strict=True)) <= tolerance, (
            fixture,
            g_in,
            g_out,
        )
        if export_fmt != "kml":
            # Attribute values survive (names may differ: shapefile truncation is mapped back).
            assert sorted(map(str, attrs_in.values())) == sorted(map(str, attrs_out.values()))


def test_dxf_round_trip_keeps_geometry_and_cad_layers(
    planner_client, project, gen, tmp_path, django_capture_on_commit_callbacks
):
    inspected = upload(planner_client, project, gen / "sample.dxf").json()
    item = {
        **new_layer_item(inspected["inspection"], "entities", "polygon", "EPSG:2136"),
        "cad_layers": ["parcels"],
        "fields": [],
    }
    run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    job = DataJob.objects.get(pk=inspected["id"])
    assert job.status == "done", job.error
    assert job.report["layers"][0]["imported"] == 6
    exported = export(
        planner_client,
        project,
        [job.report["layers"][0]["target_layer"]],
        "dxf",
        django_capture_on_commit_callbacks,
    )
    [dxf] = list(unzip(exported, tmp_path).glob("*.dxf"))
    original = [g for g, a in read_all(str(gen / "sample.dxf")) if a["Layer"] == "parcels"]
    result = [g for g, _ in read_all(str(dxf))]
    for g_in, g_out in zip(sorted(original), sorted(result), strict=True):
        assert (
            max(abs(x - y) for x, y in zip(coords(g_in), coords(g_out), strict=True)) <= 1e-6
        )  # feet


def test_shapefile_export_maps_long_names_back_on_reimport(
    planner_client, project, gen, tmp_path, django_capture_on_commit_callbacks
):
    inspected = upload(planner_client, project, gen / "sample.gpkg").json()
    item = new_layer_item(inspected["inspection"], "buildings", "polygon", "EPSG:2136")
    run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    layer_id = DataJob.objects.get(pk=inspected["id"]).report["layers"][0]["target_layer"]
    exported = export(
        planner_client, project, [layer_id], "shp", django_capture_on_commit_callbacks
    )
    from transfer.tasks import job_dir

    reinspected = upload(
        planner_client, project, job_dir(exported) / "result" / exported.result_name
    ).json()
    fields = {
        f["name"]: f["suggested_name"] for f in reinspected["inspection"]["layers"][0]["fields"]
    }
    assert fields["property_i"] == "property_id"


# --- Import behaviour --------------------------------------------------------------------------


def geojson_file(tmp_path: Path, features: list[dict[str, Any]], name: str = "in.geojson") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


SQUARE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001], [0, 0]]],
}
BOWTIE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [0.001, 0.001], [0.001, 0], [0, 0.001], [0, 0]]],
}


def feature(geometry, **props):
    return {"type": "Feature", "geometry": geometry, "properties": props}


@pytest.mark.parametrize(
    "policy,imported,skipped,fixed,status",
    [
        ("skip", 1, 1, 0, "done"),
        ("fix", 2, 0, 1, "done"),
        ("abort", 0, 0, 0, "failed"),
    ],
)
def test_invalid_geometry_policies(
    planner_client,
    project,
    tmp_path,
    django_capture_on_commit_callbacks,
    policy,
    imported,
    skipped,
    fixed,
    status,
):
    path = geojson_file(tmp_path, [feature(SQUARE, name="ok"), feature(BOWTIE, name="bowtie")])
    inspected = upload(planner_client, project, path).json()
    item = new_layer_item(
        inspected["inspection"], "in", "polygon", "EPSG:4326", invalid_geometry=policy
    )
    run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    job = DataJob.objects.get(pk=inspected["id"])
    assert job.status == status, job.error
    if status == "done":
        report = job.report["layers"][0]
        assert (report["imported"], report["skipped"], report["fixed_geometries"]) == (
            imported,
            skipped,
            fixed,
        )
    else:
        assert "Row 2" in job.error
        assert not Layer.objects.filter(name="in (geojson)").exists()  # nothing half imported


def test_values_that_dont_fit_are_blanked_and_reported(
    planner_client, project, tmp_path, django_capture_on_commit_callbacks
):
    layer = planner_client.post(
        reverse("layer-list"),
        {
            "project": project.id,
            "name": "Target",
            "geometry_type": "polygon",
            "crs": CoordinateSystem.objects.get(code="EPSG:4326").id,
            "schema": [{"name": "floors", "type": "integer"}],
        },
        format="json",
    ).json()
    path = geojson_file(tmp_path, [feature(SQUARE, floors="two"), feature(SQUARE, floors=3)])
    inspected = upload(planner_client, project, path).json()
    item = {
        "source": "in",
        "crs": "EPSG:4326",
        "target_layer": layer["id"],
        "fields": [{"source": "floors", "target": "floors"}],
        "duplicates": "keep",
    }
    run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    report = DataJob.objects.get(pk=inspected["id"]).report["layers"][0]
    assert report["imported"] == 2 and report["blanked_values"] == 1 and report["duplicates"] == 1
    assert sorted(
        str(f.properties["floors"]) for f in Feature.objects.filter(layer_id=layer["id"])
    ) == ["3", "None"]


def test_importing_into_a_layer_in_another_crs_converts_explicitly(
    planner_client, project, gen, django_capture_on_commit_callbacks
):
    target = planner_client.post(
        reverse("layer-list"),
        {"project": project.id, "name": "Grid parcels", "geometry_type": "polygon"},
        format="json",
    ).json()
    assert target["crs_detail"]["code"] == "EPSG:2136"
    inspected = upload(planner_client, project, gen / "geojson" / "parcels.geojson").json()
    item = {"source": "parcels", "crs": "EPSG:4326", "target_layer": target["id"], "fields": []}
    run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    report = DataJob.objects.get(pk=inspected["id"]).report["layers"][0]
    assert report["imported"] == 6
    assert (
        "Accra to WGS 84" in report["operation"]["name"] and report["operation"]["accuracy_m"] >= 1
    )


def test_csv_with_coordinate_columns(
    planner_client, project, tmp_path, django_capture_on_commit_callbacks
):
    path = tmp_path / "points.csv"
    path.write_text("name,x,y\nBorehole 1,1190631.45,337708.94\nBorehole 2,1190700.00,337800.00\n")
    inspected = upload(planner_client, project, path).json()
    assert inspected["inspection"]["crs_confirmation_required"] is True
    item = new_layer_item(inspected["inspection"], "points", "point", "EPSG:2136")
    run(planner_client, inspected["id"], [item], django_capture_on_commit_callbacks)
    job = DataJob.objects.get(pk=inspected["id"])
    assert job.status == "done", job.error
    assert job.report["layers"][0]["imported"] == 2


# --- Export behaviour ---------------------------------------------------------------------------


def test_export_in_a_chosen_crs_names_the_operation(
    planner_client, project, gen, tmp_path, django_capture_on_commit_callbacks
):
    inspected = upload(planner_client, project, gen / "sample.gpkg").json()
    run(
        planner_client,
        inspected["id"],
        [new_layer_item(inspected["inspection"], "parcels", "polygon", "EPSG:2136")],
        django_capture_on_commit_callbacks,
    )
    layer_id = DataJob.objects.get(pk=inspected["id"]).report["layers"][0]["target_layer"]
    exported = export(
        planner_client,
        project,
        [layer_id],
        "geojson",
        django_capture_on_commit_callbacks,
        crs="EPSG:4326",
    )
    readme = (unzip(exported, tmp_path) / "README.txt").read_text()
    assert "EPSG:4326" in readme and "Accra to WGS 84" in readme and "±" in readme


def test_export_a_selection(
    planner_client, project, gen, tmp_path, django_capture_on_commit_callbacks
):
    inspected = upload(planner_client, project, gen / "sample.gpkg").json()
    run(
        planner_client,
        inspected["id"],
        [new_layer_item(inspected["inspection"], "parcels", "polygon", "EPSG:2136")],
        django_capture_on_commit_callbacks,
    )
    layer_id = DataJob.objects.get(pk=inspected["id"]).report["layers"][0]["target_layer"]
    two = list(Feature.objects.filter(layer_id=layer_id).values_list("id", flat=True)[:2])
    exported = export(
        planner_client,
        project,
        [layer_id],
        "gpkg",
        django_capture_on_commit_callbacks,
        feature_ids=two,
    )
    [gpkg] = list(unzip(exported, tmp_path).glob("*.gpkg"))
    assert ogr.Open(str(gpkg)).GetLayer(0).GetFeatureCount() == 2


def test_download_is_the_zip(planner_client, project, gen, django_capture_on_commit_callbacks):
    inspected = upload(planner_client, project, gen / "sample.gpkg").json()
    run(
        planner_client,
        inspected["id"],
        [new_layer_item(inspected["inspection"], "drains", "line", "EPSG:2136")],
        django_capture_on_commit_callbacks,
    )
    layer_id = DataJob.objects.get(pk=inspected["id"]).report["layers"][0]["target_layer"]
    exported = export(
        planner_client, project, [layer_id], "kmz", django_capture_on_commit_callbacks
    )
    response = planner_client.get(reverse("datajob-download", args=[exported.id]))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")


@pytest.mark.skipif(
    not gdal_io.dwg_available(),
    reason="LibreDWG isn't installed in this image (WITH_LIBREDWG=false)",
)
def test_dwg_round_trip(planner_client, project, gen, tmp_path, django_capture_on_commit_callbacks):
    inspected = upload(planner_client, project, gen / "sample.gpkg").json()
    run(
        planner_client,
        inspected["id"],
        [new_layer_item(inspected["inspection"], "parcels", "polygon", "EPSG:2136")],
        django_capture_on_commit_callbacks,
    )
    layer_id = DataJob.objects.get(pk=inspected["id"]).report["layers"][0]["target_layer"]
    exported = export(
        planner_client, project, [layer_id], "dwg", django_capture_on_commit_callbacks
    )
    [dwg] = list(unzip(exported, tmp_path).glob("*.dwg"))
    again = upload(planner_client, project, dwg)
    assert again.status_code == 201, again.data


def test_dwg_unavailable_is_explained(planner_client, project, tmp_path):
    if gdal_io.dwg_available():
        pytest.skip("LibreDWG is installed")
    path = tmp_path / "plan.dwg"
    path.write_bytes(b"AC1015")
    response = upload(planner_client, project, path)
    assert response.status_code == 400 and "DWG isn't available" in json.dumps(response.json())


# --- Safety, tenancy, roles ---------------------------------------------------------------------


def test_path_traversal_zip_is_refused(planner_client, project, tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../escape.shp", b"x")
    response = upload(planner_client, project, archive)
    assert response.status_code == 400 and "Unsafe path" in json.dumps(response.json())


def test_zip_bomb_is_refused(planner_client, project, tmp_path):
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.shp", b"\0" * 50_000_000)
    response = upload(planner_client, project, archive)
    assert response.status_code == 400 and "zip bomb" in json.dumps(response.json())


@pytest.mark.parametrize("role", [Role.FIELD_OFFICER, Role.VIEWER])
def test_only_planners_and_admins_move_data(api, members_a, district_a, project, gen, role):
    client = api(members_a[role], district_a)
    assert upload(client, project, gen / "sample.gpkg").status_code == 403
    assert (
        client.post(
            reverse("datajob-export"),
            {"project": project.id, "layer_ids": [1], "format": "gpkg"},
            format="json",
        ).status_code
        == 403
    )


def test_jobs_are_private_to_the_district(
    planner_client, project, gen, api, make_member, district_b
):
    job_id = upload(planner_client, project, gen / "sample.gpkg").json()["id"]
    other = api(make_member(district_b, Role.DISTRICT_ADMIN), district_b)
    assert other.get(reverse("datajob-detail", args=[job_id])).status_code == 404

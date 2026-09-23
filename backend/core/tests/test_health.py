import pytest
from django.urls import reverse

from core.health import REQUIRED_OGR_DRIVERS, check_gdal


@pytest.mark.django_db
def test_health_endpoint_reports_all_services_ok(client):
    response = client.get(reverse("health"))
    body = response.json()
    assert response.status_code == 200, body
    assert body["ok"] is True
    assert body["database"]["postgis"]
    assert body["gdal"]["missing_drivers"] == []


def test_gdal_has_every_driver_the_import_pipeline_needs():
    result = check_gdal()
    assert result["ok"], f"missing OGR drivers: {result['missing_drivers']}"
    assert set(REQUIRED_OGR_DRIVERS) >= {"ESRI Shapefile", "DXF", "GPKG", "GeoJSON"}


@pytest.mark.django_db
def test_openapi_schema_is_served(client):
    response = client.get(reverse("schema"))
    assert response.status_code == 200

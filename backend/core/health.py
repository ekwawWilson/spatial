"""Checks that every service the platform depends on is reachable and usable."""

from typing import Any

import redis
from django.conf import settings
from django.db import connection
from osgeo import gdal

# Vector formats the import/export pipeline (Phase 5) relies on. DWG is handled
# separately through LibreDWG, so it is not listed here.
REQUIRED_OGR_DRIVERS = ("ESRI Shapefile", "DXF", "KML", "LIBKML", "GPKG", "GeoJSON", "CSV")


def check_database() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT postgis_lib_version(), postgis_proj_version()")
        postgis, proj = cursor.fetchone()
    return {"ok": True, "postgis": postgis, "proj": proj}


def check_gdal() -> dict[str, Any]:
    missing = [name for name in REQUIRED_OGR_DRIVERS if gdal.GetDriverByName(name) is None]
    return {"ok": not missing, "version": gdal.__version__, "missing_drivers": missing}


def check_redis() -> dict[str, Any]:
    client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    return {"ok": bool(client.ping())}


def run_checks() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, check in (("database", check_database), ("gdal", check_gdal), ("redis", check_redis)):
        try:
            results[name] = check()
        except Exception as exc:  # noqa: BLE001 - report any failure, never crash the probe
            results[name] = {"ok": False, "error": str(exc)}
    results["ok"] = all(r["ok"] for r in results.values())
    return results

"""Seeds the built-in coordinate systems and the initial system default.

The default comes from settings.INITIAL_DEFAULT_CRS (EPSG:2136 unless changed)
and only applies to a new installation; administrators can change it at any
time afterwards.
"""

from typing import Any

from django.conf import settings
from django.db import migrations
from pyproj import CRS

BUILTINS: list[tuple[int, str]] = [
    (2136, "Ghana National Grid (Accra datum, Gold Coast feet): the long-standing survey and cadastral grid."),
    (25000, "Ghana Metre Grid (Leigon datum, metres), onshore and offshore."),
    (2137, "Defined by EPSG for offshore Ghana. For onshore metre work prefer EPSG:25000 unless instructed otherwise."),
    (4168, "Accra geographic coordinates (latitude/longitude on the Accra datum)."),
    (32630, "UTM zone 30N (WGS 84): most of Ghana, west of 0 deg."),
    (32631, "UTM zone 31N (WGS 84): far east of Ghana, east of 0 deg."),
    (4326, "WGS 84 latitude/longitude: GPS, GeoJSON, KML."),
    (3857, "Web Mercator: web basemaps (Google, OSM, Esri). Not for measurement."),
]


def seed(apps: Any, schema_editor: Any) -> None:
    from crs.services import describe

    CoordinateSystem = apps.get_model("crs", "CoordinateSystem")
    SystemCrsSettings = apps.get_model("crs", "SystemCrsSettings")
    for code, notes in BUILTINS:
        CoordinateSystem.objects.update_or_create(
            code=f"EPSG:{code}",
            defaults={**describe(CRS.from_epsg(code)), "srid": code, "is_builtin": True, "notes": notes},
        )
    default_code = settings.INITIAL_DEFAULT_CRS.upper()
    default = CoordinateSystem.objects.filter(code=default_code).first()
    if default is None:
        raise ValueError(f"INITIAL_DEFAULT_CRS {default_code} is not a built-in system.")
    SystemCrsSettings.objects.update_or_create(pk=1, defaults={"default_crs": default})


def unseed(apps: Any, schema_editor: Any) -> None:
    apps.get_model("crs", "SystemCrsSettings").objects.all().delete()
    apps.get_model("crs", "CoordinateSystem").objects.filter(is_builtin=True).delete()


class Migration(migrations.Migration):
    dependencies = [("crs", "0002_rls_audit_and_srs_function")]

    operations = [migrations.RunPython(seed, unseed)]

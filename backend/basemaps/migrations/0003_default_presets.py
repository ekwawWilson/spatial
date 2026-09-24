"""Adds OpenStreetMap and Esri World Imagery for every district on a new
installation (neither needs a key). Google and Bing need keys, so
administrators add them from the Basemaps page."""

from typing import Any

from django.db import migrations

DEFAULTS = ["osm", "esri_imagery"]


def add(apps: Any, schema_editor: Any) -> None:
    from basemaps.presets import PRESETS

    BasemapSource = apps.get_model("basemaps", "BasemapSource")
    for order, preset in enumerate(DEFAULTS):
        if not BasemapSource.objects.filter(preset=preset, district__isnull=True).exists():
            BasemapSource.objects.create(preset=preset, order=order, **PRESETS[preset])


def remove(apps: Any, schema_editor: Any) -> None:
    apps.get_model("basemaps", "BasemapSource").objects.filter(
        preset__in=DEFAULTS, district__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("basemaps", "0002_rls_audit")]

    operations = [migrations.RunPython(add, remove)]

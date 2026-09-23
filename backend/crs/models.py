"""Coordinate reference system registry and defaults.

Stored coordinates are never reprojected implicitly: every layer and project
records the CRS its coordinates are in. The defaults here only decide which CRS
a *new* project starts with.
"""

from typing import ClassVar

from django.conf import settings
from django.db import models

# PostGIS reserves this SRID range for user-defined systems.
CUSTOM_SRID_MIN = 910000
CUSTOM_SRID_MAX = 998999


class CoordinateSystem(models.Model):
    class Kind(models.TextChoices):
        PROJECTED = "projected", "Projected"
        GEOGRAPHIC = "geographic", "Geographic"

    code = models.CharField(max_length=64, unique=True, help_text="EPSG:2136 or CUSTOM:<id>")
    name = models.CharField(max_length=200)
    srid = models.IntegerField(unique=True, help_text="SRID in PostGIS spatial_ref_sys")
    wkt = models.TextField(help_text="Authoritative definition (WKT2)")
    proj4 = models.TextField(help_text="Approximation for web maps (proj4js)")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    units = models.CharField(max_length=40, help_text="Axis unit, e.g. 'metre', 'Gold Coast foot'")
    unit_to_metre = models.FloatField(
        null=True, help_text="Linear unit in metres; null for degrees"
    )
    area_of_use = models.CharField(max_length=200, blank=True)
    bounds = models.JSONField(null=True, help_text="[west, south, east, north] in degrees")
    notes = models.TextField(blank=True)
    is_builtin = models.BooleanField(default=False)
    # Null: available to every district. Set: a district's own custom system.
    district = models.ForeignKey(
        "core.District", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_builtin", "code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class SystemCrsSettings(models.Model):
    """Singleton (id=1): the platform-wide default CRS."""

    default_crs = models.ForeignKey(CoordinateSystem, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[models.Manager["SystemCrsSettings"]]

    def __str__(self) -> str:
        return f"System default: {self.default_crs.code}"


class DistrictCrsSettings(models.Model):
    """A district's default CRS, overriding the system default. Tenant-scoped."""

    district = models.OneToOneField("core.District", on_delete=models.CASCADE, related_name="+")
    default_crs = models.ForeignKey(CoordinateSystem, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.district_id}: {self.default_crs.code}"


class UserCrsPreference(models.Model):
    """A user's own default, overriding district and system defaults."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    preferred_crs = models.ForeignKey(CoordinateSystem, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.preferred_crs.code}"


class PreferredTransformation(models.Model):
    """Pins the coordinate operation used between two systems (e.g. which
    Accra -> WGS 84 datum shift). The reverse direction uses its inverse, so a
    round trip returns to the starting point."""

    source = models.ForeignKey(CoordinateSystem, on_delete=models.CASCADE, related_name="+")
    target = models.ForeignKey(CoordinateSystem, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=300)
    pipeline = models.TextField(help_text="PROJ pipeline, axis order x/y (lon/lat, east/north)")
    accuracy_m = models.FloatField(null=True, help_text="Stated accuracy in metres, if known")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "target"], name="unique_transformation_pair"),
        ]

    def __str__(self) -> str:
        return f"{self.source.code} -> {self.target.code}: {self.name}"

"""Raster data a district brings itself: drone orthophotos (shown as a
basemap, also offline in the field) and elevation models (for contours).

The uploaded file is converted to a cloud-optimised GeoTIFF in its own
coordinate system; it is never resampled into another one on disk. Tiles for
the map are warped on request."""

import uuid

from django.conf import settings
from django.db import models


class Imagery(models.Model):
    class Kind(models.TextChoices):
        ORTHO = "ortho", "Orthophoto (drone or satellite image)"
        DEM = "dem", "Elevation model"

    class Status(models.TextChoices):
        QUEUED = "queued", "Waiting to be processed"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="imagery"
    )
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=5, choices=Kind.choices, default=Kind.ORTHO)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    error = models.TextField(blank=True)
    original_name = models.CharField(max_length=255)
    capture_date = models.DateField(null=True, blank=True, help_text="When it was flown or taken")
    source = models.CharField(max_length=200, blank=True, help_text="Who captured it, and how")
    assigned_crs = models.CharField(
        max_length=64, blank=True, help_text="CRS given at upload, for files that carry none"
    )
    crs = models.CharField(max_length=200, blank=True, help_text="The file's CRS, as read")
    width = models.PositiveIntegerField(null=True)
    height = models.PositiveIntegerField(null=True)
    bands = models.PositiveSmallIntegerField(null=True)
    resolution_m = models.FloatField(null=True, help_text="Ground size of a pixel, metres")
    bounds = models.JSONField(null=True, help_text="[west, south, east, north] in degrees")
    value_range = models.JSONField(null=True, help_text="[min, max] of an elevation model")
    min_zoom = models.PositiveSmallIntegerField(default=0)
    max_zoom = models.PositiveSmallIntegerField(default=19)
    size_bytes = models.PositiveBigIntegerField(default=0)
    basemap = models.OneToOneField(
        "basemaps.BasemapSource", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "imagery"

    def __str__(self) -> str:
        return self.name

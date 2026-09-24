from django.conf import settings
from django.db import models


class BasemapSource(models.Model):
    """A background map (tiles from a web service). Global (district null) or a
    district's own. API keys are stored encrypted and never returned by the API."""

    class Kind(models.TextChoices):
        XYZ = "xyz", "XYZ tiles"
        WMS = "wms", "WMS"
        WMTS = "wmts", "WMTS"
        GOOGLE = "google", "Google Map Tiles API"
        BING = "bing", "Bing Maps"

    district = models.ForeignKey(
        "core.District", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    preset = models.CharField(max_length=40, blank=True)
    url = models.CharField(
        max_length=500,
        blank=True,
        help_text="XYZ: template with {z}/{x}/{y}; WMS: service URL; WMTS: capabilities URL",
    )
    layers = models.CharField(
        max_length=200, blank=True, help_text="WMS layer names, WMTS layer id, Google/Bing map type"
    )
    attribution = models.CharField(max_length=300, blank=True)
    min_zoom = models.PositiveSmallIntegerField(default=0)
    max_zoom = models.PositiveSmallIntegerField(default=19)
    requires_key = models.BooleanField(default=False)
    api_key_encrypted = models.TextField(blank=True)
    offline_cache_allowed = models.BooleanField(
        default=False,
        help_text="True only when the licence allows storing tiles for offline field use",
    )
    notes = models.TextField(blank=True, help_text="Terms of use and other notes")
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

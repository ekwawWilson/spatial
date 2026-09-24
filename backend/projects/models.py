"""Plan projects, their layers and features.

Coordinates of record live in feature.geom_native, an unconstrained PostGIS
column that is *not* a model field: it is created by migration 0002 and read and
written only through projects.geometry (explicit SQL), so nothing can reproject
it implicitly. feature.geom_4326 is a derived copy for display, tiles and
cross-layer queries, computed with the platform's own coordinate operation
(crs.services).
"""

import uuid
from typing import ClassVar

from django.conf import settings
from django.contrib.gis.db import models as gis
from django.db import models


class Domain(models.TextChoices):
    """The data domains of the platform's data architecture."""

    TERRITORY = "A", "A. Territory"
    LAND = "B", "B. Land & parcels"
    BUILDINGS = "C", "C. Buildings & properties"
    STREETS = "D", "D. Streets & addressing"
    INFRASTRUCTURE = "E", "E. Infrastructure & services"
    ENVIRONMENT = "F", "F. Environment & physical geography"
    DEVELOPMENT = "G", "G. Development activity"
    SOCIOECONOMIC = "H", "H. Socio-economic & demographic"
    PROJECTS = "I", "I. Projects & investment"
    PLANNING = "J", "J. Planning & policy"
    OTHER = "other", "Other"


class PlanProject(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    district = models.ForeignKey("core.District", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=200)
    community = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    # Fixed at creation: the project's working CRS. Defaults changing later
    # never alter it.
    crs = models.ForeignKey("crs.CoordinateSystem", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["district", "name"], name="unique_project_name"),
        ]

    def __str__(self) -> str:
        return self.name


class GeometryType(models.TextChoices):
    POINT = "point", "Point"
    LINE = "line", "Line"
    POLYGON = "polygon", "Polygon"


# Which GeoJSON types a layer of each geometry type accepts.
ACCEPTED_GEOJSON_TYPES: dict[str, frozenset[str]] = {
    GeometryType.POINT: frozenset({"Point", "MultiPoint"}),
    GeometryType.LINE: frozenset({"LineString", "MultiLineString"}),
    GeometryType.POLYGON: frozenset({"Polygon", "MultiPolygon"}),
}


class Layer(models.Model):
    class Source(models.TextChoices):
        DRAWN = "drawn", "Drawn"
        UPLOAD = "upload", "Uploaded"
        FIELD = "field", "Field capture"
        DERIVED = "derived", "Derived"

    district = models.ForeignKey("core.District", on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey(PlanProject, on_delete=models.CASCADE, related_name="layers")
    name = models.CharField(max_length=200)
    domain = models.CharField(max_length=5, choices=Domain.choices, default=Domain.OTHER)
    geometry_type = models.CharField(max_length=10, choices=GeometryType.choices)
    # Native CRS of the layer's coordinates. Can't change once it has features.
    crs = models.ForeignKey("crs.CoordinateSystem", on_delete=models.PROTECT, related_name="+")
    schema = models.JSONField(default=list, help_text="Field definitions: see projects.schema")
    style = models.JSONField(default=dict, help_text="Display style: see projects.styles")
    order = models.IntegerField(default=0, help_text="Draw order: higher is drawn on top")
    visible = models.BooleanField(default=True)
    opacity = models.FloatField(default=1.0)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.DRAWN)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_layer_name"),
            models.CheckConstraint(
                condition=models.Q(opacity__gte=0) & models.Q(opacity__lte=1),
                name="layer_opacity_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Feature(models.Model):
    class Origin(models.TextChoices):
        DRAWN = "drawn", "Drawn"
        IMPORT = "import", "Imported"
        FIELD = "field", "Field capture"
        DERIVED = "derived", "Derived"

    district = models.ForeignKey("core.District", on_delete=models.PROTECT, related_name="+")
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE, related_name="features")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # geom_native: see module docstring (not a model field on purpose).
    geom_4326 = gis.GeometryField(srid=4326, null=True, spatial_index=True)
    properties = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.DRAWN)
    verified = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[models.Manager["Feature"]]

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["layer", "id"], name="feature_layer_id_idx")]

    def __str__(self) -> str:
        return str(self.uuid)

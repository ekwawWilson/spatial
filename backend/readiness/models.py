"""The readiness checklist: what must be in place before a community plan can
be prepared (authority, planning area, base map, existing situation, people
and standards).

Templates (the platform default, or a district's own) are copied into each
project, so later template changes never rewrite a project's checklist.
"""

from django.conf import settings
from django.db import models


class Group(models.TextChoices):
    AUTHORITY = "authority", "1. Authority and set-up"
    PLANNING_AREA = "planning_area", "2. Planning area"
    BASE_MAP = "base_map", "3. Base map"
    EXISTING = "existing", "4. Existing situation"
    PEOPLE = "people", "5. People and standards"


class Kind(models.TextChoices):
    DOCUMENT = "document", "Document or decision"
    LAYER = "layer", "Map layer"
    BOUNDARY = "boundary", "Planning area boundary"


class Template(models.Model):
    """A checklist template. district=null is the platform default; a district
    may have its own, used for its new projects instead."""

    district = models.OneToOneField(
        "core.District", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(max_length=200)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(district__isnull=True),
                name="one_default_template",
            )
        ]

    def __str__(self) -> str:
        return self.name


class TemplateItem(models.Model):
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name="items")
    group = models.CharField(max_length=20, choices=Group.choices)
    key = models.SlugField(max_length=60)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    domain = models.CharField(max_length=5, blank=True, help_text="Data domain A-J (layer items)")
    geometry_type = models.CharField(
        max_length=10, blank=True, help_text="Expected geometry (layer items)"
    )
    # e.g. {"min_features": 1, "min_coverage": 90, "min_attributes": 80,
    #       "max_age_days": 365, "min_verified": 0, "no_overlaps": true}
    rules = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["group", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["template", "key"], name="unique_template_item")
        ]

    def __str__(self) -> str:
        return self.title


class Item(models.Model):
    """One checklist item of one project (a copy of a template item)."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        READY = "ready", "Ready"
        VERIFIED = "verified", "Verified"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="checklist_items"
    )
    group = models.CharField(max_length=20, choices=Group.choices)
    key = models.SlugField(max_length=60)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    domain = models.CharField(max_length=5, blank=True)
    geometry_type = models.CharField(max_length=10, blank=True)
    rules = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOT_STARTED)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    linked_layer = models.ForeignKey(
        "projects.Layer", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["group", "order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "key"], name="unique_project_item")
        ]

    def __str__(self) -> str:
        return self.title


class Attachment(models.Model):
    """A document for a checklist item (e.g. the Assembly resolution)."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=500)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.name

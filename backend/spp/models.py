"""A record of every .spp file saved from or opened on this server: who, when,
which project, which key. The file itself is not kept."""

import uuid

from django.conf import settings
from django.db import models


class FileRecord(models.Model):
    class Direction(models.TextChoices):
        SAVED = "saved", "Saved as .spp"
        OPENED = "opened", "Opened from .spp"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    project_name = models.CharField(max_length=200)
    direction = models.CharField(max_length=6, choices=Direction.choices)
    file_id = models.UUIDField(default=uuid.uuid4, help_text="Identifies the file (in its header)")
    key_id = models.CharField(max_length=40)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField()
    summary = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_direction_display()}: {self.project_name}"

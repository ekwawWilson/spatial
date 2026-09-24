"""Import and export jobs. Files live under MEDIA_ROOT/transfer/<job uuid>/."""

import uuid

from django.conf import settings
from django.db import models


class DataJob(models.Model):
    class Kind(models.TextChoices):
        IMPORT = "import", "Import"
        EXPORT = "export", "Export"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        INSPECTED = "inspected", "Inspected: waiting for your choices"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(max_length=6, choices=Kind.choices)
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="data_jobs"
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    file_format = models.CharField(max_length=10, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    # What the file contains (imports), as found by inspection.
    inspection = models.JSONField(default=dict, blank=True)
    # What to do: target layers, CRS, field mapping, geometry policy (imports);
    # layers, format and CRS (exports).
    plan = models.JSONField(default=dict, blank=True)
    progress = models.JSONField(default=dict, blank=True)
    report = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    result_name = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} {self.uuid}"

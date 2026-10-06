"""Sync between the field app and the server.

* AppliedChange makes pushes idempotent: each change a device sends has an id,
  and sending it again returns what happened the first time.
* Conflict holds a field edit that was based on an older version than the
  server's, for a person to resolve.
* Tombstone records deleted features (written by a database trigger), so
  devices can remove them on their next pull.
* Capture is how a field feature was recorded (who, method, accuracy).
* Photo is a field photo, uploaded in resumable chunks.
* FieldTask is a ground-truthing task: check one feature on the ground.
"""

import uuid

from django.conf import settings
from django.db import models


class AppliedChange(models.Model):
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    change_id = models.UUIDField(unique=True)
    device_id = models.CharField(max_length=64)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    result = models.JSONField()
    applied_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.change_id)


class Conflict(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    class Resolution(models.TextChoices):
        KEEP_FIELD = "keep_field", "Kept the field version"
        KEEP_OFFICE = "keep_office", "Kept the office version"
        MERGED = "merged", "Merged field by field"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="sync_conflicts"
    )
    feature = models.ForeignKey("projects.Feature", on_delete=models.CASCADE, related_name="+")
    change_id = models.UUIDField(unique=True)
    device_id = models.CharField(max_length=64)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    base_version = models.PositiveIntegerField(help_text="The version the device edited")
    server_version = models.PositiveIntegerField(help_text="The server's version at that time")
    field_properties = models.JSONField(null=True, help_text="Attributes sent by the device")
    field_geometry = models.JSONField(null=True, help_text="Geometry sent (WGS 84), if changed")
    capture = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    resolution = models.CharField(max_length=12, choices=Resolution.choices, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Conflict on feature {self.feature_id}"


class Tombstone(models.Model):
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    layer_id = models.BigIntegerField(db_index=True)
    feature_uuid = models.UUIDField()
    deleted_at = models.DateTimeField(db_index=True)

    def __str__(self) -> str:
        return str(self.feature_uuid)


class Capture(models.Model):
    class Method(models.TextChoices):
        GPS = "gps", "GPS point (averaged)"
        GPS_TRACK = "gps_track", "GPS walk"
        DRAWN = "drawn", "Drawn on the device's map"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    feature = models.ForeignKey(
        "projects.Feature", on_delete=models.CASCADE, related_name="captures"
    )
    feature_version = models.PositiveIntegerField()
    method = models.CharField(max_length=10, choices=Method.choices, blank=True)
    accuracy_m = models.FloatField(null=True)
    fix_time = models.DateTimeField(null=True)
    readings = models.PositiveIntegerField(null=True)
    captured_at = models.DateTimeField(null=True)
    captured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    device_id = models.CharField(max_length=64)
    notes = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-id"]

    def __str__(self) -> str:
        return f"Capture of feature {self.feature_id}"


class Photo(models.Model):
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    feature = models.ForeignKey("projects.Feature", on_delete=models.CASCADE, related_name="photos")
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)
    size = models.PositiveBigIntegerField(help_text="Size of the whole file in bytes")
    sha256 = models.CharField(max_length=64)
    received = models.PositiveBigIntegerField(default=0, help_text="Bytes received so far")
    complete = models.BooleanField(default=False)
    path = models.CharField(max_length=500, blank=True)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    accuracy_m = models.FloatField(null=True)
    taken_at = models.DateTimeField(null=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return str(self.uuid)


class FieldTask(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "To check"
        DONE = "done", "Checked"

    class Outcome(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed as recorded"
        CORRECTED = "corrected", "Corrected in the field"
        NOT_FOUND = "not_found", "Not found on the ground"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="field_tasks"
    )
    item = models.ForeignKey(
        "readiness.Item", null=True, on_delete=models.SET_NULL, related_name="field_tasks"
    )
    feature = models.ForeignKey(
        "projects.Feature", on_delete=models.CASCADE, related_name="field_tasks"
    )
    status = models.CharField(max_length=5, choices=Status.choices, default=Status.OPEN)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["feature"],
                condition=models.Q(status="open"),
                name="one_open_task_per_feature",
            )
        ]

    def __str__(self) -> str:
        return f"Check feature {self.feature_id}"

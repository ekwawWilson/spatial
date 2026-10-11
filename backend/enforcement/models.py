"""Enforcement (Act 925 s.160-167; L.I. 2384 r.30, r.55-59): a case for each
contravention, the notices served in it, and the runs that look for new
development by comparing two images."""

from django.conf import settings
from django.db import models


class Case(models.Model):
    class Origin(models.TextChoices):
        INSPECTION = "inspection", "Found on inspection"
        COMPLAINT = "complaint", "Reported by the public"
        DETECTION = "detection", "Found by comparing images"
        CHECK = "check", "Flagged by the standards check"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        NOTICE = "notice", "Notice served"
        RECTIFIED = "rectified", "Rectified by the owner"
        ENFORCED = "enforced", "Rectified by the Assembly"
        DROPPED = "dropped", "No contravention found"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="enforcement_cases"
    )
    number = models.CharField(max_length=40)
    origin = models.CharField(max_length=10, choices=Origin.choices)
    contravention = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    # What the case is about on the map: a building, a parcel, or a detected change.
    feature = models.ForeignKey(
        "projects.Feature", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    permit = models.ForeignKey(
        "permits.Application", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    owner_name = models.CharField(max_length=200, blank=True)
    owner_address = models.CharField(max_length=300, blank=True)
    owner_contact = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opened_on = models.DateField()
    closed_on = models.DateField(null=True, blank=True)
    outcome = models.TextField(blank=True)
    # r.57(4): the cost of rectification, recovered from the person responsible.
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_recovered = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["district", "number"], name="one_case_number")
        ]
        indexes = [models.Index(fields=["project", "status"], name="case_project_status_idx")]

    def __str__(self) -> str:
        return self.number


class Notice(models.Model):
    """A notice served in a case (registry.NOTICES)."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="notices")
    kind = models.CharField(max_length=14)
    # What has come to the Assembly's attention, and what must be done about it.
    grounds = models.TextField()
    required = models.TextField(blank=True)
    issued_on = models.DateField()
    comply_by = models.DateField(null=True, blank=True)
    # r.56: how and when it was served.
    served_on = models.DateField(null=True, blank=True)
    served_by = models.CharField(max_length=16, blank=True)
    served_note = models.CharField(max_length=300, blank=True)
    complied_on = models.DateField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.kind} in {self.case_id}"


class DetectionRun(models.Model):
    """One comparison of two images, and what it found."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="detection_runs"
    )
    before = models.ForeignKey(
        "imagery.Imagery", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    after = models.ForeignKey(
        "imagery.Imagery", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    # The layer the changed places were put in.
    layer = models.ForeignKey(
        "projects.Layer", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    found = models.PositiveIntegerField(default=0)
    # By kind: with a permit, at a building already on the map, new.
    summary = models.JSONField(default=dict, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"Run {self.pk} of project {self.project_id}"

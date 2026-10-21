"""Applications that change the land itself: re-zoning (L.I. 2384 r.33),
change of use (r.34), and the subdivision or consolidation of land (r.54).
What each kind requires is in registry.py; here is what was done and when."""

from django.conf import settings
from django.db import models


class Application(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Being considered"
        DEFERRED = "deferred", "Decision deferred"
        APPROVED = "approved", "Approved"
        REFUSED = "refused", "Refused"
        WITHDRAWN = "withdrawn", "Withdrawn"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="land_applications"
    )
    number = models.CharField(max_length=40)
    kind = models.CharField(max_length=14)
    applicant_name = models.CharField(max_length=200)
    applicant_phone = models.CharField(max_length=40, blank=True)
    applicant_email = models.EmailField(blank=True)
    applicant_address = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    # The parcels the application is about (ids of features on the map).
    parcels = models.JSONField(default=list, blank=True)
    # Re-zoning: from which zone to which, and why (r.33(2)-(3)).
    current_zone = models.CharField(max_length=80, blank=True)
    proposed_zone = models.CharField(max_length=80, blank=True)
    ground = models.CharField(max_length=16, blank=True)
    circumstance = models.CharField(max_length=20, blank=True)
    # Change of use: from which use to which, and the tests of r.34.
    current_use = models.CharField(max_length=120, blank=True)
    proposed_use = models.CharField(max_length=120, blank=True)
    assessment = models.JSONField(default=dict, blank=True)
    # Subdivision: into how many plots.
    lots = models.PositiveSmallIntegerField(null=True, blank=True)
    received_on = models.DateField()
    # The steps taken: {step code: {"on": date, "note": text}}.
    steps = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)
    deferred_on = models.DateField(null=True, blank=True)
    defer_reason = models.TextField(blank=True)
    decided_on = models.DateField(null=True, blank=True)
    conditions = models.TextField(blank=True)
    reasons = models.TextField(blank=True)
    # Re-zoning: when the new zone was written to the parcels on the map.
    applied_on = models.DateField(null=True, blank=True)
    # The officer handling it (Phase 23): their work list shows it.
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["district", "number"], name="one_land_app_number")
        ]
        indexes = [models.Index(fields=["project", "status"], name="land_app_project_status_idx")]

    def __str__(self) -> str:
        return self.number


class Comment(models.Model):
    """A comment, objection or representation on an application (Form 59),
    and what the applicant said in reply."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="comments")
    kind = models.CharField(max_length=16)
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=200, blank=True)
    text = models.TextField()
    received_on = models.DateField()
    response = models.TextField(blank=True)
    responded_on = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.kind} on {self.application_id}"

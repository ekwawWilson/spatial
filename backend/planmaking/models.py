"""Making a local plan (L.I. 2384 r.23-27): the steps taken for a project's
plan, what the plan covers, the consultations held (r.65) and the public's
comments on the draft (Form 59)."""

from django.conf import settings
from django.db import models


class PlanProcess(models.Model):
    class Origin(models.TextChoices):
        COMMITTEE = "committee", "Prepared by the District Spatial Planning Committee"
        APPLICANT = "applicant", "Prepared by another person, for approval"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.OneToOneField(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="plan_process"
    )
    origin = models.CharField(max_length=10, choices=Origin.choices, default=Origin.COMMITTEE)
    prepared_by = models.CharField(max_length=200, blank=True)
    # The structure plan for the area came into force (r.23(1): twelve months from then).
    structure_plan_on = models.DateField(null=True, blank=True)
    # A plan prepared by another person: when the application for approval came in (r.25(1)).
    application_on = models.DateField(null=True, blank=True)
    # The steps taken: {step code: {"on": date, "note": text}}.
    steps = models.JSONField(default=dict, blank=True)
    # What the plan specifies (r.24): {item: {"covered": bool, "note": text}}.
    content = models.JSONField(default=dict, blank=True)
    # r.27: the conditions imposed, and the plan's validity.
    conditions = models.TextField(blank=True)
    valid_until = models.DateField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Local plan of project {self.project_id}"


class Consultation(models.Model):
    """A public or key stakeholder consultation and its minutes (r.65, Form 56)."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="consultations"
    )
    stage = models.CharField(max_length=8)
    held_on = models.DateField()
    venue = models.CharField(max_length=200)
    # Who was consulted: chiefs, land owners, traders, utilities ...
    groups = models.TextField(blank=True)
    attendance = models.PositiveIntegerField(null=True, blank=True)
    issues = models.TextField()
    outcome = models.TextField(blank=True)
    # r.65(3): a copy of the minutes is displayed in the Public Data Room.
    displayed_on = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["held_on", "id"]

    def __str__(self) -> str:
        return f"Consultation of {self.held_on} for project {self.project_id}"


class PlanComment(models.Model):
    """A comment on the draft local plan (r.23(5)-(7), Form 59), and the reply."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="plan_comments"
    )
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=200, blank=True)
    # The item of r.24 it is about ("" if general): r.23(6).
    topic = models.CharField(max_length=2, blank=True)
    text = models.TextField()
    received_on = models.DateField()
    # Sent in through the Public Data Room online, not recorded by the office.
    online = models.BooleanField(default=False)
    response = models.TextField(blank=True)
    responded_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Comment {self.pk} on project {self.project_id}"

"""The Public Data Room (Act 925 s.47; L.I. 2384 r.64, r.67-68): what an
Assembly puts before the public, and the public's requests for information.

Nothing is public until the district opens its room and publishes a project.
What the public then sees is assembled from the records themselves (permits,
zoning schemes, standards), so the register can't fall out of date."""

from django.conf import settings
from django.db import models


class DataRoom(models.Model):
    """A district's Public Data Room: whether it is open online, and how."""

    district = models.OneToOneField("core.District", on_delete=models.CASCADE, related_name="+")
    is_open = models.BooleanField(default=False)
    # r.68(2)(b): names are personal data. Off, the register shows the permit
    # without the person it was issued to.
    show_applicants = models.BooleanField(default=False)
    welcome = models.TextField(blank=True)
    contact = models.TextField(blank=True, help_text="Office, hours, phone, email")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Data room of district {self.district_id}"


class Publication(models.Model):
    """A project whose permits and zoning are in the public register."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.OneToOneField(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="publication"
    )
    permits = models.BooleanField(default=True)
    zoning = models.BooleanField(default=True)
    published_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Project {self.project_id}"


class RoomDocument(models.Model):
    """A document on display: a plan, a notice, a record of consultation (r.64(2))."""

    class Kind(models.TextChoices):
        SDF = "sdf", "Spatial Development Framework"
        STRUCTURE_PLAN = "structure_plan", "Structure plan"
        LOCAL_PLAN = "local_plan", "Local plan"
        ZONING_SCHEME = "zoning_scheme", "Zoning scheme"
        NOTICE = "notice", "Notice"
        CONSULTATION = "consultation", "Record of public consultation"
        OUTSOURCED = "outsourced", "Scope of outsourced services"
        OTHER = "other", "Other document"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=500)
    size = models.PositiveBigIntegerField()
    # Shown from this day, and (for a notice or a draft plan) until this one.
    display_from = models.DateField()
    display_until = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-display_from", "-id"]

    def __str__(self) -> str:
        return self.title


class InformationRequest(models.Model):
    """A request for information from the Data Room (Form 55): answered within
    five days, and kept on record (r.64(6)-(8))."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ANSWERED = "answered", "Answered"
        DECLINED = "declined", "Declined"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    reference = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    received_on = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    answer = models.TextField(blank=True)
    answered_on = models.DateField(null=True, blank=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["district", "reference"], name="one_request_reference")
        ]

    def __str__(self) -> str:
        return self.reference

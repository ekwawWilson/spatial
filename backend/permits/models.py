"""Planning and development permits: an application from receipt to
certificate, with the documents, comments, inspection, decision and fees the
Regulations ask for (L.I. 2384 r.43-46). The site is a feature in the
project's permits layer, so it is on the map and in the relationship layer
like everything else."""

from django.conf import settings
from django.db import models


class Counter(models.Model):
    """The last application number given, per district, kind and year."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=12)
    year = models.PositiveSmallIntegerField()
    last = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["district", "kind", "year"], name="one_permit_counter")
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.year}: {self.last}"


class Fee(models.Model):
    """A line of the Assembly's fee-fixing resolution that permits use."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    # "processing" or "permit", for a kind of permit and (optionally) a category.
    stage = models.CharField(max_length=12)
    kind = models.CharField(max_length=12)
    category = models.CharField(max_length=20, blank=True)
    label = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stage", "kind", "category"]
        constraints = [
            models.UniqueConstraint(
                fields=["district", "stage", "kind", "category"], name="one_fee_per_line"
            )
        ]

    def __str__(self) -> str:
        return self.label


class Application(models.Model):
    class Kind(models.TextChoices):
        PLANNING = "planning", "Planning permit"
        DEVELOPMENT = "development", "Development permit"

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        REVIEW = "review", "With the Technical Sub-Committee"
        REPORTED = "reported", "With the Spatial Planning Committee"
        GRANTED = "granted", "Granted: permit fee due"
        DEFERRED = "deferred", "Deferred"
        REFUSED = "refused", "Refused"
        ISSUED = "issued", "Permit issued"
        WITHDRAWN = "withdrawn", "Withdrawn"

    class Recommendation(models.TextChoices):
        GRANT = "grant", "Grant"
        REFUSE = "refuse", "Refuse"
        DEFER = "defer", "Defer"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="permit_applications"
    )
    number = models.CharField(max_length=40)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    category = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED)

    applicant_name = models.CharField(max_length=200)
    applicant_phone = models.CharField(max_length=40, blank=True)
    applicant_email = models.EmailField(blank=True)
    applicant_address = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    proposed_use = models.CharField(max_length=200, blank=True)
    proposed_floors = models.PositiveSmallIntegerField(null=True, blank=True)
    # The site, in the project's permits layer.
    site = models.ForeignKey(
        "projects.Feature", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Documents the officer asked for beyond the required ones ("where applicable").
    extra_requirements = models.JSONField(default=list, blank=True)

    received_on = models.DateField()
    acknowledged_on = models.DateField(null=True, blank=True)
    inspected_on = models.DateField(null=True, blank=True)
    reported_on = models.DateField(null=True, blank=True)
    decided_on = models.DateField(null=True, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    # r.45(15)-(18): the Certificate of Habitation, once the finished development is inspected.
    habitation_on = models.DateField(null=True, blank=True)

    # The automatic checks, as last run: advice to the committees.
    checks = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    # The Technical Sub-Committee's report.
    recommendation = models.CharField(max_length=6, choices=Recommendation.choices, blank=True)
    report = models.TextField(blank=True)
    # The Spatial Planning Committee's decision.
    reasons = models.TextField(blank=True)
    conditions = models.TextField(blank=True)

    processing_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    processing_receipt = models.CharField(max_length=60, blank=True)
    processing_paid_on = models.DateField(null=True, blank=True)
    permit_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    permit_receipt = models.CharField(max_length=60, blank=True)
    permit_paid_on = models.DateField(null=True, blank=True)

    # In the certificate's QR code: anyone holding it can check the permit.
    token = models.CharField(max_length=64, blank=True)
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
            models.UniqueConstraint(fields=["district", "number"], name="one_permit_number"),
        ]
        indexes = [
            models.Index(fields=["project", "status"], name="permit_project_status_idx"),
            models.Index(fields=["token"], name="permit_token_idx"),
        ]

    def __str__(self) -> str:
        return self.number


class Document(models.Model):
    """A document submitted with an application."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    requirement = models.CharField(
        max_length=30, blank=True, help_text="Which requirement it meets"
    )
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=500)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class Comment(models.Model):
    """What a department or agency said about an application it was sent."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="comments")
    agency = models.CharField(max_length=120)
    body = models.TextField()
    objection = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.agency}: {self.body[:40]}"


class Inspection(models.Model):
    """A site inspection (r.44(7)(f)): what was found on each point."""

    class Purpose(models.TextChoices):
        APPLICATION = "application", "For the application"
        COMPLETION = "completion", "Of the completed development"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="inspections"
    )
    purpose = models.CharField(max_length=12, choices=Purpose.choices, default=Purpose.APPLICATION)
    inspected_on = models.DateField()
    # Point code -> what was found (registry.INSPECTION_POINTS).
    findings = models.JSONField(default=dict, blank=True)
    summary = models.TextField(blank=True)
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.application_id} on {self.inspected_on}"


class Event(models.Model):
    """The application's history in plain steps, for staff and the applicant."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20)
    note = models.TextField(blank=True)
    on = models.DateField()
    by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.kind} on {self.on}"


class Challenge(models.Model):
    """A request for review (r.62, Form 53) or an appeal (r.63, Form 54)
    against a decision on an application, and how it ended."""

    class Kind(models.TextChoices):
        REVIEW = "review", "Request for review"
        APPEAL = "appeal", "Appeal"

    class Outcome(models.TextChoices):
        UPHELD = "upheld", "Decision upheld"
        VARIED = "varied", "Decision varied"
        OVERTURNED = "overturned", "Decision overturned"
        WITHDRAWN = "withdrawn", "Withdrawn"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="challenges"
    )
    kind = models.CharField(max_length=6, choices=Kind.choices)
    # Who hears it: the Assembly (review), the Council or the Authority (appeal).
    body = models.CharField(max_length=8)
    lodged_on = models.DateField()
    grounds = models.TextField()
    decided_on = models.DateField(null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, blank=True)
    decision = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["lodged_on", "id"]

    def __str__(self) -> str:
        return f"{self.kind} of {self.application_id}"

"""The relationship layer: links between features, how each link was made and
how sure it is, the district's development-control standards, and the runs
that work the links out."""

from django.conf import settings
from django.db import models


class LayerRole(models.Model):
    """Which layer of a project plays a part (properties, streets, ...)."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="layer_roles"
    )
    role = models.CharField(max_length=20)
    layer = models.ForeignKey("projects.Layer", on_delete=models.CASCADE, related_name="roles")
    config = models.JSONField(default=dict, blank=True, help_text="Field names and distances")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "role"], name="one_layer_per_role")
        ]

    def __str__(self) -> str:
        return f"{self.role}: {self.layer_id}"


class DevelopmentStandard(models.Model):
    """Development-control standards for a zone. zone="" is the district's
    default, used where no standard names the zone."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    zone = models.CharField(max_length=100, blank=True)
    # From any boundary of the plot. The three below, where set, apply to the
    # side facing the street, the sides, and the back.
    min_setback_m = models.FloatField(null=True, blank=True)
    front_setback_m = models.FloatField(null=True, blank=True)
    side_setback_m = models.FloatField(null=True, blank=True)
    rear_setback_m = models.FloatField(null=True, blank=True)
    min_floors = models.PositiveSmallIntegerField(null=True, blank=True)
    max_floors = models.PositiveSmallIntegerField(null=True, blank=True)
    max_coverage_pct = models.FloatField(null=True, blank=True)
    min_plot_m2 = models.FloatField(null=True, blank=True)
    min_width_m = models.FloatField(null=True, blank=True, help_text="Along the street")
    prohibited_uses = models.JSONField(
        default=list, blank=True, help_text="Words that, in a property's use, suggest a breach"
    )
    # "luspa-2025" when adopted from the national standards and not changed since.
    source = models.CharField(max_length=20, blank=True)
    permit_required = models.BooleanField(default=False)
    build_in_flood_area = models.BooleanField(
        default=True, help_text="False: building in a flood-prone area breaks the standard"
    )
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["zone"]
        constraints = [
            models.UniqueConstraint(fields=["district", "zone"], name="one_standard_per_zone")
        ]

    def __str__(self) -> str:
        return self.zone or "Default"


class ZoningScheme(models.Model):
    """The register entry for a project's zoning scheme: when it was approved
    and took effect, when it was sent to LUSPA, and when it is next due for
    update (L.I. 2384 r.29)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        ADOPTED = "adopted", "Existing scheme adopted"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="zoning_schemes"
    )
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    structure_plan_approved_on = models.DateField(null=True, blank=True)
    approved_on = models.DateField(null=True, blank=True)
    effective_on = models.DateField(null=True, blank=True)
    sent_to_luspa_on = models.DateField(null=True, blank=True)
    update_every_months = models.PositiveSmallIntegerField(
        default=60, help_text="The scheme's schedule for periodic updates"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.name


class Relationship(models.Model):
    class Method(models.TextChoices):
        CALCULATED = "calculated", "Calculated from the geometry or attributes"
        INFERRED = "inferred", "Inferred: likely, not certain"
        CONFIRMED = "confirmed", "Confirmed by a person"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected by a person"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="relationships"
    )
    type = models.CharField(max_length=30)
    subject = models.ForeignKey(
        "projects.Feature", on_delete=models.CASCADE, related_name="links_from"
    )
    # Null for a link to a planning standard (violations).
    object = models.ForeignKey(
        "projects.Feature", null=True, on_delete=models.CASCADE, related_name="links_to"
    )
    # For violations: which rule ("setback", "floors", ...). Empty otherwise.
    rule = models.CharField(max_length=30, blank=True)
    method = models.CharField(max_length=10, choices=Method.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    confidence = models.FloatField(default=1.0)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    checked_at = models.DateTimeField(help_text="When a procedure last found or kept this link")
    # Set when a person confirms or rejects: procedures never change such links.
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["project", "type", "status"], name="rel_project_type_idx"),
            models.Index(fields=["subject", "type"], name="rel_subject_idx"),
            models.Index(fields=["object"], name="rel_object_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.subject_id} {self.type} {self.object_id or self.rule}"


class Run(models.Model):
    class Trigger(models.TextChoices):
        MANUAL = "manual", "Started by a person"
        NIGHTLY = "nightly", "Nightly"
        EDIT = "edit", "After an edit"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="relation_runs"
    )
    trigger = models.CharField(max_length=8, choices=Trigger.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # Per procedure: links found, kept from people, skipped (and why).
    report = models.JSONField(default=dict, blank=True)
    # Totals per community, and for the whole project (the plan's baseline).
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"Run {self.pk} of project {self.project_id}"


class StreetName(models.Model):
    """A name proposed for a street, and its way to the street signs:
    community consultation, the Spatial Planning Committee's approval,
    publication, signs put up (L.I. 2384 r.28: the national street naming
    manual)."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        CONSULTED = "consulted", "Consulted on"
        APPROVED = "approved", "Approved"
        REFUSED = "refused", "Refused"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="street_names"
    )
    street = models.ForeignKey(
        "projects.Feature", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    name = models.CharField(max_length=120)
    # Why this name: a person, a historical event, a landmark, a local name.
    basis = models.TextField(blank=True)
    proposed_by = models.CharField(max_length=200, blank=True)
    proposed_on = models.DateField()
    consulted_on = models.DateField(null=True, blank=True)
    consultation = models.TextField(blank=True)
    decided_on = models.DateField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    published_on = models.DateField(null=True, blank=True)
    signs_on = models.DateField(null=True, blank=True)
    # The street's name before this one was applied.
    previous_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-proposed_on", "-id"]

    def __str__(self) -> str:
        return self.name

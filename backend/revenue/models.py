"""The property register, its bills and payments, and betterment charges.

Only the Assembly may levy rates in the district (Local Governance Act, 2016,
Act 936). Betterment: L.I. 2384 r.40-42. Owners' names and contacts are
personal data, shown only to roles that may see it (data.sensitive)."""

from django.conf import settings
from django.db import models


class Use(models.TextChoices):
    RESIDENTIAL = "residential", "Residential"
    COMMERCIAL = "commercial", "Commercial"
    INDUSTRIAL = "industrial", "Industrial"
    MIXED = "mixed", "Mixed use"
    INSTITUTIONAL = "institutional", "Institutional"
    VACANT = "vacant", "Vacant land"
    OTHER = "other", "Other"


class Property(models.Model):
    """A rateable property, tied to its building or plot on the map."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="properties"
    )
    feature = models.ForeignKey(
        "projects.Feature", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # The property's reference: its address number where it has one, else its map id.
    number = models.CharField(max_length=60)
    address = models.CharField(max_length=200, blank=True)
    use = models.CharField(max_length=14, choices=Use.choices, default=Use.RESIDENTIAL)
    owner_name = models.CharField(max_length=200, blank=True)
    owner_contact = models.CharField(max_length=200, blank=True)
    # From the Land Valuation Division's valuation list.
    valuation_ref = models.CharField(max_length=60, blank=True)
    rateable_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    valued_on = models.DateField(null=True, blank=True)
    # The revenue system's own account number for it, once known.
    revenue_ref = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "number"], name="one_property_number"),
        ]

    def __str__(self) -> str:
        return self.number


class RateBand(models.Model):
    """The rate for one use in one year: a share of the rateable value (the
    impost, from the Assembly's fee-fixing resolution), with a minimum, and a
    flat rate for properties not yet valued."""

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    year = models.PositiveSmallIntegerField()
    use = models.CharField(max_length=14, choices=Use.choices)
    impost = models.DecimalField(max_digits=8, decimal_places=6)
    minimum = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    flat = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-year", "use"]
        constraints = [
            models.UniqueConstraint(fields=["district", "year", "use"], name="one_rate_band"),
        ]

    def __str__(self) -> str:
        return f"{self.use} {self.year}"


class Bill(models.Model):
    class Source(models.TextChoices):
        PLATFORM = "platform", "Worked out here"
        REVENUE = "revenue", "From the revenue system"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="bills")
    year = models.PositiveSmallIntegerField()
    reference = models.CharField(max_length=60, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    issued_on = models.DateField()
    last_paid_on = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.PLATFORM)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "id"]
        constraints = [
            models.UniqueConstraint(fields=["property", "year"], name="one_bill_a_year"),
        ]

    def __str__(self) -> str:
        return f"{self.property_id} {self.year}"


class BettermentScheme(models.Model):
    """A public improvement (a road, a drain) and the charge on the properties it bettered."""

    class Basis(models.TextChoices):
        SUM = "sum", "A fixed sum on each property"
        RATE = "rate", "A share of each property's increase in value"

    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey(
        "projects.PlanProject", on_delete=models.CASCADE, related_name="betterment_schemes"
    )
    name = models.CharField(max_length=200)
    works = models.TextField(blank=True)
    # The works on the map, and how far from them a property counts as bettered.
    works_feature = models.ForeignKey(
        "projects.Feature", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reach_m = models.DecimalField(max_digits=8, decimal_places=1, default=100)
    completed_on = models.DateField()
    basis = models.CharField(max_length=4, choices=Basis.choices, default=Basis.SUM)
    # A sum in GHS (basis "sum"), or a share of the increase, e.g. 0.25 (basis "rate").
    amount = models.DecimalField(max_digits=12, decimal_places=4)
    # r.40(3): how the Form 40 notice was published: {"newspaper": date, ...}.
    published = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-completed_on", "-id"]

    def __str__(self) -> str:
        return self.name


class BettermentCharge(models.Model):
    district = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="+")
    scheme = models.ForeignKey(BettermentScheme, on_delete=models.CASCADE, related_name="charges")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="betterment")
    distance_m = models.DecimalField(max_digits=10, decimal_places=1)
    # For basis "rate": the increase in value the charge is a share of.
    increase = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # r.40(7): the Form 41 assessment notice served on the owner.
    served_on = models.DateField(null=True, blank=True)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["distance_m", "id"]
        constraints = [
            models.UniqueConstraint(fields=["scheme", "property"], name="one_charge_a_scheme"),
        ]

    def __str__(self) -> str:
        return f"{self.scheme_id} {self.property_id}"

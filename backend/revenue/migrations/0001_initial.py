# Hand-written (depends on the GeoDjango projects app, which can't be loaded
# without GDAL on the dev machine); test_no_model_changes_without_migrations
# checks it matches models.py.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.tenancy import audit_trigger_sql, tenant_rls_sql

CASCADE = django.db.models.deletion.CASCADE
SET_NULL = django.db.models.deletion.SET_NULL

USES = [
    ("residential", "Residential"),
    ("commercial", "Commercial"),
    ("industrial", "Industrial"),
    ("mixed", "Mixed use"),
    ("institutional", "Institutional"),
    ("vacant", "Vacant land"),
    ("other", "Other"),
]


def pk():
    return ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"))


def district():
    return ("district", models.ForeignKey(on_delete=CASCADE, related_name="+", to="core.district"))


def money(name, **extra):
    return (name, models.DecimalField(decimal_places=2, max_digits=12, **extra))


def day(name):
    return (name, models.DateField(blank=True, null=True))


TABLES = (
    "revenue_property",
    "revenue_rateband",
    "revenue_bill",
    "revenue_bettermentscheme",
    "revenue_bettermentcharge",
)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Property",
            fields=[
                pk(),
                ("number", models.CharField(max_length=60)),
                ("address", models.CharField(blank=True, max_length=200)),
                ("use", models.CharField(choices=USES, default="residential", max_length=14)),
                ("owner_name", models.CharField(blank=True, max_length=200)),
                ("owner_contact", models.CharField(blank=True, max_length=200)),
                ("valuation_ref", models.CharField(blank=True, max_length=60)),
                ("rateable_value", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                day("valued_on"),
                ("revenue_ref", models.CharField(blank=True, max_length=60)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                district(),
                ("feature", models.ForeignKey(blank=True, null=True, on_delete=SET_NULL, related_name="+", to="projects.feature")),
                ("project", models.ForeignKey(on_delete=CASCADE, related_name="properties", to="projects.planproject")),
            ],
            options={
                "ordering": ["number", "id"],
                "constraints": [models.UniqueConstraint(fields=("project", "number"), name="one_property_number")],
            },
        ),
        migrations.CreateModel(
            name="RateBand",
            fields=[
                pk(),
                ("year", models.PositiveSmallIntegerField()),
                ("use", models.CharField(choices=USES, max_length=14)),
                ("impost", models.DecimalField(decimal_places=6, max_digits=8)),
                money("minimum", default=0),
                money("flat", blank=True, null=True),
                district(),
            ],
            options={
                "ordering": ["-year", "use"],
                "constraints": [models.UniqueConstraint(fields=("district", "year", "use"), name="one_rate_band")],
            },
        ),
        migrations.CreateModel(
            name="Bill",
            fields=[
                pk(),
                ("year", models.PositiveSmallIntegerField()),
                ("reference", models.CharField(blank=True, max_length=60)),
                money("amount"),
                money("paid", default=0),
                ("issued_on", models.DateField()),
                day("last_paid_on"),
                (
                    "source",
                    models.CharField(
                        choices=[("platform", "Worked out here"), ("revenue", "From the revenue system")],
                        default="platform",
                        max_length=8,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                district(),
                ("property", models.ForeignKey(on_delete=CASCADE, related_name="bills", to="revenue.property")),
            ],
            options={
                "ordering": ["-year", "id"],
                "constraints": [models.UniqueConstraint(fields=("property", "year"), name="one_bill_a_year")],
            },
        ),
        migrations.CreateModel(
            name="BettermentScheme",
            fields=[
                pk(),
                ("name", models.CharField(max_length=200)),
                ("works", models.TextField(blank=True)),
                ("reach_m", models.DecimalField(decimal_places=1, default=100, max_digits=8)),
                ("completed_on", models.DateField()),
                (
                    "basis",
                    models.CharField(
                        choices=[
                            ("sum", "A fixed sum on each property"),
                            ("rate", "A share of each property's increase in value"),
                        ],
                        default="sum",
                        max_length=4,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=4, max_digits=12)),
                ("published", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                district(),
                ("project", models.ForeignKey(on_delete=CASCADE, related_name="betterment_schemes", to="projects.planproject")),
                ("works_feature", models.ForeignKey(blank=True, null=True, on_delete=SET_NULL, related_name="+", to="projects.feature")),
            ],
            options={"ordering": ["-completed_on", "-id"]},
        ),
        migrations.CreateModel(
            name="BettermentCharge",
            fields=[
                pk(),
                ("distance_m", models.DecimalField(decimal_places=1, max_digits=10)),
                ("increase", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                money("amount", blank=True, null=True),
                day("served_on"),
                money("paid", default=0),
                day("paid_on"),
                district(),
                ("property", models.ForeignKey(on_delete=CASCADE, related_name="betterment", to="revenue.property")),
                ("scheme", models.ForeignKey(on_delete=CASCADE, related_name="charges", to="revenue.bettermentscheme")),
            ],
            options={
                "ordering": ["distance_m", "id"],
                "constraints": [models.UniqueConstraint(fields=("scheme", "property"), name="one_charge_a_scheme")],
            },
        ),
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(table)) for table in TABLES],
    ]

# Hand-written (depends on the GeoDjango projects app, which can't be loaded
# without GDAL on the dev machine); test_no_model_changes_without_migrations
# checks it matches models.py.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

CASCADE = django.db.models.deletion.CASCADE
SET_NULL = django.db.models.deletion.SET_NULL


def pk():
    return ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"))


def district():
    return ("district", models.ForeignKey(on_delete=CASCADE, related_name="+", to="core.district"))


def user(name: str):
    return (name, models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL))


def application(related_name: str):
    return ("application", models.ForeignKey(on_delete=CASCADE, related_name=related_name, to="permits.application"))


def money(name: str):
    return (name, models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True))


def day(name: str):
    return (name, models.DateField(blank=True, null=True))


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Counter",
            fields=[
                pk(),
                ("kind", models.CharField(max_length=12)),
                ("year", models.PositiveSmallIntegerField()),
                ("last", models.PositiveIntegerField(default=0)),
                district(),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("district", "kind", "year"), name="one_permit_counter")
                ],
            },
        ),
        migrations.CreateModel(
            name="Fee",
            fields=[
                pk(),
                ("stage", models.CharField(max_length=12)),
                ("kind", models.CharField(max_length=12)),
                ("category", models.CharField(blank=True, max_length=20)),
                ("label", models.CharField(max_length=200)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                district(),
            ],
            options={
                "ordering": ["stage", "kind", "category"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("district", "stage", "kind", "category"), name="one_fee_per_line"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Application",
            fields=[
                pk(),
                ("number", models.CharField(max_length=40)),
                (
                    "kind",
                    models.CharField(
                        choices=[("planning", "Planning permit"), ("development", "Development permit")],
                        max_length=12,
                    ),
                ),
                ("category", models.CharField(max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Received"),
                            ("review", "With the Technical Sub-Committee"),
                            ("reported", "With the Spatial Planning Committee"),
                            ("granted", "Granted: permit fee due"),
                            ("deferred", "Deferred"),
                            ("refused", "Refused"),
                            ("issued", "Permit issued"),
                            ("withdrawn", "Withdrawn"),
                        ],
                        default="received",
                        max_length=10,
                    ),
                ),
                ("applicant_name", models.CharField(max_length=200)),
                ("applicant_phone", models.CharField(blank=True, max_length=40)),
                ("applicant_email", models.EmailField(blank=True, max_length=254)),
                ("applicant_address", models.CharField(blank=True, max_length=300)),
                ("description", models.TextField(blank=True)),
                ("proposed_use", models.CharField(blank=True, max_length=200)),
                ("proposed_floors", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("extra_requirements", models.JSONField(blank=True, default=list)),
                ("received_on", models.DateField()),
                day("acknowledged_on"),
                day("inspected_on"),
                day("reported_on"),
                day("decided_on"),
                day("issued_on"),
                day("expires_on"),
                ("checks", models.JSONField(blank=True, default=dict)),
                ("checked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "recommendation",
                    models.CharField(
                        blank=True,
                        choices=[("grant", "Grant"), ("refuse", "Refuse"), ("defer", "Defer")],
                        max_length=6,
                    ),
                ),
                ("report", models.TextField(blank=True)),
                ("reasons", models.TextField(blank=True)),
                ("conditions", models.TextField(blank=True)),
                money("processing_fee"),
                ("processing_receipt", models.CharField(blank=True, max_length=60)),
                day("processing_paid_on"),
                money("permit_fee"),
                ("permit_receipt", models.CharField(blank=True, max_length=60)),
                day("permit_paid_on"),
                ("token", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                user("created_by"),
                district(),
                (
                    "project",
                    models.ForeignKey(on_delete=CASCADE, related_name="permit_applications", to="projects.planproject"),
                ),
                (
                    "site",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=SET_NULL, related_name="+", to="projects.feature"
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
                "indexes": [
                    models.Index(fields=["project", "status"], name="permit_project_status_idx"),
                    models.Index(fields=["token"], name="permit_token_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("district", "number"), name="one_permit_number")
                ],
            },
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                pk(),
                ("requirement", models.CharField(blank=True, help_text="Which requirement it meets", max_length=30)),
                ("name", models.CharField(max_length=255)),
                ("path", models.CharField(max_length=500)),
                ("size", models.PositiveBigIntegerField()),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                application("documents"),
                district(),
                user("uploaded_by"),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                pk(),
                ("agency", models.CharField(max_length=120)),
                ("body", models.TextField()),
                ("objection", models.BooleanField(default=False)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                application("comments"),
                district(),
                user("recorded_by"),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="Inspection",
            fields=[
                pk(),
                (
                    "purpose",
                    models.CharField(
                        choices=[
                            ("application", "For the application"),
                            ("completion", "Of the completed development"),
                        ],
                        default="application",
                        max_length=12,
                    ),
                ),
                ("inspected_on", models.DateField()),
                ("findings", models.JSONField(blank=True, default=dict)),
                ("summary", models.TextField(blank=True)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                application("inspections"),
                district(),
                user("inspected_by"),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="Event",
            fields=[
                pk(),
                ("kind", models.CharField(max_length=20)),
                ("note", models.TextField(blank=True)),
                ("on", models.DateField()),
                ("at", models.DateTimeField(auto_now_add=True)),
                application("events"),
                user("by"),
                district(),
            ],
            options={"ordering": ["id"]},
        ),
    ]

# Hand-written (depends on the GeoDjango projects app, which can't be loaded
# without GDAL on the dev machine); test_no_model_changes_without_migrations
# checks it matches models.py.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.tenancy import audit_trigger_sql, tenant_rls_sql

CASCADE = django.db.models.deletion.CASCADE
SET_NULL = django.db.models.deletion.SET_NULL


def pk():
    return ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"))


def district():
    return ("district", models.ForeignKey(on_delete=CASCADE, related_name="+", to="core.district"))


def user(name: str):
    return (name, models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL))


def day(name: str):
    return (name, models.DateField(blank=True, null=True))


TABLES = ("landchange_application", "landchange_comment")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Application",
            fields=[
                pk(),
                ("number", models.CharField(max_length=40)),
                ("kind", models.CharField(max_length=14)),
                ("applicant_name", models.CharField(max_length=200)),
                ("applicant_phone", models.CharField(blank=True, max_length=40)),
                ("applicant_email", models.EmailField(blank=True, max_length=254)),
                ("applicant_address", models.CharField(blank=True, max_length=300)),
                ("description", models.TextField(blank=True)),
                ("parcels", models.JSONField(blank=True, default=list)),
                ("current_zone", models.CharField(blank=True, max_length=80)),
                ("proposed_zone", models.CharField(blank=True, max_length=80)),
                ("ground", models.CharField(blank=True, max_length=16)),
                ("circumstance", models.CharField(blank=True, max_length=20)),
                ("current_use", models.CharField(blank=True, max_length=120)),
                ("proposed_use", models.CharField(blank=True, max_length=120)),
                ("assessment", models.JSONField(blank=True, default=dict)),
                ("lots", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("received_on", models.DateField()),
                ("steps", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Being considered"),
                            ("deferred", "Decision deferred"),
                            ("approved", "Approved"),
                            ("refused", "Refused"),
                            ("withdrawn", "Withdrawn"),
                        ],
                        default="received",
                        max_length=10,
                    ),
                ),
                day("deferred_on"),
                ("defer_reason", models.TextField(blank=True)),
                day("decided_on"),
                ("conditions", models.TextField(blank=True)),
                ("reasons", models.TextField(blank=True)),
                day("applied_on"),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                user("created_by"),
                district(),
                (
                    "project",
                    models.ForeignKey(on_delete=CASCADE, related_name="land_applications", to="projects.planproject"),
                ),
            ],
            options={
                "ordering": ["-id"],
                "indexes": [models.Index(fields=["project", "status"], name="land_app_project_status_idx")],
                "constraints": [models.UniqueConstraint(fields=("district", "number"), name="one_land_app_number")],
            },
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                pk(),
                ("kind", models.CharField(max_length=16)),
                ("name", models.CharField(max_length=200)),
                ("contact", models.CharField(blank=True, max_length=200)),
                ("text", models.TextField()),
                ("received_on", models.DateField()),
                ("response", models.TextField(blank=True)),
                day("responded_on"),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.ForeignKey(on_delete=CASCADE, related_name="comments", to="landchange.application")),
                district(),
                user("recorded_by"),
            ],
            options={"ordering": ["id"]},
        ),
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(table)) for table in TABLES],
    ]

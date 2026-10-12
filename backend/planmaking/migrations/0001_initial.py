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


TABLES = ("planmaking_planprocess", "planmaking_consultation", "planmaking_plancomment")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanProcess",
            fields=[
                pk(),
                (
                    "origin",
                    models.CharField(
                        choices=[
                            ("committee", "Prepared by the District Spatial Planning Committee"),
                            ("applicant", "Prepared by another person, for approval"),
                        ],
                        default="committee",
                        max_length=10,
                    ),
                ),
                ("prepared_by", models.CharField(blank=True, max_length=200)),
                day("structure_plan_on"),
                day("application_on"),
                ("steps", models.JSONField(blank=True, default=dict)),
                ("content", models.JSONField(blank=True, default=dict)),
                ("conditions", models.TextField(blank=True)),
                day("valid_until"),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                district(),
                (
                    "project",
                    models.OneToOneField(on_delete=CASCADE, related_name="plan_process", to="projects.planproject"),
                ),
                user("updated_by"),
            ],
        ),
        migrations.CreateModel(
            name="Consultation",
            fields=[
                pk(),
                ("stage", models.CharField(max_length=8)),
                ("held_on", models.DateField()),
                ("venue", models.CharField(max_length=200)),
                ("groups", models.TextField(blank=True)),
                ("attendance", models.PositiveIntegerField(blank=True, null=True)),
                ("issues", models.TextField()),
                ("outcome", models.TextField(blank=True)),
                day("displayed_on"),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                district(),
                (
                    "project",
                    models.ForeignKey(on_delete=CASCADE, related_name="consultations", to="projects.planproject"),
                ),
                user("recorded_by"),
            ],
            options={"ordering": ["held_on", "id"]},
        ),
        migrations.CreateModel(
            name="PlanComment",
            fields=[
                pk(),
                ("name", models.CharField(max_length=200)),
                ("contact", models.CharField(blank=True, max_length=200)),
                ("topic", models.CharField(blank=True, max_length=2)),
                ("text", models.TextField()),
                ("received_on", models.DateField()),
                ("online", models.BooleanField(default=False)),
                ("response", models.TextField(blank=True)),
                day("responded_on"),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                district(),
                (
                    "project",
                    models.ForeignKey(on_delete=CASCADE, related_name="plan_comments", to="projects.planproject"),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(table)) for table in TABLES],
    ]

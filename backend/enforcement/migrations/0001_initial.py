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


def money(name: str):
    return (name, models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True))


def optional(name: str, to: str):
    return (name, models.ForeignKey(blank=True, null=True, on_delete=SET_NULL, related_name="+", to=to))


def gone(name: str, to: str):
    return (name, models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=to))


TABLES = ("enforcement_case", "enforcement_notice", "enforcement_detectionrun")
AUDITED = ("enforcement_case", "enforcement_notice")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        ("imagery", "0002_rls_audit_checklist_rule"),
        ("permits", "0002_rls_audit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Case",
            fields=[
                pk(),
                ("number", models.CharField(max_length=40)),
                (
                    "origin",
                    models.CharField(
                        choices=[
                            ("inspection", "Found on inspection"),
                            ("complaint", "Reported by the public"),
                            ("detection", "Found by comparing images"),
                            ("check", "Flagged by the standards check"),
                        ],
                        max_length=10,
                    ),
                ),
                ("contravention", models.CharField(max_length=20)),
                ("description", models.TextField(blank=True)),
                ("owner_name", models.CharField(blank=True, max_length=200)),
                ("owner_address", models.CharField(blank=True, max_length=300)),
                ("owner_contact", models.CharField(blank=True, max_length=120)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("notice", "Notice served"),
                            ("rectified", "Rectified by the owner"),
                            ("enforced", "Rectified by the Assembly"),
                            ("dropped", "No contravention found"),
                        ],
                        default="open",
                        max_length=10,
                    ),
                ),
                ("opened_on", models.DateField()),
                day("closed_on"),
                ("outcome", models.TextField(blank=True)),
                money("cost"),
                money("cost_recovered"),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                district(),
                optional("feature", "projects.feature"),
                user("opened_by"),
                optional("permit", "permits.application"),
                (
                    "project",
                    models.ForeignKey(on_delete=CASCADE, related_name="enforcement_cases", to="projects.planproject"),
                ),
            ],
            options={
                "ordering": ["-id"],
                "indexes": [models.Index(fields=["project", "status"], name="case_project_status_idx")],
                "constraints": [models.UniqueConstraint(fields=("district", "number"), name="one_case_number")],
            },
        ),
        migrations.CreateModel(
            name="Notice",
            fields=[
                pk(),
                ("kind", models.CharField(max_length=14)),
                ("grounds", models.TextField()),
                ("required", models.TextField(blank=True)),
                ("issued_on", models.DateField()),
                day("comply_by"),
                day("served_on"),
                ("served_by", models.CharField(blank=True, max_length=16)),
                ("served_note", models.CharField(blank=True, max_length=300)),
                day("complied_on"),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("case", models.ForeignKey(on_delete=CASCADE, related_name="notices", to="enforcement.case")),
                district(),
                user("issued_by"),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="DetectionRun",
            fields=[
                pk(),
                ("found", models.PositiveIntegerField(default=0)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("at", models.DateTimeField(auto_now_add=True)),
                gone("after", "imagery.imagery"),
                gone("before", "imagery.imagery"),
                district(),
                gone("layer", "projects.layer"),
                (
                    "project",
                    models.ForeignKey(on_delete=CASCADE, related_name="detection_runs", to="projects.planproject"),
                ),
                user("started_by"),
            ],
            options={"ordering": ["-id"]},
        ),
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(table)) for table in AUDITED],
    ]

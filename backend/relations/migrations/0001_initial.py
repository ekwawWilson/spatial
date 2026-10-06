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


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LayerRole",
            fields=[
                pk(),
                ("role", models.CharField(max_length=20)),
                ("config", models.JSONField(blank=True, default=dict, help_text="Field names and distances")),
                district(),
                ("layer", models.ForeignKey(on_delete=CASCADE, related_name="roles", to="projects.layer")),
                ("project", models.ForeignKey(on_delete=CASCADE, related_name="layer_roles", to="projects.planproject")),
            ],
            options={
                "ordering": ["id"],
                "constraints": [models.UniqueConstraint(fields=("project", "role"), name="one_layer_per_role")],
            },
        ),
        migrations.CreateModel(
            name="DevelopmentStandard",
            fields=[
                pk(),
                ("zone", models.CharField(blank=True, max_length=100)),
                ("min_setback_m", models.FloatField(blank=True, null=True)),
                ("max_floors", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("max_coverage_pct", models.FloatField(blank=True, null=True)),
                ("min_plot_m2", models.FloatField(blank=True, null=True)),
                ("permit_required", models.BooleanField(default=False)),
                (
                    "build_in_flood_area",
                    models.BooleanField(
                        default=True, help_text="False: building in a flood-prone area breaks the standard"
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                district(),
            ],
            options={
                "ordering": ["zone"],
                "constraints": [models.UniqueConstraint(fields=("district", "zone"), name="one_standard_per_zone")],
            },
        ),
        migrations.CreateModel(
            name="Relationship",
            fields=[
                pk(),
                ("type", models.CharField(max_length=30)),
                ("rule", models.CharField(blank=True, max_length=30)),
                (
                    "method",
                    models.CharField(
                        choices=[
                            ("calculated", "Calculated from the geometry or attributes"),
                            ("inferred", "Inferred: likely, not certain"),
                            ("confirmed", "Confirmed by a person"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("rejected", "Rejected by a person")],
                        default="active",
                        max_length=8,
                    ),
                ),
                ("confidence", models.FloatField(default=1.0)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("checked_at", models.DateTimeField(help_text="When a procedure last found or kept this link")),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                (
                    "decided_by",
                    models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                district(),
                (
                    "object",
                    models.ForeignKey(null=True, on_delete=CASCADE, related_name="links_to", to="projects.feature"),
                ),
                ("project", models.ForeignKey(on_delete=CASCADE, related_name="relationships", to="projects.planproject")),
                ("subject", models.ForeignKey(on_delete=CASCADE, related_name="links_from", to="projects.feature")),
            ],
            options={
                "ordering": ["id"],
                "indexes": [
                    models.Index(fields=["project", "type", "status"], name="rel_project_type_idx"),
                    models.Index(fields=["subject", "type"], name="rel_subject_idx"),
                    models.Index(fields=["object"], name="rel_object_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Run",
            fields=[
                pk(),
                (
                    "trigger",
                    models.CharField(
                        choices=[("manual", "Started by a person"), ("nightly", "Nightly"), ("edit", "After an edit")],
                        max_length=8,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("running", "Running"), ("done", "Done"), ("failed", "Failed")],
                        default="running",
                        max_length=8,
                    ),
                ),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("report", models.JSONField(blank=True, default=dict)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
                district(),
                ("project", models.ForeignKey(on_delete=CASCADE, related_name="relation_runs", to="projects.planproject")),
                (
                    "started_by",
                    models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"ordering": ["-id"]},
        ),
    ]

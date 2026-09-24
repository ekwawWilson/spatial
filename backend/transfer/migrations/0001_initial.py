# Hand-written (depends on the GeoDjango projects app, which can't be loaded
# without GDAL on the dev machine); test_no_model_changes_without_migrations
# checks it matches models.py.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0002_native_geometry_rls_audit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DataJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("kind", models.CharField(choices=[("import", "Import"), ("export", "Export")], max_length=6)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("uploaded", "Uploaded"),
                            ("inspected", "Inspected: waiting for your choices"),
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("done", "Done"),
                            ("failed", "Failed"),
                        ],
                        max_length=10,
                    ),
                ),
                ("file_format", models.CharField(blank=True, max_length=10)),
                ("original_name", models.CharField(blank=True, max_length=255)),
                ("inspection", models.JSONField(blank=True, default=dict)),
                ("plan", models.JSONField(blank=True, default=dict)),
                ("progress", models.JSONField(blank=True, default=dict)),
                ("report", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
                ("result_name", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "district",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district"
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="data_jobs",
                        to="projects.planproject",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]

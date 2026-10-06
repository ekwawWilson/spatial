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
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FileRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("project_name", models.CharField(max_length=200)),
                (
                    "direction",
                    models.CharField(
                        choices=[("saved", "Saved as .spp"), ("opened", "Opened from .spp")], max_length=6
                    ),
                ),
                (
                    "file_id",
                    models.UUIDField(default=uuid.uuid4, help_text="Identifies the file (in its header)"),
                ),
                ("key_id", models.CharField(max_length=40)),
                ("sha256", models.CharField(max_length=64)),
                ("size", models.PositiveBigIntegerField()),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "district",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district"
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="projects.planproject",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]

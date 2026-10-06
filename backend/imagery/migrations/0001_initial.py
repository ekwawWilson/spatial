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
        ("basemaps", "0003_default_presets"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Imagery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("name", models.CharField(max_length=200)),
                (
                    "kind",
                    models.CharField(
                        choices=[("ortho", "Orthophoto (drone or satellite image)"), ("dem", "Elevation model")],
                        default="ortho",
                        max_length=5,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Waiting to be processed"),
                            ("processing", "Processing"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                        ],
                        default="queued",
                        max_length=10,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                ("original_name", models.CharField(max_length=255)),
                ("capture_date", models.DateField(blank=True, help_text="When it was flown or taken", null=True)),
                ("source", models.CharField(blank=True, help_text="Who captured it, and how", max_length=200)),
                (
                    "assigned_crs",
                    models.CharField(blank=True, help_text="CRS given at upload, for files that carry none", max_length=64),
                ),
                ("crs", models.CharField(blank=True, help_text="The file's CRS, as read", max_length=200)),
                ("width", models.PositiveIntegerField(null=True)),
                ("height", models.PositiveIntegerField(null=True)),
                ("bands", models.PositiveSmallIntegerField(null=True)),
                ("resolution_m", models.FloatField(help_text="Ground size of a pixel, metres", null=True)),
                ("bounds", models.JSONField(help_text="[west, south, east, north] in degrees", null=True)),
                ("value_range", models.JSONField(help_text="[min, max] of an elevation model", null=True)),
                ("min_zoom", models.PositiveSmallIntegerField(default=0)),
                ("max_zoom", models.PositiveSmallIntegerField(default=19)),
                ("size_bytes", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "basemap",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="basemaps.basemapsource",
                    ),
                ),
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
                        on_delete=django.db.models.deletion.CASCADE, related_name="imagery", to="projects.planproject"
                    ),
                ),
            ],
            options={"ordering": ["-created_at"], "verbose_name_plural": "imagery"},
        ),
    ]

# Hand-written (GeoDjango fields can't be generated without GDAL on the dev
# machine); test_no_model_changes_without_migrations checks it matches models.py.

import uuid

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("crs", "0003_builtin_systems"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("community", models.CharField(blank=True, max_length=200)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("active", "Active"), ("archived", "Archived")],
                        default="draft",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                    "crs",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="crs.coordinatesystem"
                    ),
                ),
                (
                    "district",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="core.district"
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
                "constraints": [models.UniqueConstraint(fields=("district", "name"), name="unique_project_name")],
            },
        ),
        migrations.CreateModel(
            name="Layer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                (
                    "domain",
                    models.CharField(
                        choices=[
                            ("A", "A. Territory"),
                            ("B", "B. Land & parcels"),
                            ("C", "C. Buildings & properties"),
                            ("D", "D. Streets & addressing"),
                            ("E", "E. Infrastructure & services"),
                            ("F", "F. Environment & physical geography"),
                            ("G", "G. Development activity"),
                            ("H", "H. Socio-economic & demographic"),
                            ("I", "I. Projects & investment"),
                            ("J", "J. Planning & policy"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=5,
                    ),
                ),
                (
                    "geometry_type",
                    models.CharField(
                        choices=[("point", "Point"), ("line", "Line"), ("polygon", "Polygon")], max_length=10
                    ),
                ),
                ("schema", models.JSONField(default=list, help_text="Field definitions: see projects.schema")),
                ("style", models.JSONField(default=dict, help_text="Display style: see projects.styles")),
                ("order", models.IntegerField(default=0, help_text="Draw order: higher is drawn on top")),
                ("visible", models.BooleanField(default=True)),
                ("opacity", models.FloatField(default=1.0)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("drawn", "Drawn"),
                            ("upload", "Uploaded"),
                            ("field", "Field capture"),
                            ("derived", "Derived"),
                        ],
                        default="drawn",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                    "crs",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="crs.coordinatesystem"
                    ),
                ),
                (
                    "district",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="core.district"
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="layers", to="projects.planproject"
                    ),
                ),
            ],
            options={
                "ordering": ["-order", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("project", "name"), name="unique_layer_name"),
                    models.CheckConstraint(
                        condition=models.Q(("opacity__gte", 0), ("opacity__lte", 1)), name="layer_opacity_range"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Feature",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("geom_4326", django.contrib.gis.db.models.fields.GeometryField(null=True, srid=4326)),
                ("properties", models.JSONField(default=dict)),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "origin",
                    models.CharField(
                        choices=[
                            ("drawn", "Drawn"),
                            ("import", "Imported"),
                            ("field", "Field capture"),
                            ("derived", "Derived"),
                        ],
                        default="drawn",
                        max_length=10,
                    ),
                ),
                ("verified", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="core.district"
                    ),
                ),
                (
                    "layer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="features", to="projects.layer"
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
                "indexes": [models.Index(fields=["layer", "id"], name="feature_layer_id_idx")],
            },
        ),
    ]

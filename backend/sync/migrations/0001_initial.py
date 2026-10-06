# Hand-written (depends on the GeoDjango projects app, which can't be loaded
# without GDAL on the dev machine); test_no_model_changes_without_migrations
# checks it matches models.py.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

CASCADE = django.db.models.deletion.CASCADE
SET_NULL = django.db.models.deletion.SET_NULL


def pk():
    return ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"))


def district():
    return ("district", models.ForeignKey(on_delete=CASCADE, related_name="+", to="core.district"))


def user(name, **extra):
    return (name, models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL, **extra))


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        ("readiness", "0003_default_template"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AppliedChange",
            fields=[
                pk(),
                ("change_id", models.UUIDField(unique=True)),
                ("device_id", models.CharField(max_length=64)),
                ("result", models.JSONField()),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                district(),
                user("user"),
            ],
        ),
        migrations.CreateModel(
            name="Conflict",
            fields=[
                pk(),
                ("change_id", models.UUIDField(unique=True)),
                ("device_id", models.CharField(max_length=64)),
                ("base_version", models.PositiveIntegerField(help_text="The version the device edited")),
                ("server_version", models.PositiveIntegerField(help_text="The server's version at that time")),
                ("field_properties", models.JSONField(help_text="Attributes sent by the device", null=True)),
                ("field_geometry", models.JSONField(help_text="Geometry sent (WGS 84), if changed", null=True)),
                ("capture", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("open", "Open"), ("resolved", "Resolved")], default="open", max_length=8)),
                (
                    "resolution",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("keep_field", "Kept the field version"),
                            ("keep_office", "Kept the office version"),
                            ("merged", "Merged field by field"),
                        ],
                        max_length=12,
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                district(),
                ("feature", models.ForeignKey(on_delete=CASCADE, related_name="+", to="projects.feature")),
                ("project", models.ForeignKey(on_delete=CASCADE, related_name="sync_conflicts", to="projects.planproject")),
                user("resolved_by"),
                user("submitted_by"),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Tombstone",
            fields=[
                pk(),
                ("layer_id", models.BigIntegerField(db_index=True)),
                ("feature_uuid", models.UUIDField()),
                ("deleted_at", models.DateTimeField(db_index=True)),
                district(),
            ],
        ),
        migrations.CreateModel(
            name="Capture",
            fields=[
                pk(),
                ("feature_version", models.PositiveIntegerField()),
                (
                    "method",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("gps", "GPS point (averaged)"),
                            ("gps_track", "GPS walk"),
                            ("drawn", "Drawn on the device's map"),
                        ],
                        max_length=10,
                    ),
                ),
                ("accuracy_m", models.FloatField(null=True)),
                ("fix_time", models.DateTimeField(null=True)),
                ("readings", models.PositiveIntegerField(null=True)),
                ("captured_at", models.DateTimeField(null=True)),
                ("device_id", models.CharField(max_length=64)),
                ("notes", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                user("captured_by"),
                district(),
                ("feature", models.ForeignKey(on_delete=CASCADE, related_name="captures", to="projects.feature")),
            ],
            options={"ordering": ["-received_at", "-id"]},
        ),
        migrations.CreateModel(
            name="Photo",
            fields=[
                pk(),
                ("uuid", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("size", models.PositiveBigIntegerField(help_text="Size of the whole file in bytes")),
                ("sha256", models.CharField(max_length=64)),
                ("received", models.PositiveBigIntegerField(default=0, help_text="Bytes received so far")),
                ("complete", models.BooleanField(default=False)),
                ("path", models.CharField(blank=True, max_length=500)),
                ("latitude", models.FloatField(null=True)),
                ("longitude", models.FloatField(null=True)),
                ("accuracy_m", models.FloatField(null=True)),
                ("taken_at", models.DateTimeField(null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                district(),
                ("feature", models.ForeignKey(on_delete=CASCADE, related_name="photos", to="projects.feature")),
                user("uploaded_by"),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="FieldTask",
            fields=[
                pk(),
                ("status", models.CharField(choices=[("open", "To check"), ("done", "Checked")], default="open", max_length=5)),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("confirmed", "Confirmed as recorded"),
                            ("corrected", "Corrected in the field"),
                            ("not_found", "Not found on the ground"),
                        ],
                        max_length=10,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                user("completed_by"),
                user("created_by"),
                district(),
                ("feature", models.ForeignKey(on_delete=CASCADE, related_name="field_tasks", to="projects.feature")),
                ("item", models.ForeignKey(null=True, on_delete=SET_NULL, related_name="field_tasks", to="readiness.item")),
                ("project", models.ForeignKey(on_delete=CASCADE, related_name="field_tasks", to="projects.planproject")),
            ],
            options={
                "ordering": ["id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "open")),
                        fields=("feature",),
                        name="one_open_task_per_feature",
                    )
                ],
            },
        ),
    ]

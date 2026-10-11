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


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DataRoom",
            fields=[
                pk(),
                ("is_open", models.BooleanField(default=False)),
                ("show_applicants", models.BooleanField(default=False)),
                ("welcome", models.TextField(blank=True)),
                ("contact", models.TextField(blank=True, help_text="Office, hours, phone, email")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("district", models.OneToOneField(on_delete=CASCADE, related_name="+", to="core.district")),
            ],
        ),
        migrations.CreateModel(
            name="Publication",
            fields=[
                pk(),
                ("permits", models.BooleanField(default=True)),
                ("zoning", models.BooleanField(default=True)),
                ("published_at", models.DateTimeField(auto_now_add=True)),
                district(),
                (
                    "project",
                    models.OneToOneField(on_delete=CASCADE, related_name="publication", to="projects.planproject"),
                ),
                user("published_by"),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="RoomDocument",
            fields=[
                pk(),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("sdf", "Spatial Development Framework"),
                            ("structure_plan", "Structure plan"),
                            ("local_plan", "Local plan"),
                            ("zoning_scheme", "Zoning scheme"),
                            ("notice", "Notice"),
                            ("consultation", "Record of public consultation"),
                            ("outsourced", "Scope of outsourced services"),
                            ("other", "Other document"),
                        ],
                        max_length=16,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("name", models.CharField(max_length=255)),
                ("path", models.CharField(max_length=500)),
                ("size", models.PositiveBigIntegerField()),
                ("display_from", models.DateField()),
                ("display_until", models.DateField(blank=True, null=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                district(),
                user("uploaded_by"),
            ],
            options={"ordering": ["-display_from", "-id"]},
        ),
        migrations.CreateModel(
            name="InformationRequest",
            fields=[
                pk(),
                ("reference", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=200)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("subject", models.CharField(max_length=200)),
                ("body", models.TextField()),
                ("received_on", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("answered", "Answered"), ("declined", "Declined")],
                        default="open",
                        max_length=8,
                    ),
                ),
                ("answer", models.TextField(blank=True)),
                ("answered_on", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                user("answered_by"),
                district(),
            ],
            options={
                "ordering": ["-id"],
                "constraints": [
                    models.UniqueConstraint(fields=("district", "reference"), name="one_request_reference")
                ],
            },
        ),
    ]

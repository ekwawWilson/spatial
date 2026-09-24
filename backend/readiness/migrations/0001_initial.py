# Hand-written (depends on the GeoDjango projects app, which can't be loaded
# without GDAL on the dev machine); test_no_model_changes_without_migrations
# checks it matches models.py.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

GROUPS = [
    ("authority", "1. Authority and set-up"),
    ("planning_area", "2. Planning area"),
    ("base_map", "3. Base map"),
    ("existing", "4. Existing situation"),
    ("people", "5. People and standards"),
]
KINDS = [
    ("document", "Document or decision"),
    ("layer", "Map layer"),
    ("boundary", "Planning area boundary"),
]
STATUSES = [
    ("not_started", "Not started"),
    ("in_progress", "In progress"),
    ("ready", "Ready"),
    ("verified", "Verified"),
]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Template",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "district",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="core.district",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("district__isnull", True)),
                        fields=("name",),
                        name="one_default_template",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="TemplateItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group", models.CharField(choices=GROUPS, max_length=20)),
                ("key", models.SlugField(max_length=60)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("kind", models.CharField(choices=KINDS, max_length=10)),
                ("domain", models.CharField(blank=True, help_text="Data domain A-J (layer items)", max_length=5)),
                ("geometry_type", models.CharField(blank=True, help_text="Expected geometry (layer items)", max_length=10)),
                ("rules", models.JSONField(blank=True, default=dict)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="readiness.template",
                    ),
                ),
            ],
            options={
                "ordering": ["group", "order", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("template", "key"), name="unique_template_item")
                ],
            },
        ),
        migrations.CreateModel(
            name="Item",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group", models.CharField(choices=GROUPS, max_length=20)),
                ("key", models.SlugField(max_length=60)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("kind", models.CharField(choices=KINDS, max_length=10)),
                ("domain", models.CharField(blank=True, max_length=5)),
                ("geometry_type", models.CharField(blank=True, max_length=10)),
                ("rules", models.JSONField(blank=True, default=dict)),
                ("order", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=STATUSES, default="not_started", max_length=12)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "district",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district"
                    ),
                ),
                (
                    "linked_layer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="projects.layer",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checklist_items",
                        to="projects.planproject",
                    ),
                ),
            ],
            options={
                "ordering": ["group", "order", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("project", "key"), name="unique_project_item")
                ],
            },
        ),
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("path", models.CharField(max_length=500)),
                ("size", models.PositiveBigIntegerField()),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "district",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district"
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="readiness.item",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-uploaded_at"]},
        ),
    ]

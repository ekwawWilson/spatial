# Hand-written, like 0001 (see the note there). Phase 14: the national zoning
# standards' site rules on each district standard, and the zoning scheme register.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.tenancy import audit_trigger_sql, tenant_rls_sql

CASCADE = django.db.models.deletion.CASCADE
SET_NULL = django.db.models.deletion.SET_NULL


def number(name: str, help_text: str = ""):
    options = {"help_text": help_text} if help_text else {}
    return migrations.AddField(
        model_name="developmentstandard",
        name=name,
        field=models.FloatField(blank=True, null=True, **options),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("relations", "0002_rls_audit"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        number("front_setback_m"),
        number("side_setback_m"),
        number("rear_setback_m"),
        number("min_width_m", "Along the street"),
        migrations.AddField(
            model_name="developmentstandard",
            name="min_floors",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="developmentstandard",
            name="prohibited_uses",
            field=models.JSONField(
                blank=True, default=list, help_text="Words that, in a property's use, suggest a breach"
            ),
        ),
        migrations.AddField(
            model_name="developmentstandard",
            name="source",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.CreateModel(
            name="ZoningScheme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("approved", "Approved"), ("adopted", "Existing scheme adopted")],
                        default="draft",
                        max_length=8,
                    ),
                ),
                ("structure_plan_approved_on", models.DateField(blank=True, null=True)),
                ("approved_on", models.DateField(blank=True, null=True)),
                ("effective_on", models.DateField(blank=True, null=True)),
                ("sent_to_luspa_on", models.DateField(blank=True, null=True)),
                (
                    "update_every_months",
                    models.PositiveSmallIntegerField(default=60, help_text="The scheme's schedule for periodic updates"),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(null=True, on_delete=SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
                ("district", models.ForeignKey(on_delete=CASCADE, related_name="+", to="core.district")),
                (
                    "project",
                    models.ForeignKey(on_delete=CASCADE, related_name="zoning_schemes", to="projects.planproject"),
                ),
            ],
            options={"ordering": ["-id"]},
        ),
        migrations.RunSQL(*tenant_rls_sql("relations_zoningscheme")),
        migrations.RunSQL(*audit_trigger_sql("relations_zoningscheme")),
    ]

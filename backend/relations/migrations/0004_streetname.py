# Hand-written, like 0001 (see the note there): street names from proposal to signs.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.tenancy import audit_trigger_sql, tenant_rls_sql


def day(name):
    return (name, models.DateField(blank=True, null=True))


class Migration(migrations.Migration):
    dependencies = [
        ("relations", "0003_zoning"),
        ("projects", "0004_audit_exact_geometry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StreetName",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("basis", models.TextField(blank=True)),
                ("proposed_by", models.CharField(blank=True, max_length=200)),
                ("proposed_on", models.DateField()),
                day("consulted_on"),
                ("consultation", models.TextField(blank=True)),
                day("decided_on"),
                ("decision_note", models.TextField(blank=True)),
                day("published_on"),
                day("signs_on"),
                ("previous_name", models.CharField(blank=True, max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("proposed", "Proposed"),
                            ("consulted", "Consulted on"),
                            ("approved", "Approved"),
                            ("refused", "Refused"),
                        ],
                        default="proposed",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("district", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="street_names", to="projects.planproject")),
                ("street", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="projects.feature")),
            ],
            options={"ordering": ["-proposed_on", "-id"]},
        ),
        migrations.RunSQL(*tenant_rls_sql("relations_streetname")),
        migrations.RunSQL(*audit_trigger_sql("relations_streetname")),
    ]

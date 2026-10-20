# Hand-written, like 0001 (see the note there).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.tenancy import audit_trigger_sql, tenant_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("permits", "0003_habitation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Challenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("review", "Request for review"), ("appeal", "Appeal")], max_length=6)),
                ("body", models.CharField(max_length=8)),
                ("lodged_on", models.DateField()),
                ("grounds", models.TextField()),
                ("decided_on", models.DateField(blank=True, null=True)),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("upheld", "Decision upheld"),
                            ("varied", "Decision varied"),
                            ("overturned", "Decision overturned"),
                            ("withdrawn", "Withdrawn"),
                        ],
                        max_length=10,
                    ),
                ),
                ("decision", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "application",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="challenges", to="permits.application"),
                ),
                (
                    "district",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district"),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"ordering": ["lodged_on", "id"]},
        ),
        migrations.RunSQL(*tenant_rls_sql("permits_challenge")),
        migrations.RunSQL(*audit_trigger_sql("permits_challenge")),
    ]

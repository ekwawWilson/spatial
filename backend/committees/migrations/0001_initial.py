# Hand-written; test_no_model_changes_without_migrations checks it matches models.py.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.tenancy import audit_trigger_sql, tenant_rls_sql

TABLES = ("committees_committee", "committees_meeting")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Committee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=4)),
                ("members", models.JSONField(blank=True, default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("district", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district")),
            ],
            options={
                "ordering": ["kind"],
                "constraints": [models.UniqueConstraint(fields=("district", "kind"), name="one_committee_kind")],
            },
        ),
        migrations.CreateModel(
            name="Meeting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("held_on", models.DateField()),
                ("venue", models.CharField(blank=True, max_length=200)),
                ("notice_served_on", models.DateField(blank=True, null=True)),
                ("attendance", models.JSONField(blank=True, default=list)),
                ("agenda", models.JSONField(blank=True, default=list)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("committee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meetings", to="committees.committee")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("district", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="core.district")),
            ],
            options={"ordering": ["-held_on", "-id"]},
        ),
        *[migrations.RunSQL(*tenant_rls_sql(t)) for t in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(t)) for t in TABLES],
    ]

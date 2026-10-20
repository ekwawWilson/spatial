# Hand-written; test_no_model_changes_without_migrations checks it matches models.py.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.tenancy import audit_trigger_sql, tenant_rls_sql

TABLE = "exchange_exchangekey"


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0002_tenancy_and_audit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExchangeKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("prefix", models.CharField(max_length=24, unique=True)),
                ("digest", models.CharField(max_length=64)),
                ("scopes", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("uses", models.PositiveIntegerField(default=0)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
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
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunSQL(*tenant_rls_sql(TABLE)),
        # Each use updates last_used_at and uses, so the audit log is also the
        # record of who read what when. The key's hash stays out of it.
        migrations.RunSQL(*audit_trigger_sql(TABLE, exclude=("digest",))),
    ]

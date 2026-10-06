"""Row-level security and auditing, and the checklist's imagery item learns
to measure itself: its completion rule (imagery under 12 months old) is added
to the platform default and to project checklists that still have no rule."""

from typing import Any

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

RULE = {"imagery_max_age_days": 365}


def add_rule(apps: Any, schema_editor: Any) -> None:
    for model in ("TemplateItem", "Item"):
        apps.get_model("readiness", model).objects.filter(key="imagery", rules={}).update(rules=RULE)


def remove_rule(apps: Any, schema_editor: Any) -> None:
    for model in ("TemplateItem", "Item"):
        apps.get_model("readiness", model).objects.filter(key="imagery", rules=RULE).update(rules={})


class Migration(migrations.Migration):
    dependencies = [("imagery", "0001_initial"), ("readiness", "0003_default_template")]

    operations = [
        migrations.RunSQL(*tenant_rls_sql("imagery_imagery")),
        migrations.RunSQL(*audit_trigger_sql("imagery_imagery")),
        migrations.RunPython(add_rule, remove_rule),
    ]

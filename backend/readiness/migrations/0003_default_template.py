"""The platform's default checklist (readiness.defaults)."""

from typing import Any

from django.db import migrations

NAME = "Platform default"


def create(apps: Any, schema_editor: Any) -> None:
    from readiness.defaults import DEFAULT_ITEMS

    Template = apps.get_model("readiness", "Template")
    TemplateItem = apps.get_model("readiness", "TemplateItem")
    template = Template.objects.create(name=NAME, district=None)
    for order, item in enumerate(DEFAULT_ITEMS):
        TemplateItem.objects.create(template=template, order=order, **item)


def remove(apps: Any, schema_editor: Any) -> None:
    apps.get_model("readiness", "Template").objects.filter(district=None, name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("readiness", "0002_rls_audit")]

    operations = [migrations.RunPython(create, remove)]

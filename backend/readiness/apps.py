from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_save


class ReadinessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "readiness"
    verbose_name = "Plan readiness checklist"

    def ready(self) -> None:
        from projects.models import PlanProject

        post_save.connect(
            give_new_project_a_checklist, sender=PlanProject, dispatch_uid="readiness-new-project"
        )


def give_new_project_a_checklist(
    sender: Any, instance: Any, created: bool, raw: bool = False, **kwargs: Any
) -> None:
    if created and not raw:
        from .services import ensure_items

        ensure_items(instance)

from celery import shared_task
from django.core.cache import cache

from core.tenancy import tenant_context
from projects.models import Feature, PlanProject

from . import services
from .models import LayerRole, Run


@shared_task  # type: ignore[misc]
def refresh_project(project_id: int, district_id: int, feature_id: int | None) -> None:
    """Refreshes links after an edit: one property's, or the whole project's."""
    cache.delete(f"relations.pending.{project_id}.{feature_id or 'all'}")
    with tenant_context(district_id):
        project = PlanProject.objects.filter(pk=project_id).first()
        if project is None:
            return
        scope = None
        if feature_id is not None:
            if not Feature.objects.filter(pk=feature_id).exists():
                scope = None  # it was deleted: its links went with it; redo the totals
            else:
                scope = [feature_id]
        services.run_project(project, Run.Trigger.EDIT, scope=scope)


@shared_task  # type: ignore[misc]
def nightly() -> int:
    """Runs every procedure for every project that has layers mapped."""
    with tenant_context(None, is_system_admin=True):
        targets = list(
            LayerRole.objects.values_list("project_id", "district_id")
            .distinct()
            .order_by("project_id")
        )
    done = 0
    for project_id, district_id in targets:
        with tenant_context(district_id):
            project = PlanProject.objects.filter(pk=project_id).exclude(status="archived").first()
            if project is None:
                continue
            try:
                services.run_project(project, Run.Trigger.NIGHTLY)
                done += 1
            except Exception:  # noqa: BLE001, S112 - one project's failure doesn't stop the rest; the run records it
                continue
    return done

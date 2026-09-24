from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("checklist-items", views.ItemViewSet, basename="checklist-item")
router.register("checklist-attachments", views.AttachmentViewSet, basename="checklist-attachment")
router.register("readiness/template-items", views.TemplateItemViewSet, basename="template-item")

urlpatterns = [
    path(
        "projects/<int:project_id>/checklist/",
        views.ChecklistView.as_view(),
        name="project-checklist",
    ),
    path(
        "projects/<int:project_id>/checklist/export/",
        views.ChecklistExportView.as_view(),
        name="project-checklist-export",
    ),
    path("readiness/", views.DashboardView.as_view(), name="readiness-dashboard"),
    path("readiness/template/", views.TemplateView.as_view(), name="readiness-template"),
    *router.urls,
]

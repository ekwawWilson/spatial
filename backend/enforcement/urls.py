from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("enforcement/cases", views.CaseViewSet, basename="enforcement-case")
router.register("enforcement/notices", views.NoticeViewSet, basename="enforcement-notice")

urlpatterns = [
    path("enforcement/registry/", views.RegistryView.as_view(), name="enforcement-registry"),
    path(
        "projects/<int:project_id>/detections/",
        views.DetectionView.as_view(),
        name="project-detections",
    ),
    *router.urls,
]

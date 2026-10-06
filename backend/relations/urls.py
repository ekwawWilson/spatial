from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("relationships", views.RelationshipViewSet, basename="relationship")
router.register("standards", views.StandardViewSet, basename="standard")

urlpatterns = [
    path("relations/registry/", views.RegistryView.as_view(), name="relations-registry"),
    path(
        "projects/<int:project_id>/layer-roles/",
        views.LayerRolesView.as_view(),
        name="project-layer-roles",
    ),
    path(
        "projects/<int:project_id>/relations/run/",
        views.RunView.as_view(),
        name="project-relations-run",
    ),
    *router.urls,
]

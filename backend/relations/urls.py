from django.urls import path
from rest_framework.routers import DefaultRouter

from . import naming_views, views

router = DefaultRouter()
router.register("relationships", views.RelationshipViewSet, basename="relationship")
router.register("standards", views.StandardViewSet, basename="standard")
router.register("zoning-schemes", views.ZoningSchemeViewSet, basename="zoning-scheme")
router.register("street-names", naming_views.StreetNameViewSet, basename="street-name")

urlpatterns = [
    path("relations/registry/", views.RegistryView.as_view(), name="relations-registry"),
    path("relations/zones/", views.ZonesView.as_view(), name="relations-zones"),
    path(
        "projects/<int:project_id>/addressing/",
        views.AddressingView.as_view(),
        name="project-addressing",
    ),
    path(
        "projects/<int:project_id>/zoning-style/",
        views.ZoningStyleView.as_view(),
        name="project-zoning-style",
    ),
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

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("projects", views.ProjectViewSet, basename="project")
router.register("layers", views.LayerViewSet, basename="layer")
router.register("features", views.FeatureViewSet, basename="feature")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "layers/<int:layer_id>/tiles/<int:z>/<int:x>/<int:y>.pbf",
        views.LayerTileView.as_view(),
        name="layer-tile",
    ),
]

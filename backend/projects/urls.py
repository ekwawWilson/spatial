from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("projects", views.ProjectWithBoundaryViewSet, basename="project")
router.register("layers", views.LayerViewSet, basename="layer")
router.register("features", views.FeatureWithEditingViewSet, basename="feature")

urlpatterns = [
    path("", include(router.urls)),
    path("geometry/traverse/", views.TraverseView.as_view(), name="traverse"),
    path(
        "layers/<int:layer_id>/tiles/<int:z>/<int:x>/<int:y>.pbf",
        views.LayerTileView.as_view(),
        name="layer-tile",
    ),
]

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("systems", views.CoordinateSystemViewSet, basename="crs-system")

urlpatterns = [
    path("", include(router.urls)),
    path("validate/", views.ValidateDefinitionView.as_view(), name="crs-validate"),
    path("defaults/", views.DefaultsView.as_view(), name="crs-defaults"),
    path("defaults/system/", views.SetSystemDefaultView.as_view(), name="crs-default-system"),
    path("defaults/district/", views.SetDistrictDefaultView.as_view(), name="crs-default-district"),
    path("defaults/me/", views.SetMyDefaultView.as_view(), name="crs-default-me"),
    path("transform/", views.TransformView.as_view(), name="crs-transform"),
    path("operations/", views.OperationsView.as_view(), name="crs-operations"),
]

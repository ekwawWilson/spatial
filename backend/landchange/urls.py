from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("land/applications", views.LandApplicationViewSet, basename="land-application")

urlpatterns = [
    path("land/registry/", views.RegistryView.as_view(), name="land-registry"),
    *router.urls,
]

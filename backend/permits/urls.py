from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("permits/applications", views.ApplicationViewSet, basename="permit-application")
router.register("permits/documents", views.DocumentViewSet, basename="permit-document")
router.register("permits/fees", views.FeeViewSet, basename="permit-fee")

urlpatterns = [
    path("permits/registry/", views.RegistryView.as_view(), name="permits-registry"),
    path("public/permits/<str:token>/", views.VerifyView.as_view(), name="permit-verify"),
    *router.urls,
]

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("revenue/properties", views.PropertyViewSet, basename="revenue-property")
router.register("revenue/rates", views.RateBandViewSet, basename="revenue-rate")
router.register("revenue/betterment", views.SchemeViewSet, basename="revenue-betterment")
router.register("revenue/betterment-charges", views.ChargeViewSet, basename="revenue-charge")

urlpatterns = [
    path("projects/<int:project_id>/register/", views.RegisterView.as_view(), name="register"),
    path(
        "projects/<int:project_id>/register/csv/",
        views.RegisterCsvView.as_view(),
        name="register-csv",
    ),
    path(
        "projects/<int:project_id>/register/<str:what>/",
        views.RegisterActionView.as_view(),
        name="register-action",
    ),
    *router.urls,
]

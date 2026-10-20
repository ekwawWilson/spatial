from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("exchange/keys", views.KeyViewSet, basename="exchange-key")

urlpatterns = [
    # For key holders (no sign-in): one dataset of the district's records.
    path("exchange/v1/<str:dataset>/", views.ExchangeView.as_view(), name="exchange-data"),
    *router.urls,
]

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("basemaps", views.BasemapViewSet, basename="basemap")

urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("imagery", views.ImageryViewSet, basename="imagery")

urlpatterns = router.urls

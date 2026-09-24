from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("jobs", views.DataJobViewSet, basename="datajob")

urlpatterns = router.urls

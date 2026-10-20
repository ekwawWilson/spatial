from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("committees/meetings", views.MeetingViewSet, basename="committee-meeting")

urlpatterns = [
    path("committees/", views.CommitteesView.as_view(), name="committees"),
    *router.urls,
]

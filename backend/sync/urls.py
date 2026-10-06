from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("sync/photos", views.PhotoViewSet, basename="sync-photo")
router.register("sync/conflicts", views.ConflictViewSet, basename="sync-conflict")

urlpatterns = [
    path("sync/push/", views.PushView.as_view(), name="sync-push"),
    path("sync/pull/", views.PullView.as_view(), name="sync-pull"),
    path("sync/captures/", views.CapturesView.as_view(), name="sync-captures"),
    path("sync/tasks/", views.TasksView.as_view(), name="sync-tasks"),
    path(
        "checklist-items/<int:item_id>/send-to-field/",
        views.SendToFieldView.as_view(),
        name="checklist-item-send-to-field",
    ),
    *router.urls,
]

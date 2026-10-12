from django.urls import path
from rest_framework.routers import DefaultRouter

from . import public, views

router = DefaultRouter()
router.register("dataroom/publications", views.PublicationViewSet, basename="dataroom-publication")
router.register("dataroom/documents", views.DocumentViewSet, basename="dataroom-document")
router.register("dataroom/requests", views.RequestViewSet, basename="dataroom-request")

urlpatterns = [
    path("dataroom/", views.RoomSettingsView.as_view(), name="dataroom-settings"),
    # No sign-in: what the public sees.
    path("public/rooms/", public.RoomsView.as_view(), name="public-rooms"),
    path("public/rooms/<str:code>/", public.RoomView.as_view(), name="public-room"),
    path(
        "public/rooms/<str:code>/register/", public.RegisterView.as_view(), name="public-register"
    ),
    path("public/rooms/<str:code>/status/", public.StatusView.as_view(), name="public-status"),
    path("public/rooms/<str:code>/zone/", public.ZoneView.as_view(), name="public-zone"),
    path("public/rooms/<str:code>/notices/", public.NoticesView.as_view(), name="public-notices"),
    path(
        "public/rooms/<str:code>/land-applications/",
        public.LandApplicationsView.as_view(),
        name="public-land-applications",
    ),
    path("public/rooms/<str:code>/plans/", public.PlansView.as_view(), name="public-plans"),
    path(
        "public/rooms/<str:code>/plans/<int:project_id>/comments/",
        public.PlanCommentView.as_view(),
        name="public-plan-comment",
    ),
    path(
        "public/rooms/<str:code>/requests/", public.RequestsView.as_view(), name="public-requests"
    ),
    path(
        "public/rooms/<str:code>/documents/<int:document_id>/",
        public.DocumentView.as_view(),
        name="public-document",
    ),
    *router.urls,
]

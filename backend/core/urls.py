from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views_admin, views_auth
from .views import HealthView

router = DefaultRouter()
router.register("regions", views_admin.RegionViewSet, basename="region")
router.register("districts", views_admin.DistrictViewSet, basename="district")
router.register("users", views_admin.UserViewSet, basename="user")
router.register("memberships", views_admin.MembershipViewSet, basename="membership")
router.register("audit", views_admin.AuditLogViewSet, basename="audit")

auth_patterns = [
    path("login/", views_auth.LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", views_auth.LogoutView.as_view(), name="logout"),
    path("me/", views_auth.MeView.as_view(), name="me"),
    path("password/change/", views_auth.ChangePasswordView.as_view(), name="password-change"),
    path("password/reset/", views_auth.PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        views_auth.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include(auth_patterns)),
    path("", include(router.urls)),
]

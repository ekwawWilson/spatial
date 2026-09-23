"""Authentication: JWT plus district context, and login lockout."""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import District, Membership, User
from .tenancy import set_db_context

DISTRICT_HEADER = "HTTP_X_DISTRICT_ID"


class TenantJWTAuthentication(JWTAuthentication):
    """Authenticates the JWT, then scopes the database transaction to the caller
    and, if an X-District-ID header is sent, to that district.

    Sets on the request:
      request.district_id  - the active district, or None
      request.membership   - the caller's Membership there (None for system
                             admins acting in a district they don't belong to)
    """

    def authenticate(self, request: Request) -> tuple[Any, Any] | None:
        # Anonymous requests (login, password reset) also run as the app role.
        set_db_context(user_id=None, district_id=None, is_system_admin=False)
        request.district_id = None  # type: ignore[attr-defined]
        request.membership = None  # type: ignore[attr-defined]

        result = super().authenticate(request)
        if result is None:
            return None
        user = result[0]
        if not isinstance(user, User):
            raise AuthenticationFailed("Unknown user type.")
        set_db_context(user_id=user.id, district_id=None, is_system_admin=user.is_system_admin)

        raw = request.META.get(DISTRICT_HEADER)
        if raw:
            district_id, membership = self._resolve_district(user, raw)
            request.district_id = district_id  # type: ignore[attr-defined]
            request.membership = membership  # type: ignore[attr-defined]
            set_db_context(
                user_id=user.id, district_id=district_id, is_system_admin=user.is_system_admin
            )
        return result

    @staticmethod
    def _resolve_district(user: User, raw: str) -> tuple[int, Membership | None]:
        try:
            district_id = int(raw)
        except ValueError:
            raise PermissionDenied("X-District-ID must be a district id.") from None
        # Readable here because the context already carries the user id.
        membership = (
            Membership.objects.select_related("district")
            .filter(user=user, district_id=district_id, is_active=True, district__is_active=True)
            .first()
        )
        if membership:
            return district_id, membership
        if user.is_system_admin and District.objects.filter(id=district_id).exists():
            return district_id, None
        raise PermissionDenied("You are not a member of this district.")


def attempt_login(request: Request, email: str, password: str) -> User | None:
    """Returns the user if the credentials are valid and the account isn't locked.

    Each failure counts towards AUTH_LOCKOUT_THRESHOLD; reaching it locks the
    account for AUTH_LOCKOUT_MINUTES. Callers must return a response rather than
    raise, so the failure count is committed rather than rolled back.
    """
    email = email.strip().lower()
    now = timezone.now()
    user = User.objects.filter(email=email).first()
    if user and user.locked_until and user.locked_until > now:
        return None

    authed = authenticate(request, email=email, password=password)
    if not isinstance(authed, User):
        if user:
            User.objects.filter(pk=user.pk).update(failed_login_count=F("failed_login_count") + 1)
            user.refresh_from_db(fields=["failed_login_count"])
            if user.failed_login_count >= settings.AUTH_LOCKOUT_THRESHOLD:
                user.locked_until = now + timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)
                user.failed_login_count = 0
                user.save(update_fields=["locked_until", "failed_login_count"])
        return None

    authed.failed_login_count = 0
    authed.locked_until = None
    authed.last_login = now
    authed.save(update_fields=["failed_login_count", "locked_until", "last_login"])
    return authed

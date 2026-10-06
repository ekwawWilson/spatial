"""Rate limits. Rates come from settings each time they're needed (so they can
be changed without touching code), and API_THROTTLING=False turns them off.

Scopes:
  anon    any request without a sign-in, per IP address
  user    any signed-in request, per user (generous: a map loads many tiles)
  login   sign-in and password-reset attempts, per IP address (brute force)
  upload  file uploads, per user (each can be hundreds of megabytes)
"""

from typing import Any

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class _FromSettings(SimpleRateThrottle):
    def get_rate(self) -> str | None:
        rates: dict[str, str | None] = settings.API_THROTTLE_RATES
        return rates.get(self.scope or "")

    def allow_request(self, request: Request, view: Any) -> bool:
        if not settings.API_THROTTLING:
            return True
        return super().allow_request(request, view)


class AnonThrottle(_FromSettings, AnonRateThrottle):
    scope = "anon"


class UserThrottle(_FromSettings, UserRateThrottle):
    scope = "user"


class LoginThrottle(_FromSettings, SimpleRateThrottle):
    """Per IP address, whether or not the attempt names a real account."""

    scope = "login"

    def get_cache_key(self, request: Request, view: Any) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class UploadThrottle(_FromSettings, UserRateThrottle):
    scope = "upload"

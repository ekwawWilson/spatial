"""Refuses to run in production with the example secrets.

With DJANGO_DEBUG=false, every value that .env.example marks CHANGE_ME, and a
development .spp key, is an error: `manage.py check` (and so `migrate` and
the server) stop with an explanation instead of running insecurely.
"""

from typing import Any

from django.conf import settings
from django.core.checks import Error, register


@register()
def production_secrets(app_configs: Any, **kwargs: Any) -> list[Error]:
    if settings.DEBUG:
        return []
    errors = []
    if "CHANGE_ME" in settings.SECRET_KEY or len(settings.SECRET_KEY) < 50:
        errors.append(
            Error(
                "DJANGO_SECRET_KEY is the example value or too short.",
                hint="Set at least 50 random characters in .env (docs/ops/deployment.md).",
                id="spatial.E001",
            )
        )
    database = settings.DATABASES["default"]
    if "CHANGE_ME" in str(database.get("PASSWORD", "")):
        errors.append(
            Error(
                "The database password is the example value.",
                hint="Set POSTGRES_PASSWORD and APP_DB_PASSWORD in .env before first start.",
                id="spatial.E002",
            )
        )
    if any(entry.strip().startswith("dev-") for entry in settings.SPP_ORG_KEYS.split(",")):
        errors.append(
            Error(
                "SPP_ORG_KEYS holds a development key.",
                hint="Make a real one: manage.py spp_key generate (docs/ops/spp-keys.md).",
                id="spatial.E003",
            )
        )
    if settings.ALLOWED_HOSTS in ([], ["*"]):
        errors.append(
            Error(
                "DJANGO_ALLOWED_HOSTS must name the site's address.",
                id="spatial.E004",
            )
        )
    return errors

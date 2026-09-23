from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        from . import schema  # noqa: F401 - registers OpenAPI extensions

        post_migrate.connect(grant_app_role, sender=self, dispatch_uid="core.grant_app_role")


def grant_app_role(using: str = "default", **kwargs: Any) -> None:
    """Gives the app role access to every table after migrations.

    Default privileges set at database creation don't carry over to the test
    database, and new tables appear with each phase, so grants are re-applied
    here after every migrate. Runs as the migrating (owner) role.
    """
    from django.conf import settings
    from django.db import connections

    from .tenancy import READ_ONLY_FOR_APP

    connection = connections[using]
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [settings.APP_DB_USER])
        if cursor.fetchone() is None:
            return
        role = connection.ops.quote_name(settings.APP_DB_USER)
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
        )
        cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
        for table in READ_ONLY_FOR_APP:
            cursor.execute("SELECT to_regclass(%s)", [table])
            if cursor.fetchone()[0] is not None:
                cursor.execute(f"REVOKE INSERT, UPDATE, DELETE ON {table} FROM {role}")

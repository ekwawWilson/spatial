"""District tenancy enforced by PostgreSQL row-level security (RLS).

How it fits together:

* Every API request runs in one transaction (ATOMIC_REQUESTS). After DRF has
  authenticated the caller, core.auth.TenantJWTAuthentication calls
  set_db_context(), which, for that transaction only:
    - switches to the non-superuser app role (SET LOCAL ROLE), so RLS applies
      even when the connection itself belongs to the owner role (as in tests);
    - records the user, the active district and the system-admin flag in the
      session settings app.user_id / app.district_id / app.is_system_admin.
* RLS policies (created with tenant_rls_sql() in migrations) compare each row's
  district_id with app_current_district(). With no district set, a tenant table
  returns no rows: the default is deny.
* The audit trigger (AUDIT_FUNCTION_SQL) records the same user and district.
* ResetDbContextMiddleware clears the context after each request. In production
  the transaction has already ended, so this is a no-op. In tests, requests run
  inside the test's own transaction, and without the reset the test would carry
  on as the app role.

Code that touches tenant tables outside a request (Celery tasks, commands) uses
tenant_context().
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connection, transaction
from django.http import HttpRequest, HttpResponse

# --- SQL used by migrations -------------------------------------------------

CONTEXT_FUNCTIONS_SQL = """
CREATE OR REPLACE FUNCTION app_current_user() RETURNS bigint
    LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.user_id', true), '')::bigint $$;

CREATE OR REPLACE FUNCTION app_current_district() RETURNS bigint
    LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.district_id', true), '')::bigint $$;

CREATE OR REPLACE FUNCTION app_is_system_admin() RETURNS boolean
    LANGUAGE sql STABLE AS
    $$ SELECT COALESCE(current_setting('app.is_system_admin', true), '') = 'on' $$;
"""

DROP_CONTEXT_FUNCTIONS_SQL = """
DROP FUNCTION IF EXISTS app_is_system_admin();
DROP FUNCTION IF EXISTS app_current_district();
DROP FUNCTION IF EXISTS app_current_user();
"""

# Runs as the function owner (SECURITY DEFINER), so it can write the audit table
# even though the app role only has SELECT on it. Trigger arguments name columns
# to leave out of the recorded row (e.g. password hashes).
AUDIT_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION app_audit() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
DECLARE
    old_row jsonb;
    new_row jsonb;
    col text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN old_row := to_jsonb(OLD); END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN new_row := to_jsonb(NEW); END IF;
    IF TG_NARGS > 0 THEN
        FOREACH col IN ARRAY TG_ARGV LOOP
            old_row := old_row - col;
            new_row := new_row - col;
        END LOOP;
    END IF;
    INSERT INTO core_auditlog
        (occurred_at, table_name, row_id, action, before, after, user_id, district_id)
    VALUES (
        clock_timestamp(),
        TG_TABLE_NAME,
        COALESCE(new_row, old_row) ->> 'id',
        TG_OP,
        old_row,
        new_row,
        app_current_user(),
        COALESCE((COALESCE(new_row, old_row) ->> 'district_id')::bigint, app_current_district())
    );
    RETURN NULL;
END
$$;
"""

DROP_AUDIT_FUNCTION_SQL = "DROP FUNCTION IF EXISTS app_audit();"


def audit_trigger_sql(table: str, exclude: tuple[str, ...] = ()) -> tuple[str, str]:
    """(forward, reverse) SQL attaching the audit trigger to a table."""
    args = ", ".join(f"'{col}'" for col in exclude)
    forward = (
        f"CREATE TRIGGER {table}_audit AFTER INSERT OR UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION app_audit({args});"
    )
    return forward, f"DROP TRIGGER IF EXISTS {table}_audit ON {table};"


TENANT_CHECK = "(district_id = app_current_district() OR app_is_system_admin())"


def tenant_rls_sql(table: str, extra_read: str = "") -> tuple[str, str]:
    """(forward, reverse) SQL enabling the standard district policy on a table
    with a district_id column. extra_read widens SELECT only (e.g. a user may
    always see their own memberships)."""
    read = TENANT_CHECK[:-1] + (f" OR {extra_read})" if extra_read else ")")
    forward = f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON {table} FOR SELECT USING {read};
CREATE POLICY tenant_insert ON {table} FOR INSERT WITH CHECK {TENANT_CHECK};
CREATE POLICY tenant_update ON {table} FOR UPDATE USING {TENANT_CHECK} WITH CHECK {TENANT_CHECK};
CREATE POLICY tenant_delete ON {table} FOR DELETE USING {TENANT_CHECK};
"""
    reverse = f"""
DROP POLICY IF EXISTS tenant_delete ON {table};
DROP POLICY IF EXISTS tenant_update ON {table};
DROP POLICY IF EXISTS tenant_insert ON {table};
DROP POLICY IF EXISTS tenant_select ON {table};
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""
    return forward, reverse


# Tables the app role may read but never write.
READ_ONLY_FOR_APP = ("core_auditlog", "spatial_ref_sys")


# --- Runtime context ----------------------------------------------------------


def set_db_context(*, user_id: int | None, district_id: int | None, is_system_admin: bool) -> None:
    """Switch the current transaction to the app role and set the tenant context."""
    if not connection.in_atomic_block:
        raise ImproperlyConfigured(
            "Tenant context needs a transaction (ATOMIC_REQUESTS or tenant_context())."
        )
    role = connection.ops.quote_name(settings.APP_DB_USER)
    with connection.cursor() as cursor:
        cursor.execute(f"SET LOCAL ROLE {role}")
        cursor.execute(
            "SELECT set_config('app.user_id', %s, true),"
            " set_config('app.district_id', %s, true),"
            " set_config('app.is_system_admin', %s, true)",
            [
                str(user_id) if user_id else "",
                str(district_id) if district_id else "",
                "on" if is_system_admin else "",
            ],
        )


def reset_db_context() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT set_config('app.user_id', '', false),"
            " set_config('app.district_id', '', false),"
            " set_config('app.is_system_admin', '', false)"
        )


@contextmanager
def tenant_context(
    district_id: int | None, *, user_id: int | None = None, is_system_admin: bool = False
) -> Iterator[None]:
    """Run a block as the app role for one district, in its own transaction."""
    with transaction.atomic():
        set_db_context(user_id=user_id, district_id=district_id, is_system_admin=is_system_admin)
        yield
        # Only needed on success: a rollback (also to a savepoint) already
        # discards SET LOCAL, and resetting inside an aborted transaction fails.
        reset_db_context()


class ResetDbContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.get_response(request)
        finally:
            # Skip requests that never opened a database connection.
            if connection.connection is not None:
                try:
                    reset_db_context()
                except DatabaseError:
                    # An aborted transaction is rolled back by its owner, which
                    # also discards the SET LOCAL context.
                    pass

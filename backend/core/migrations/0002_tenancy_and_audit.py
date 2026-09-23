"""Row-level security and audit triggers for the Phase 1 tables.

The SQL comes from core.tenancy helpers, which are therefore part of migration
history: change them only in ways that keep these statements valid, and put
behaviour changes in new migrations (CREATE OR REPLACE for functions).
"""

from django.db import migrations

from core.tenancy import (
    AUDIT_FUNCTION_SQL,
    CONTEXT_FUNCTIONS_SQL,
    DROP_AUDIT_FUNCTION_SQL,
    DROP_CONTEXT_FUNCTIONS_SQL,
    audit_trigger_sql,
    tenant_rls_sql,
)

AUDITED = [
    ("core_user", ("password",)),
    ("core_region", ()),
    ("core_district", ()),
    ("core_membership", ()),
]

AUDIT_LOG_RLS = (
    """
ALTER TABLE core_auditlog ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_select ON core_auditlog FOR SELECT
    USING (district_id = app_current_district() OR app_is_system_admin());
""",
    """
DROP POLICY IF EXISTS tenant_select ON core_auditlog;
ALTER TABLE core_auditlog DISABLE ROW LEVEL SECURITY;
""",
)


def _ops() -> list[migrations.RunSQL]:
    ops = [
        migrations.RunSQL(CONTEXT_FUNCTIONS_SQL, DROP_CONTEXT_FUNCTIONS_SQL),
        migrations.RunSQL(AUDIT_FUNCTION_SQL, DROP_AUDIT_FUNCTION_SQL),
    ]
    for table, exclude in AUDITED:
        forward, reverse = audit_trigger_sql(table, exclude)
        ops.append(migrations.RunSQL(forward, reverse))
    # A user can always read their own memberships (to pick a district).
    forward, reverse = tenant_rls_sql("core_membership", extra_read="user_id = app_current_user()")
    ops.append(migrations.RunSQL(forward, reverse))
    ops.append(migrations.RunSQL(*AUDIT_LOG_RLS))
    return ops


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = _ops()

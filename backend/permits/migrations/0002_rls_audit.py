"""Row-level security on every table. Auditing where people decide or record
things; the counter and the events are bookkeeping."""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

TABLES = (
    "permits_counter",
    "permits_fee",
    "permits_application",
    "permits_document",
    "permits_comment",
    "permits_inspection",
    "permits_event",
)
AUDITED = (
    "permits_fee",
    "permits_application",
    "permits_document",
    "permits_comment",
    "permits_inspection",
)


class Migration(migrations.Migration):
    dependencies = [("permits", "0001_initial")]

    operations = [
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[
            # The token is what a certificate holder shows: kept out of the log.
            migrations.RunSQL(*audit_trigger_sql(table, exclude=("token",) if table == "permits_application" else ()))
            for table in AUDITED
        ],
    ]

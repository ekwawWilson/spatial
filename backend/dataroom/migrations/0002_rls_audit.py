"""Row-level security and auditing on every table: each is something the
Assembly decides to show, or a member of the public asked."""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

TABLES = (
    "dataroom_dataroom",
    "dataroom_publication",
    "dataroom_roomdocument",
    "dataroom_informationrequest",
)


class Migration(migrations.Migration):
    dependencies = [("dataroom", "0001_initial"), ("permits", "0002_rls_audit")]

    operations = [
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(table)) for table in TABLES],
    ]

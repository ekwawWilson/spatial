"""Row-level security on every table. Auditing where people decide things:
roles, standards and relationships. Runs are themselves a log."""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

TABLES = ("relations_layerrole", "relations_developmentstandard", "relations_relationship", "relations_run")
AUDITED = ("relations_layerrole", "relations_developmentstandard", "relations_relationship")


class Migration(migrations.Migration):
    dependencies = [("relations", "0001_initial")]

    operations = [
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(table)) for table in AUDITED],
    ]

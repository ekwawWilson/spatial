from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql


class Migration(migrations.Migration):
    dependencies = [("transfer", "0001_initial")]

    operations = [
        migrations.RunSQL(*tenant_rls_sql("transfer_datajob")),
        # Inspection and reports can be large and are already on the job row.
        migrations.RunSQL(*audit_trigger_sql("transfer_datajob", ("inspection", "report", "progress"))),
    ]

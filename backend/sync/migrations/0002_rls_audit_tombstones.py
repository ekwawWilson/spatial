"""Row-level security and auditing, and the trigger that leaves a tombstone
whenever a feature is deleted (however it is deleted), so devices can remove
it on their next pull."""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

TABLES = (
    "sync_appliedchange",
    "sync_conflict",
    "sync_tombstone",
    "sync_capture",
    "sync_photo",
    "sync_fieldtask",
)
# Audited: what people decide or record. Tombstones and applied changes are
# themselves logs of other audited events.
AUDITED = ("sync_conflict", "sync_capture", "sync_photo", "sync_fieldtask")

TOMBSTONE_TRIGGER = (
    """
CREATE OR REPLACE FUNCTION sync_leave_tombstone() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
BEGIN
    INSERT INTO sync_tombstone (district_id, layer_id, feature_uuid, deleted_at)
    VALUES (OLD.district_id, OLD.layer_id, OLD.uuid, clock_timestamp());
    RETURN NULL;
END
$$;
CREATE TRIGGER projects_feature_tombstone AFTER DELETE ON projects_feature
    FOR EACH ROW EXECUTE FUNCTION sync_leave_tombstone();
""",
    """
DROP TRIGGER IF EXISTS projects_feature_tombstone ON projects_feature;
DROP FUNCTION IF EXISTS sync_leave_tombstone();
""",
)


class Migration(migrations.Migration):
    dependencies = [("sync", "0001_initial")]

    operations = [
        *[migrations.RunSQL(*tenant_rls_sql(table)) for table in TABLES],
        *[migrations.RunSQL(*audit_trigger_sql(table)) for table in AUDITED],
        migrations.RunSQL(*TOMBSTONE_TRIGGER),
    ]

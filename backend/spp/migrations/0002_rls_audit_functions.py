"""Row-level security and auditing for file records, and two functions that
opening a file needs but the app role can't do on its own:

* app_taken_feature_uuids: which of these feature UUIDs already exist anywhere
  (row-level security hides other districts' features, but UUIDs are unique
  across the whole server, so a clash must be found before inserting).
* app_import_feature_history: writes a feature's earlier versions, carried in
  the file, to the audit log (which only triggers may write). It refuses ids
  that already have a feature, so it can't rewrite the history of existing
  data: ids are reserved from the sequence first, history is written, and the
  features are inserted last.
"""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

FUNCTIONS = (
    """
CREATE OR REPLACE FUNCTION app_taken_feature_uuids(p_uuids uuid[]) RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT uuid FROM projects_feature WHERE uuid = ANY(p_uuids) $$;

CREATE OR REPLACE FUNCTION app_import_feature_history(
    p_row_id bigint, p_action text, p_before jsonb, p_after jsonb, p_occurred_at timestamptz
) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
BEGIN
    IF app_current_district() IS NULL THEN
        RAISE EXCEPTION 'no district selected';
    END IF;
    IF p_action NOT IN ('INSERT', 'UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'unknown action %', p_action;
    END IF;
    IF EXISTS (SELECT 1 FROM projects_feature WHERE id = p_row_id) THEN
        RAISE EXCEPTION 'feature % already exists; its history cannot be imported', p_row_id;
    END IF;
    INSERT INTO core_auditlog
        (occurred_at, table_name, row_id, action, before, after, user_id, district_id)
    VALUES (p_occurred_at, 'projects_feature', p_row_id::text, p_action, p_before, p_after,
            NULL, app_current_district());
END
$$;
""",
    """
DROP FUNCTION IF EXISTS app_import_feature_history(bigint, text, jsonb, jsonb, timestamptz);
DROP FUNCTION IF EXISTS app_taken_feature_uuids(uuid[]);
""",
)


class Migration(migrations.Migration):
    dependencies = [("spp", "0001_initial")]

    operations = [
        migrations.RunSQL(*tenant_rls_sql("spp_filerecord")),
        migrations.RunSQL(*audit_trigger_sql("spp_filerecord", ("summary",))),
        migrations.RunSQL(*FUNCTIONS),
    ]

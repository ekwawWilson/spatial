"""Record feature geometry in the audit log exactly.

to_jsonb() turns a PostGIS geometry into GeoJSON with 9 decimals, which isn't
exact enough to restore surveyed coordinates. The audit function learns an
'ewkb:<column>' argument that stores that column as hex EWKB (exact) instead,
and the feature trigger uses it for geom_native.
"""

from django.db import migrations

AUDIT_FUNCTION_V2 = """
CREATE OR REPLACE FUNCTION app_audit() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
DECLARE
    old_row jsonb;
    new_row jsonb;
    col text;
    val text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN old_row := to_jsonb(OLD); END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN new_row := to_jsonb(NEW); END IF;
    IF TG_NARGS > 0 THEN
        FOREACH col IN ARRAY TG_ARGV LOOP
            IF col LIKE 'ewkb:%' THEN
                col := substr(col, 6);
                IF old_row IS NOT NULL THEN
                    EXECUTE format('SELECT encode(ST_AsEWKB(($1).%I), ''hex'')', col) USING OLD INTO val;
                    old_row := jsonb_set(old_row, ARRAY[col], COALESCE(to_jsonb(val), 'null'::jsonb));
                END IF;
                IF new_row IS NOT NULL THEN
                    EXECUTE format('SELECT encode(ST_AsEWKB(($1).%I), ''hex'')', col) USING NEW INTO val;
                    new_row := jsonb_set(new_row, ARRAY[col], COALESCE(to_jsonb(val), 'null'::jsonb));
                END IF;
            ELSE
                old_row := old_row - col;
                new_row := new_row - col;
            END IF;
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

# The Phase 1 version, restored when this migration is reversed.
from core.tenancy import AUDIT_FUNCTION_SQL  # noqa: E402

FEATURE_TRIGGER = (
    """
DROP TRIGGER IF EXISTS projects_feature_audit ON projects_feature;
CREATE TRIGGER projects_feature_audit AFTER INSERT OR UPDATE OR DELETE ON projects_feature
    FOR EACH ROW EXECUTE FUNCTION app_audit('geom_4326', 'ewkb:geom_native');
""",
    """
DROP TRIGGER IF EXISTS projects_feature_audit ON projects_feature;
CREATE TRIGGER projects_feature_audit AFTER INSERT OR UPDATE OR DELETE ON projects_feature
    FOR EACH ROW EXECUTE FUNCTION app_audit('geom_4326');
""",
)


class Migration(migrations.Migration):
    dependencies = [("projects", "0003_project_boundary")]

    operations = [
        migrations.RunSQL(AUDIT_FUNCTION_V2, AUDIT_FUNCTION_SQL),
        migrations.RunSQL(*FEATURE_TRIGGER),
    ]

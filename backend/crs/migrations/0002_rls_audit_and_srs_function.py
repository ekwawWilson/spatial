"""Row-level security, audit triggers, and the function that registers custom
systems in PostGIS spatial_ref_sys (which the app role can't write directly)."""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

REGISTER_SRS = (
    """
CREATE OR REPLACE FUNCTION app_register_srs(p_srid integer, p_srtext text, p_proj4 text)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS
$$
BEGIN
    IF p_srid < 910000 OR p_srid > 998999 THEN
        RAISE EXCEPTION 'custom SRIDs must be between 910000 and 998999, got %', p_srid;
    END IF;
    INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, srtext, proj4text)
    VALUES (p_srid, 'SPATIAL', p_srid, p_srtext, p_proj4);
END
$$;
""",
    "DROP FUNCTION IF EXISTS app_register_srs(integer, text, text);",
)

# Global systems (district_id NULL) are visible to everyone and writable only by
# system admins; a district's own systems follow the usual tenant rule.
COORDINATE_SYSTEM_RLS = (
    """
ALTER TABLE crs_coordinatesystem ENABLE ROW LEVEL SECURITY;
CREATE POLICY crs_select ON crs_coordinatesystem FOR SELECT USING (
    district_id IS NULL OR district_id = app_current_district() OR app_is_system_admin());
CREATE POLICY crs_insert ON crs_coordinatesystem FOR INSERT WITH CHECK (
    app_is_system_admin() OR (district_id IS NOT NULL AND district_id = app_current_district()));
CREATE POLICY crs_update ON crs_coordinatesystem FOR UPDATE
    USING (app_is_system_admin() OR (district_id IS NOT NULL AND district_id = app_current_district()))
    WITH CHECK (app_is_system_admin() OR (district_id IS NOT NULL AND district_id = app_current_district()));
CREATE POLICY crs_delete ON crs_coordinatesystem FOR DELETE USING (app_is_system_admin());
""",
    """
DROP POLICY IF EXISTS crs_delete ON crs_coordinatesystem;
DROP POLICY IF EXISTS crs_update ON crs_coordinatesystem;
DROP POLICY IF EXISTS crs_insert ON crs_coordinatesystem;
DROP POLICY IF EXISTS crs_select ON crs_coordinatesystem;
ALTER TABLE crs_coordinatesystem DISABLE ROW LEVEL SECURITY;
""",
)

AUDITED = [
    "crs_coordinatesystem",
    "crs_systemcrssettings",
    "crs_districtcrssettings",
    "crs_usercrspreference",
    "crs_preferredtransformation",
]


def _ops() -> list[migrations.RunSQL]:
    ops = [migrations.RunSQL(*REGISTER_SRS), migrations.RunSQL(*COORDINATE_SYSTEM_RLS)]
    ops.append(migrations.RunSQL(*tenant_rls_sql("crs_districtcrssettings")))
    for table in AUDITED:
        ops.append(migrations.RunSQL(*audit_trigger_sql(table)))
    return ops


class Migration(migrations.Migration):
    dependencies = [("crs", "0001_initial"), ("core", "0002_tenancy_and_audit")]

    operations = _ops()

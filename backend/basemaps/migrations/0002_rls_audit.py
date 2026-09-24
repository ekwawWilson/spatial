"""Row-level security (global sources visible to all, writable by system
admins; a district's own follow the tenant rule) and auditing. The encrypted
API key is left out of audit records."""

from django.db import migrations

from core.tenancy import audit_trigger_sql

RLS = (
    """
ALTER TABLE basemaps_basemapsource ENABLE ROW LEVEL SECURITY;
CREATE POLICY basemap_select ON basemaps_basemapsource FOR SELECT USING (
    district_id IS NULL OR district_id = app_current_district() OR app_is_system_admin());
CREATE POLICY basemap_insert ON basemaps_basemapsource FOR INSERT WITH CHECK (
    app_is_system_admin() OR (district_id IS NOT NULL AND district_id = app_current_district()));
CREATE POLICY basemap_update ON basemaps_basemapsource FOR UPDATE
    USING (app_is_system_admin() OR (district_id IS NOT NULL AND district_id = app_current_district()))
    WITH CHECK (app_is_system_admin() OR (district_id IS NOT NULL AND district_id = app_current_district()));
CREATE POLICY basemap_delete ON basemaps_basemapsource FOR DELETE USING (app_is_system_admin());
""",
    """
DROP POLICY IF EXISTS basemap_delete ON basemaps_basemapsource;
DROP POLICY IF EXISTS basemap_update ON basemaps_basemapsource;
DROP POLICY IF EXISTS basemap_insert ON basemaps_basemapsource;
DROP POLICY IF EXISTS basemap_select ON basemaps_basemapsource;
ALTER TABLE basemaps_basemapsource DISABLE ROW LEVEL SECURITY;
""",
)


class Migration(migrations.Migration):
    dependencies = [("basemaps", "0001_initial")]

    operations = [
        migrations.RunSQL(*RLS),
        migrations.RunSQL(*audit_trigger_sql("basemaps_basemapsource", ("api_key_encrypted",))),
    ]

"""Row-level security and auditing. Templates follow the basemap rule: the
platform default (no district) is visible to everyone and changed only by
system admins; a district's own follows the tenant rule. Template items
inherit their template's visibility."""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

TEMPLATE_WRITE = "app_is_system_admin() OR (district_id IS NOT NULL AND district_id = app_current_district())"
ITEM_TEMPLATE_WRITE = (
    "EXISTS (SELECT 1 FROM readiness_template t WHERE t.id = template_id AND"
    " (app_is_system_admin() OR (t.district_id IS NOT NULL AND t.district_id = app_current_district())))"
)

TEMPLATES = (
    f"""
ALTER TABLE readiness_template ENABLE ROW LEVEL SECURITY;
CREATE POLICY template_select ON readiness_template FOR SELECT USING (
    district_id IS NULL OR district_id = app_current_district() OR app_is_system_admin());
CREATE POLICY template_insert ON readiness_template FOR INSERT WITH CHECK ({TEMPLATE_WRITE});
CREATE POLICY template_update ON readiness_template FOR UPDATE
    USING ({TEMPLATE_WRITE}) WITH CHECK ({TEMPLATE_WRITE});
CREATE POLICY template_delete ON readiness_template FOR DELETE USING ({TEMPLATE_WRITE});

ALTER TABLE readiness_templateitem ENABLE ROW LEVEL SECURITY;
CREATE POLICY templateitem_select ON readiness_templateitem FOR SELECT USING (
    EXISTS (SELECT 1 FROM readiness_template t WHERE t.id = template_id));
CREATE POLICY templateitem_insert ON readiness_templateitem FOR INSERT WITH CHECK ({ITEM_TEMPLATE_WRITE});
CREATE POLICY templateitem_update ON readiness_templateitem FOR UPDATE
    USING ({ITEM_TEMPLATE_WRITE}) WITH CHECK ({ITEM_TEMPLATE_WRITE});
CREATE POLICY templateitem_delete ON readiness_templateitem FOR DELETE USING ({ITEM_TEMPLATE_WRITE});
""",
    """
DROP POLICY IF EXISTS templateitem_delete ON readiness_templateitem;
DROP POLICY IF EXISTS templateitem_update ON readiness_templateitem;
DROP POLICY IF EXISTS templateitem_insert ON readiness_templateitem;
DROP POLICY IF EXISTS templateitem_select ON readiness_templateitem;
ALTER TABLE readiness_templateitem DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS template_delete ON readiness_template;
DROP POLICY IF EXISTS template_update ON readiness_template;
DROP POLICY IF EXISTS template_insert ON readiness_template;
DROP POLICY IF EXISTS template_select ON readiness_template;
ALTER TABLE readiness_template DISABLE ROW LEVEL SECURITY;
""",
)


class Migration(migrations.Migration):
    dependencies = [("readiness", "0001_initial")]

    operations = [
        migrations.RunSQL(*TEMPLATES),
        migrations.RunSQL(*tenant_rls_sql("readiness_item")),
        migrations.RunSQL(*tenant_rls_sql("readiness_attachment")),
        migrations.RunSQL(*audit_trigger_sql("readiness_template")),
        migrations.RunSQL(*audit_trigger_sql("readiness_templateitem")),
        migrations.RunSQL(*audit_trigger_sql("readiness_item")),
        migrations.RunSQL(*audit_trigger_sql("readiness_attachment")),
    ]

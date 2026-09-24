"""Native geometry column, its safety triggers, row-level security, auditing.

geom_native is deliberately unconstrained (no SRID typmod) and not a Django
field: each layer has its own CRS, and only projects.geometry writes it, with
explicit SQL. Triggers make a mismatch between a feature's SRID and its layer's
CRS an error rather than something to "fix" silently.
"""

from django.db import migrations

from core.tenancy import audit_trigger_sql, tenant_rls_sql

NATIVE_GEOMETRY = (
    """
ALTER TABLE projects_feature ADD COLUMN geom_native geometry;
CREATE INDEX projects_feature_geom_native_gist ON projects_feature USING gist (geom_native);

CREATE OR REPLACE FUNCTION app_feature_check_srid() RETURNS trigger LANGUAGE plpgsql AS
$$
DECLARE
    layer_srid integer;
BEGIN
    IF NEW.geom_native IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT c.srid INTO layer_srid
        FROM projects_layer l JOIN crs_coordinatesystem c ON c.id = l.crs_id
        WHERE l.id = NEW.layer_id;
    IF ST_SRID(NEW.geom_native) IS DISTINCT FROM layer_srid THEN
        RAISE EXCEPTION 'feature SRID % does not match its layer''s SRID %',
            ST_SRID(NEW.geom_native), layer_srid
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER projects_feature_check_srid
    BEFORE INSERT OR UPDATE OF geom_native, layer_id ON projects_feature
    FOR EACH ROW EXECUTE FUNCTION app_feature_check_srid();

CREATE OR REPLACE FUNCTION app_layer_lock_crs() RETURNS trigger LANGUAGE plpgsql AS
$$
BEGIN
    IF NEW.crs_id IS DISTINCT FROM OLD.crs_id
       AND EXISTS (SELECT 1 FROM projects_feature WHERE layer_id = OLD.id) THEN
        RAISE EXCEPTION 'a layer''s CRS cannot change once it has features'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER projects_layer_lock_crs
    BEFORE UPDATE OF crs_id ON projects_layer
    FOR EACH ROW EXECUTE FUNCTION app_layer_lock_crs();
""",
    """
DROP TRIGGER IF EXISTS projects_layer_lock_crs ON projects_layer;
DROP FUNCTION IF EXISTS app_layer_lock_crs();
DROP TRIGGER IF EXISTS projects_feature_check_srid ON projects_feature;
DROP FUNCTION IF EXISTS app_feature_check_srid();
DROP INDEX IF EXISTS projects_feature_geom_native_gist;
ALTER TABLE projects_feature DROP COLUMN IF EXISTS geom_native;
""",
)

TENANT_TABLES = ["projects_planproject", "projects_layer", "projects_feature"]

# geom_4326 is derived from geom_native, so auditing it would only duplicate data.
AUDITED = [
    ("projects_planproject", ()),
    ("projects_layer", ()),
    ("projects_feature", ("geom_4326",)),
]


def _ops() -> list[migrations.RunSQL]:
    ops = [migrations.RunSQL(*NATIVE_GEOMETRY)]
    for table in TENANT_TABLES:
        ops.append(migrations.RunSQL(*tenant_rls_sql(table)))
    for table, exclude in AUDITED:
        ops.append(migrations.RunSQL(*audit_trigger_sql(table, exclude)))
    return ops


class Migration(migrations.Migration):
    dependencies = [("projects", "0001_initial")]

    operations = _ops()

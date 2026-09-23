import pytest
from django.conf import settings
from django.db import connection


@pytest.mark.django_db
def test_postgis_is_installed():
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'postgis'")
        assert cursor.fetchone() is not None


@pytest.mark.django_db
def test_postgis_knows_the_ghana_crs_used_as_default():
    code = int(settings.INITIAL_DEFAULT_CRS.split(":")[1])
    with connection.cursor() as cursor:
        cursor.execute("SELECT srtext FROM spatial_ref_sys WHERE srid = %s", [code])
        row = cursor.fetchone()
    assert row is not None and "Ghana" in row[0]


@pytest.mark.django_db
def test_app_role_cannot_bypass_row_level_security():
    # Superusers and BYPASSRLS roles ignore row-level security, so the role the
    # running app uses must have neither (Phase 1 depends on this).
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
            [settings.APP_DB_USER],
        )
        row = cursor.fetchone()
    assert row is not None, "app role missing: check db/init/01-roles.sh ran"
    assert row == (False, False)

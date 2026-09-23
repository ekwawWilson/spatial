import pytest
from django.core.management import call_command
from django.db import connection


@pytest.mark.django_db(transaction=True)
def test_core_migrations_reverse_cleanly_and_reapply():
    call_command("migrate", "core", "zero", verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('core_membership'), to_regprocedure('app_audit()')")
        assert cursor.fetchone() == (None, None)
    call_command("migrate", verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'core_membership'")
        assert cursor.fetchone() == (True,)


def test_no_model_changes_without_migrations():
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)

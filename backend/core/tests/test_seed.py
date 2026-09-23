import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from core.models import District, Membership, Role, User

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=True)
def test_seed_demo_is_idempotent():
    call_command("seed_demo", verbosity=0)
    call_command("seed_demo", verbosity=0)
    assert set(District.objects.values_list("code", flat=True)) == {"SMA", "ODA"}
    assert User.objects.filter(email__endswith="@example.test").count() == 6
    sma_roles = set(Membership.objects.filter(district__code="SMA").values_list("role", flat=True))
    assert sma_roles == set(Role)
    assert User.objects.get(email="admin@example.test").is_system_admin


@override_settings(DEBUG=False)
def test_seed_demo_refuses_without_debug():
    with pytest.raises(CommandError):
        call_command("seed_demo")

"""District isolation, enforced by PostgreSQL row-level security.

The database-level tests switch to the app role themselves (tenant_context), so
they show the policies hold even for code that forgets to filter by district.
"""

import pytest
from django.conf import settings
from django.db import DatabaseError, connection
from django.urls import reverse

from core.models import AuditLog, Membership, Role
from core.tenancy import tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_districts(make_member, district_a, district_b):
    return {
        "a_admin": make_member(district_a, Role.DISTRICT_ADMIN),
        "a_viewer": make_member(district_a, Role.VIEWER),
        "b_admin": make_member(district_b, Role.DISTRICT_ADMIN),
    }


def test_rows_are_limited_to_the_current_district(two_districts, district_a, district_b):
    with tenant_context(district_a.id):
        assert set(Membership.objects.values_list("district_id", flat=True)) == {district_a.id}
    with tenant_context(district_b.id):
        assert set(Membership.objects.values_list("district_id", flat=True)) == {district_b.id}


def test_no_district_context_means_no_rows(two_districts):
    with tenant_context(None):
        assert Membership.objects.count() == 0


def test_user_sees_own_memberships_without_a_district(two_districts, district_a):
    user = two_districts["a_viewer"]
    with tenant_context(None, user_id=user.id):
        assert list(Membership.objects.values_list("user_id", flat=True)) == [user.id]


def test_system_admin_sees_every_district(two_districts):
    with tenant_context(None, is_system_admin=True):
        assert Membership.objects.count() == 3


def test_cannot_write_into_another_district(two_districts, district_a, district_b):
    with pytest.raises(DatabaseError, match="row-level security"):
        with tenant_context(district_a.id):
            Membership.objects.create(
                user=two_districts["a_viewer"], district=district_b, role=Role.VIEWER
            )


def test_cannot_move_a_row_to_another_district(two_districts, district_a, district_b):
    membership = Membership.objects.get(user=two_districts["a_viewer"])
    with pytest.raises(DatabaseError, match="row-level security"):
        with tenant_context(district_a.id):
            Membership.objects.filter(pk=membership.pk).update(district=district_b)


def test_updates_to_other_districts_silently_match_nothing(two_districts, district_a):
    b_membership = Membership.objects.get(user=two_districts["b_admin"])
    with tenant_context(district_a.id):
        assert Membership.objects.filter(pk=b_membership.pk).update(role=Role.VIEWER) == 0
    b_membership.refresh_from_db()
    assert b_membership.role == Role.DISTRICT_ADMIN


def test_app_role_cannot_write_the_audit_log(district_a):
    with pytest.raises(DatabaseError, match="permission denied"):
        with tenant_context(district_a.id, is_system_admin=True):
            AuditLog.objects.filter(district_id=district_a.id).delete()


def current_db_user() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        return str(cursor.fetchone()[0])


def test_tenant_context_switches_to_the_app_role_and_back(district_a):
    owner = current_db_user()
    assert owner != settings.APP_DB_USER
    with tenant_context(district_a.id):
        assert current_db_user() == settings.APP_DB_USER
    assert current_db_user() == owner


def test_api_requests_leave_the_connection_as_the_owner(api, two_districts, district_a):
    # ResetDbContextMiddleware: without it, test code after a request would
    # silently keep running as the app role.
    owner = current_db_user()
    api(two_districts["a_admin"], district_a).get(reverse("membership-list"))
    assert current_db_user() == owner


# --- Through the API ------------------------------------------------------------


def test_api_lists_only_the_requested_district(api, two_districts, district_a):
    response = api(two_districts["a_admin"], district_a).get(reverse("membership-list"))
    assert response.status_code == 200
    emails = {m["user"]["email"] for m in response.json()["results"]}
    assert emails == {two_districts["a_admin"].email, two_districts["a_viewer"].email}


def test_api_refuses_a_district_the_user_does_not_belong_to(api, two_districts, district_b):
    response = api(two_districts["a_admin"], district_b).get(reverse("membership-list"))
    assert response.status_code == 403
    assert "not a member" in response.json()["detail"]


def test_api_cannot_reach_another_districts_row_by_id(api, two_districts, district_a):
    b_membership = Membership.objects.get(user=two_districts["b_admin"])
    client = api(two_districts["a_admin"], district_a)
    url = reverse("membership-detail", args=[b_membership.pk])
    assert client.get(url).status_code == 404
    assert client.patch(url, {"role": "viewer"}, format="json").status_code == 404


def test_deactivated_membership_loses_access(api, two_districts, district_a):
    viewer = two_districts["a_viewer"]
    Membership.objects.filter(user=viewer).update(is_active=False)
    response = api(viewer, district_a).get(reverse("district-list"))
    assert response.status_code == 403


def test_district_list_shows_only_own_districts(api, two_districts, district_a, system_admin):
    mine = api(two_districts["a_viewer"]).get(reverse("district-list")).json()
    assert [d["code"] for d in mine] == ["DA"]
    everything = api(system_admin).get(reverse("district-list")).json()
    assert {d["code"] for d in everything} == {"DA", "DB"}


def test_system_admin_may_act_in_any_district(api, two_districts, system_admin, district_b):
    response = api(system_admin, district_b).get(reverse("membership-list"))
    assert response.status_code == 200
    assert response.json()["count"] == 1

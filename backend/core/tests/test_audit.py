from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog, Membership, Role, User

pytestmark = pytest.mark.django_db


def entries(table, row_id):
    return list(AuditLog.objects.filter(table_name=table, row_id=str(row_id)).order_by("id"))


def test_api_change_is_attributed_to_the_actor_and_district(api, members_a, district_a):
    admin = members_a[Role.DISTRICT_ADMIN]
    viewer_membership = Membership.objects.get(user=members_a[Role.VIEWER])
    response = api(admin, district_a).patch(
        reverse("membership-detail", args=[viewer_membership.pk]),
        {"role": "planner"},
        format="json",
    )
    assert response.status_code == 200, response.data

    update = entries("core_membership", viewer_membership.pk)[-1]
    assert update.action == "UPDATE"
    assert update.user_id == admin.id
    assert update.district_id == district_a.id
    assert update.before["role"] == "viewer" and update.after["role"] == "planner"
    assert update.changed_fields() == ["role"]


def test_insert_and_delete_are_recorded(region):
    from core.models import District

    district = District.objects.create(region=region, name="Temp", code="TMP", kind="district")
    pk = district.pk
    district.delete()
    actions = [e.action for e in entries("core_district", pk)]
    assert actions == ["INSERT", "DELETE"]
    assert entries("core_district", pk)[-1].after is None


def test_bulk_updates_are_recorded_row_by_row(members_a, district_a):
    count = Membership.objects.filter(district=district_a).update(is_active=False)
    updates = AuditLog.objects.filter(table_name="core_membership", action="UPDATE")
    assert updates.count() == count == len(Role)


def test_password_hashes_never_reach_the_audit_log(make_user):
    user = make_user("kofi@example.test")
    user.set_password("Another-Passw0rd-1")
    user.save()
    for entry in entries("core_user", user.pk):
        assert "password" not in (entry.before or {})
        assert "password" not in (entry.after or {})


def test_audit_endpoint_shows_only_the_current_district(
    api, members_a, district_a, make_member, district_b
):
    make_member(district_b, Role.VIEWER)  # an event in district B
    response = api(members_a[Role.DISTRICT_ADMIN], district_a).get(reverse("audit-list"))
    assert response.status_code == 200
    results = response.json()["results"]
    assert results and {r["district_id"] for r in results} == {district_a.id}


def test_audit_endpoint_filters_and_names_the_actor(api, members_a, district_a):
    admin = members_a[Role.DISTRICT_ADMIN]
    client = api(admin, district_a)
    client.post(
        reverse("membership-list"), {"email": "new@example.test", "role": "viewer"}, format="json"
    )
    response = client.get(
        reverse("audit-list"), {"table": "core_membership", "action": "INSERT", "user_id": admin.id}
    )
    [entry] = response.json()["results"]
    assert entry["user_email"] == admin.email
    assert entry["after"]["role"] == "viewer"


def test_audit_endpoint_rejects_bad_filters(api, members_a, district_a):
    client = api(members_a[Role.DISTRICT_ADMIN], district_a)
    assert client.get(reverse("audit-list"), {"since": "yesterday"}).status_code == 400
    assert client.get(reverse("audit-list"), {"user_id": "abc"}).status_code == 400


# --- Membership rules --------------------------------------------------------------


def test_adding_an_unknown_email_creates_and_invites_the_user(api, members_a, district_a):
    response = api(members_a[Role.DISTRICT_ADMIN], district_a).post(
        reverse("membership-list"),
        {"email": "New.Person@Example.test", "role": "field_officer", "first_name": "Abena"},
        format="json",
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(email="new.person@example.test")
    assert not user.has_usable_password()
    [message] = mail.outbox
    assert message.to == [user.email] and "District A" in message.subject


def test_adding_an_existing_member_is_rejected(api, members_a, district_a):
    response = api(members_a[Role.DISTRICT_ADMIN], district_a).post(
        reverse("membership-list"),
        {"email": members_a[Role.VIEWER].email, "role": "planner"},
        format="json",
    )
    assert response.status_code == 400


def test_re_adding_a_former_member_reactivates_them(api, members_a, district_a):
    viewer = members_a[Role.VIEWER]
    Membership.objects.filter(user=viewer).update(is_active=False)
    response = api(members_a[Role.DISTRICT_ADMIN], district_a).post(
        reverse("membership-list"), {"email": viewer.email, "role": "planner"}, format="json"
    )
    assert response.status_code == 201
    membership = Membership.objects.get(user=viewer)
    assert membership.is_active and membership.role == Role.PLANNER
    assert mail.outbox == []  # existing account: no invitation


def test_last_district_admin_cannot_be_removed_or_demoted(api, members_a, district_a):
    admin = members_a[Role.DISTRICT_ADMIN]
    own = Membership.objects.get(user=admin)
    client = api(admin, district_a)
    url = reverse("membership-detail", args=[own.pk])
    assert client.patch(url, {"role": "viewer"}, format="json").status_code == 400
    assert client.delete(url).status_code == 400
    own.refresh_from_db()
    assert own.is_active and own.role == Role.DISTRICT_ADMIN


def test_admin_can_step_down_when_another_admin_exists(api, members_a, district_a, make_member):
    make_member(district_a, Role.DISTRICT_ADMIN, email="second.admin@example.test")
    admin = members_a[Role.DISTRICT_ADMIN]
    own = Membership.objects.get(user=admin)
    response = api(admin, district_a).delete(reverse("membership-detail", args=[own.pk]))
    assert response.status_code == 204
    own.refresh_from_db()
    assert own.is_active is False  # deactivated, not deleted


def test_system_admin_cannot_lock_themselves_out(api, system_admin):
    url = reverse("user-detail", args=[system_admin.pk])
    client = api(system_admin)
    assert client.patch(url, {"is_active": False}, format="json").status_code == 400
    assert client.patch(url, {"is_system_admin": False}, format="json").status_code == 400


def test_system_admin_can_unlock_a_user(api, system_admin, make_user):
    user = make_user("locked@example.test")
    user.locked_until = timezone.now() + timedelta(hours=1)
    user.save()
    response = api(system_admin).post(reverse("user-unlock", args=[user.pk]))
    assert response.status_code == 200 and response.json()["is_locked"] is False

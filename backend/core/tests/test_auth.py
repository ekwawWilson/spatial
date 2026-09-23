import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from conftest import PASSWORD
from core.models import Role, User
from core.views_auth import LOGIN_FAILED

pytestmark = pytest.mark.django_db


def login(api, email, password=PASSWORD):
    return api().post(reverse("login"), {"email": email, "password": password}, format="json")


def test_login_returns_tokens_and_memberships(api, make_member, district_a):
    make_member(district_a, Role.PLANNER, email="kofi@example.test")
    response = login(api, "Kofi@Example.test")  # email is case-insensitive
    assert response.status_code == 200, response.data
    body = response.json()
    assert body["access"] and body["refresh"]
    [membership] = body["user"]["memberships"]
    assert membership["district"]["code"] == "DA"
    assert membership["role"] == "planner"
    assert "district.view" in membership["permissions"]


@pytest.mark.parametrize("email", ["kofi@example.test", "nobody@example.test"])
def test_failed_login_gives_the_same_answer_for_unknown_and_wrong_password(api, make_user, email):
    make_user("kofi@example.test")
    response = login(api, email, "wrong-password")
    assert response.status_code == 401
    assert response.json()["detail"] == LOGIN_FAILED


def test_account_locks_after_threshold_even_with_correct_password(api, make_user):
    user = make_user("kofi@example.test")
    for _ in range(settings.AUTH_LOCKOUT_THRESHOLD):
        assert login(api, user.email, "wrong-password").status_code == 401
    user.refresh_from_db()
    assert user.locked_until is not None and user.locked_until > timezone.now()

    assert login(api, user.email).status_code == 401


def test_lock_expires(api, make_user):
    user = make_user("kofi@example.test")
    user.locked_until = timezone.now() - timedelta(seconds=1)
    user.save()
    assert login(api, user.email).status_code == 200
    user.refresh_from_db()
    assert user.locked_until is None


def test_successful_login_resets_failure_count(api, make_user):
    user = make_user("kofi@example.test")
    for _ in range(settings.AUTH_LOCKOUT_THRESHOLD - 1):
        login(api, user.email, "wrong-password")
    assert login(api, user.email).status_code == 200
    user.refresh_from_db()
    assert user.failed_login_count == 0
    assert user.last_login is not None


def test_inactive_user_cannot_log_in(api, make_user):
    make_user("gone@example.test", is_active=False)
    assert login(api, "gone@example.test").status_code == 401


def test_refresh_rotates_and_old_refresh_token_stops_working(api, make_user):
    make_user("kofi@example.test")
    refresh = login(api, "kofi@example.test").json()["refresh"]
    first = api().post(reverse("token-refresh"), {"refresh": refresh}, format="json")
    assert first.status_code == 200 and first.json()["refresh"] != refresh
    again = api().post(reverse("token-refresh"), {"refresh": refresh}, format="json")
    assert again.status_code == 401


def test_logout_revokes_refresh_token(api, make_user):
    make_user("kofi@example.test")
    refresh = login(api, "kofi@example.test").json()["refresh"]
    assert api().post(reverse("logout"), {"refresh": refresh}, format="json").status_code == 204
    after = api().post(reverse("token-refresh"), {"refresh": refresh}, format="json")
    assert after.status_code == 401


def test_me_requires_authentication(api, make_user):
    assert api().get(reverse("me")).status_code == 401
    user = make_user("kofi@example.test")
    assert api(user).get(reverse("me")).json()["email"] == "kofi@example.test"


def reset_link_params(message) -> tuple[str, str]:
    match = re.search(r"uid=([^&\s]+)&token=([^\s]+)", message.body)
    assert match, message.body
    return match.group(1), match.group(2)


def test_password_reset_flow_sets_password_and_unlocks(api, make_user):
    user = make_user("kofi@example.test")
    user.locked_until = timezone.now() + timedelta(hours=1)
    user.save()

    response = api().post(reverse("password-reset"), {"email": user.email}, format="json")
    assert response.status_code == 204
    [message] = mail.outbox
    assert message.to == [user.email]
    assert message.body.count(settings.WEB_APP_URL) == 1
    uid, token = reset_link_params(message)

    new = "A-Brand-New-Passw0rd"
    confirm = api().post(
        reverse("password-reset-confirm"),
        {"uid": uid, "token": token, "new_password": new},
        format="json",
    )
    assert confirm.status_code == 204, confirm.data
    assert login(api, user.email, new).status_code == 200

    reused = api().post(
        reverse("password-reset-confirm"),
        {"uid": uid, "token": token, "new_password": "Another-Passw0rd-1"},
        format="json",
    )
    assert reused.status_code == 400  # token is single-use (password hash changed)


def test_password_reset_for_unknown_email_is_silent(api):
    response = api().post(reverse("password-reset"), {"email": "x@example.test"}, format="json")
    assert response.status_code == 204
    assert mail.outbox == []


def test_password_reset_rejects_weak_password(api, make_user):
    user = make_user("kofi@example.test")
    api().post(reverse("password-reset"), {"email": user.email}, format="json")
    uid, token = reset_link_params(mail.outbox[0])
    response = api().post(
        reverse("password-reset-confirm"),
        {"uid": uid, "token": token, "new_password": "12345678"},
        format="json",
    )
    assert response.status_code == 400
    assert "new_password" in response.json()


def test_change_password_checks_current_and_revokes_sessions(api, make_user):
    user = make_user("kofi@example.test")
    refresh = login(api, user.email).json()["refresh"]
    client = api(user)
    wrong = client.post(
        reverse("password-change"),
        {"current_password": "nope", "new_password": "A-Brand-New-Passw0rd"},
        format="json",
    )
    assert wrong.status_code == 400
    ok = client.post(
        reverse("password-change"),
        {"current_password": PASSWORD, "new_password": "A-Brand-New-Passw0rd"},
        format="json",
    )
    assert ok.status_code == 204
    after = api().post(reverse("token-refresh"), {"refresh": refresh}, format="json")
    assert after.status_code == 401
    assert User.objects.get(pk=user.pk).check_password("A-Brand-New-Passw0rd")

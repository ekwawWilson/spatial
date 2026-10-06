"""Phase 13: rate limits."""

import pytest
from django.core.cache import cache
from django.urls import reverse

from core.models import Role

pytestmark = pytest.mark.django_db


@pytest.fixture
def limits(settings):
    cache.clear()
    settings.API_THROTTLING = True
    settings.API_THROTTLE_RATES = {
        "anon": "50/min",
        "user": "5/min",
        "login": "3/min",
        "upload": "1/min",
    }
    yield settings
    cache.clear()


def test_sign_in_attempts_are_limited_per_address(api, limits):
    client = api()
    body = {"email": "nobody@example.test", "password": "wrong"}
    statuses = [client.post(reverse("login"), body, format="json").status_code for _ in range(5)]
    assert statuses == [401, 401, 401, 429, 429]
    blocked = client.post(reverse("login"), body, format="json")
    assert int(blocked["Retry-After"]) > 0
    # Another address isn't affected.
    elsewhere = client.post(reverse("login"), body, format="json", REMOTE_ADDR="203.0.113.9")
    assert elsewhere.status_code == 401


def test_requests_are_limited_per_user(api, members_a, district_a, limits):
    planner = api(members_a[Role.PLANNER], district_a)
    viewer = api(members_a[Role.VIEWER], district_a)
    url = reverse("project-list")
    assert [planner.get(url).status_code for _ in range(7)] == [200] * 5 + [429] * 2
    assert viewer.get(url).status_code == 200  # counted separately


def test_uploads_have_their_own_tighter_limit(api, members_a, district_a, limits, tmp_path):
    limits.API_THROTTLE_RATES = {**limits.API_THROTTLE_RATES, "user": "100/min"}
    planner = api(members_a[Role.PLANNER], district_a)
    project = planner.post(reverse("project-list"), {"name": "Limits"}, format="json").json()
    path = tmp_path / "a.geojson"
    path.write_text('{"type": "FeatureCollection", "features": []}')

    def upload():
        with open(path, "rb") as fh:
            return planner.post(
                reverse("datajob-upload"),
                {"project": project["id"], "file": fh},
                format="multipart",
            ).status_code

    assert upload() != 429
    assert upload() == 429
    assert planner.get(reverse("project-list")).status_code == 200  # ordinary requests carry on


def test_limits_can_be_switched_off(api, limits):
    limits.API_THROTTLING = False
    client = api()
    body = {"email": "nobody@example.test", "password": "wrong"}
    assert {client.post(reverse("login"), body, format="json").status_code for _ in range(6)} == {
        401
    }

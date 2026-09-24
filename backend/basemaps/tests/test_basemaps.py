"""Phase 4: basemaps."""

import io
import json
import urllib.error
from email.message import Message
from unittest import mock

import pytest
from django.core.cache import cache
from django.urls import reverse

from basemaps import services
from basemaps.models import BasemapSource
from basemaps.presets import PRESETS
from core.models import AuditLog, Role

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def admin_a(api, members_a, district_a):
    return api(members_a[Role.DISTRICT_ADMIN], district_a)


def add_preset(client, preset, **extra):
    return client.post(reverse("basemap-presets"), {"preset": preset, **extra}, format="json")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def google_ok(request, timeout):
    assert "key=GOOD-KEY" in request.full_url
    assert json.loads(request.data)["mapType"] in ("roadmap", "satellite")
    return FakeResponse(json.dumps({"session": "SESSION-1", "expiry": "9999999999"}).encode())


def google_rejects(request, timeout):
    body = io.BytesIO(json.dumps({"error": {"message": "API key not valid."}}).encode())
    raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", Message(), body)


# --- Presets and offline rules --------------------------------------------------------


def test_free_presets_are_available_from_the_start(admin_a):
    names = {b["preset"] for b in admin_a.get(reverse("basemap-list")).json()}
    assert {"osm", "esri_imagery"} <= names


@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_no_provider_preset_may_be_cached_offline(admin_a, preset):
    created = add_preset(admin_a, preset, api_key="K" if PRESETS[preset]["requires_key"] else "")
    assert created.status_code == 201, created.data
    source = BasemapSource.objects.get(pk=created.json()["id"])
    assert source.offline_cache_allowed is False
    with pytest.raises(services.OfflineCachingNotAllowed):
        services.assert_offline_allowed(source)


def test_an_own_licensed_source_can_be_marked_cacheable(admin_a):
    created = admin_a.post(
        reverse("basemap-list"),
        {
            "name": "District drone mosaic",
            "kind": "xyz",
            "url": "https://tiles.example.gov.gh/drone/{z}/{x}/{y}.png",
            "offline_cache_allowed": True,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    services.assert_offline_allowed(BasemapSource.objects.get(pk=created.json()["id"]))


@pytest.mark.parametrize(
    "body",
    [
        {"name": "No placeholders", "kind": "xyz", "url": "https://example.com/tiles.png"},
        {"name": "Plain http", "kind": "xyz", "url": "http://example.com/{z}/{x}/{y}.png"},
        {
            "name": "Bad zooms",
            "kind": "xyz",
            "url": "https://e.com/{z}/{x}/{y}",
            "min_zoom": 12,
            "max_zoom": 3,
        },
    ],
)
def test_bad_sources_are_rejected(admin_a, body):
    assert admin_a.post(reverse("basemap-list"), body, format="json").status_code == 400


# --- Keys --------------------------------------------------------------------------------


def test_keys_are_encrypted_at_rest_and_never_returned(admin_a):
    created = add_preset(admin_a, "google_satellite", api_key="GOOD-KEY")
    body = created.json()
    assert "api_key" not in body and "api_key_encrypted" not in body
    assert body["has_key"] is True
    source = BasemapSource.objects.get(pk=body["id"])
    assert source.api_key_encrypted and "GOOD-KEY" not in source.api_key_encrypted
    assert services.api_key(source) == "GOOD-KEY"
    listed = admin_a.get(reverse("basemap-list")).content.decode()
    assert "GOOD-KEY" not in listed and source.api_key_encrypted not in listed
    for entry in AuditLog.objects.filter(table_name="basemaps_basemapsource"):
        assert "api_key_encrypted" not in (entry.after or {})


def test_missing_key_gives_a_plain_message(admin_a):
    source_id = add_preset(admin_a, "google_roadmap").json()["id"]
    response = admin_a.get(reverse("basemap-client-config", args=[source_id]))
    assert response.status_code == 400
    assert "needs an API key" in json.dumps(response.json())


def test_google_session_is_created_server_side(admin_a):
    source_id = add_preset(admin_a, "google_roadmap", api_key="GOOD-KEY").json()["id"]
    with mock.patch("urllib.request.urlopen", side_effect=google_ok) as urlopen:
        first = admin_a.get(reverse("basemap-client-config", args=[source_id])).json()
        second = admin_a.get(reverse("basemap-client-config", args=[source_id])).json()
    assert first["kind"] == "xyz"
    assert "session=SESSION-1" in first["url"] and "{z}/{x}/{y}" in first["url"]
    assert first == second
    assert urlopen.call_count == 1  # session cached until it expires


def test_rejected_google_key_gives_a_plain_message(admin_a):
    source_id = add_preset(admin_a, "google_roadmap", api_key="BAD-KEY").json()["id"]
    with mock.patch("urllib.request.urlopen", side_effect=google_rejects):
        response = admin_a.get(reverse("basemap-client-config", args=[source_id]))
    assert response.status_code == 400
    text = json.dumps(response.json())
    assert "Google rejected the API key" in text and "API key not valid" in text


def test_osm_needs_no_key(admin_a):
    osm = next(b for b in admin_a.get(reverse("basemap-list")).json() if b["preset"] == "osm")
    config = admin_a.get(reverse("basemap-client-config", args=[osm["id"]])).json()
    assert config["url"] == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    assert "OpenStreetMap" in config["attribution"]


def test_clearing_a_key(admin_a):
    source_id = add_preset(admin_a, "bing_aerial", api_key="K").json()["id"]
    response = admin_a.patch(
        reverse("basemap-detail", args=[source_id]), {"api_key": ""}, format="json"
    )
    assert response.json()["has_key"] is False


# --- Tenancy and roles -------------------------------------------------------------------


def test_district_sources_are_private(admin_a, api, make_member, district_b):
    created = add_preset(admin_a, "bing_aerial", api_key="K").json()
    assert created["scope"] == "district"
    other = api(make_member(district_b, Role.DISTRICT_ADMIN), district_b)
    assert created["id"] not in {b["id"] for b in other.get(reverse("basemap-list")).json()}


@pytest.mark.parametrize("role", [Role.PLANNER, Role.FIELD_OFFICER, Role.VIEWER])
def test_only_district_admins_manage_district_basemaps(api, members_a, district_a, role):
    client = api(members_a[role], district_a)
    assert client.get(reverse("basemap-list")).status_code == 200
    assert add_preset(client, "osm").status_code == 403


def test_only_system_admins_manage_global_basemaps(admin_a, api, system_admin):
    assert add_preset(admin_a, "osm", scope="global").status_code == 403
    assert add_preset(api(system_admin), "osm", scope="global").status_code == 201
    global_osm = BasemapSource.objects.filter(preset="osm", district__isnull=True).first()
    assert global_osm is not None
    response = admin_a.patch(
        reverse("basemap-detail", args=[global_osm.id]), {"name": "Mine"}, format="json"
    )
    assert response.status_code == 403


def test_adding_a_basemap_never_changes_the_default(admin_a):
    first_before = admin_a.get(reverse("basemap-list")).json()[0]["preset"]
    add_preset(admin_a, "bing_aerial")  # "Bing" sorts before "OpenStreetMap" by name
    listed = admin_a.get(reverse("basemap-list")).json()
    assert listed[0]["preset"] == first_before == "osm"
    assert listed[-1]["preset"] == "bing_aerial"

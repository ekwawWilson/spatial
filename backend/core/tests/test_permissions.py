"""Every role against every Phase 1 endpoint, as the permission matrix says."""

import re

import pytest
from django.conf import settings
from django.urls import reverse

from core.models import Role
from core.permissions import PERMISSIONS

pytestmark = pytest.mark.django_db

ADMIN = Role.DISTRICT_ADMIN
OTHERS = [Role.PLANNER, Role.FIELD_OFFICER, Role.VIEWER]

# (name, method, url name, body, district-scoped)
ENDPOINTS = {
    "list members": ("get", "membership-list", None, True),
    "add member": ("post", "membership-list", {"email": "n@example.test", "role": "viewer"}, True),
    "view audit": ("get", "audit-list", None, True),
    "list districts": ("get", "district-list", None, False),
    "create district": (
        "post",
        "district-list",
        {"name": "X", "code": "X", "kind": "district", "region": "<region>"},
        False,
    ),
    "list users": ("get", "user-list", None, False),
    "create region": ("post", "region-list", {"name": "Volta", "code": "VR"}, False),
    "list regions": ("get", "region-list", None, False),
}

ALLOWED = {
    "list members": {ADMIN},
    "add member": {ADMIN},
    "view audit": {ADMIN},
    "list districts": set(Role),
    "create district": set(),
    "list users": set(),
    "create region": set(),
    "list regions": set(Role),
}


def call(client, method, url_name, body, region=None):
    if body and body.get("region") == "<region>":
        # Anonymous calls are refused before the body is read; any id will do.
        body = {**body, "region": region.id if region else 1}
    return getattr(client, method)(reverse(url_name), body, format="json")


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("endpoint", list(ENDPOINTS))
def test_role_matrix(api, members_a, district_a, region, role, endpoint):
    method, url_name, body, _scoped = ENDPOINTS[endpoint]
    response = call(api(members_a[role], district_a), method, url_name, body, region)
    if role in ALLOWED[endpoint]:
        assert response.status_code in (200, 201), (endpoint, role, response.data)
    else:
        assert response.status_code == 403, (endpoint, role, response.status_code)


@pytest.mark.parametrize("endpoint", list(ENDPOINTS))
def test_system_admin_can_do_everything(api, system_admin, district_a, region, endpoint):
    method, url_name, body, _scoped = ENDPOINTS[endpoint]
    response = call(api(system_admin, district_a), method, url_name, body, region)
    assert response.status_code in (200, 201), (endpoint, response.data)


@pytest.mark.parametrize("endpoint", [e for e, spec in ENDPOINTS.items() if spec[3]])
def test_district_scoped_endpoints_need_a_district(api, members_a, endpoint):
    method, url_name, body, _scoped = ENDPOINTS[endpoint]
    response = call(api(members_a[ADMIN]), method, url_name, body)
    assert response.status_code == 403
    assert "X-District-ID" in response.json()["detail"]


@pytest.mark.parametrize("endpoint", list(ENDPOINTS))
def test_anonymous_is_refused(api, endpoint):
    method, url_name, body, _scoped = ENDPOINTS[endpoint]
    assert call(api(), method, url_name, body).status_code == 401


def test_permissions_doc_matches_code():
    """docs/dev/permissions.md must list exactly the matrix in core/permissions.py."""
    text = (settings.DOCS_DIR / "dev" / "permissions.md").read_text()
    # Only the matrix section: the roles table above it has the same row shape.
    text = text.split("## Permission matrix", 1)[1].split("\n## ", 1)[0]
    documented = {}
    for code, roles in re.findall(r"^\| `([a-z.]+)` \| ([^|]*)\|", text, flags=re.M):
        documented[code] = {r.strip() for r in roles.split(",") if r.strip()}
    in_code = {code: {str(r) for r in roles} for code, roles in PERMISSIONS.items()}
    assert documented == in_code

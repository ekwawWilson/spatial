import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import District, Membership, Region, Role, User

PASSWORD = "Correct-Horse-9-Battery"  # noqa: S105 - test accounts


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(settings.FIXTURES_DIR)


@pytest.fixture(scope="session")
def fixture_manifest(fixtures_dir: Path) -> dict[str, Any]:
    path = fixtures_dir / "generated" / "manifest.json"
    if not path.exists():
        pytest.fail("Fixtures not built. Run `make fixtures`.")
    data: dict[str, Any] = json.loads(path.read_text())
    return data


# --- Tenancy fixtures ---------------------------------------------------------
# Created directly as the owner role (tests' own connection), so row-level
# security doesn't apply to setup. API calls then run as the app role.


@pytest.fixture
def region(db: None) -> Region:
    return Region.objects.create(name="Greater Accra", code="GA")


@pytest.fixture
def district_a(region: Region) -> District:
    return District.objects.create(
        region=region, name="District A", code="DA", kind=District.Kind.MUNICIPAL
    )


@pytest.fixture
def district_b(region: Region) -> District:
    return District.objects.create(
        region=region, name="District B", code="DB", kind=District.Kind.DISTRICT
    )


@pytest.fixture
def make_user(db: None) -> Callable[..., User]:
    def make(email: str, *, system_admin: bool = False, **extra: Any) -> User:
        return User.objects.create_user(
            email=email, password=PASSWORD, is_system_admin=system_admin, **extra
        )

    return make


@pytest.fixture
def make_member(make_user: Callable[..., User]) -> Callable[..., User]:
    def make(district: District, role: Role, email: str | None = None) -> User:
        user = make_user(email or f"{role}.{district.code.lower()}@example.test")
        Membership.objects.create(user=user, district=district, role=role)
        return user

    return make


@pytest.fixture
def system_admin(make_user: Callable[..., User]) -> User:
    return make_user("root@example.test", system_admin=True)


@pytest.fixture
def members_a(make_member: Callable[..., User], district_a: District) -> dict[Role, User]:
    """One user per role in district A."""
    return {role: make_member(district_a, role) for role in Role}


@pytest.fixture
def api() -> Callable[..., APIClient]:
    """API client authenticated with a real JWT, optionally scoped to a district,
    so requests take exactly the production path (authenticator, RLS)."""

    def make(user: User | None = None, district: District | None = None) -> APIClient:
        client = APIClient()
        headers: dict[str, str] = {}
        if user is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {RefreshToken.for_user(user).access_token}"
        if district is not None:
            headers["HTTP_X_DISTRICT_ID"] = str(district.id)
        client.credentials(**headers)
        return client

    return make


@pytest.fixture(autouse=True)
def _celery_runs_inline():
    """Background jobs (imports, exports) run inline in tests."""
    from config.celery import app

    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True


@pytest.fixture(autouse=True)
def _media_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"

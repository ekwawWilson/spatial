"""Role -> permission matrix. The single source of truth for who may do what;
docs/dev/permissions.md mirrors it and a test keeps the two in sync.

System admins (User.is_system_admin) have every permission in every district.
District roles only apply within the district the request is scoped to
(X-District-ID header).
"""

from typing import Any

from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .models import Membership, Role, User

ALL_ROLES = frozenset(Role)

PERMISSIONS: dict[str, frozenset[Role]] = {
    "district.view": ALL_ROLES,
    "membership.view": frozenset({Role.DISTRICT_ADMIN}),
    "membership.manage": frozenset({Role.DISTRICT_ADMIN}),
    "audit.view": frozenset({Role.DISTRICT_ADMIN}),
    "crs.manage": frozenset({Role.DISTRICT_ADMIN}),
    "project.view": ALL_ROLES,
    "project.edit": frozenset({Role.DISTRICT_ADMIN, Role.PLANNER}),
    "layer.edit": frozenset({Role.DISTRICT_ADMIN, Role.PLANNER}),
    "feature.edit": frozenset({Role.DISTRICT_ADMIN, Role.PLANNER}),
    "basemap.manage": frozenset({Role.DISTRICT_ADMIN}),
}


def request_membership(request: Request) -> Membership | None:
    return getattr(request, "membership", None)


def request_district_id(request: Request) -> int | None:
    return getattr(request, "district_id", None)


def require_district_id(request: Request) -> int:
    """The active district; views behind DistrictPermission always have one."""
    district_id = request_district_id(request)
    if district_id is None:
        raise PermissionDenied("Select a district: send its id in the X-District-ID header.")
    return district_id


def request_user(request: Request) -> User:
    user = request.user
    if not isinstance(user, User):
        raise NotAuthenticated()
    return user


def is_system_admin(request: Request) -> bool:
    return bool(request.user and request.user.is_authenticated and request.user.is_system_admin)


def has_permission(request: Request, code: str) -> bool:
    if code not in PERMISSIONS:
        raise KeyError(f"Unknown permission {code!r}")
    if is_system_admin(request):
        return True
    membership = request_membership(request)
    return membership is not None and membership.role in PERMISSIONS[code]


def permissions_for_role(role: str) -> list[str]:
    return sorted(code for code, roles in PERMISSIONS.items() if role in roles)


class IsSystemAdmin(BasePermission):
    message = "Only system administrators can do this."

    def has_permission(self, request: Request, view: Any) -> bool:
        return is_system_admin(request)


class DistrictPermission(BasePermission):
    """Grants access when the request is scoped to a district and the caller's
    role there includes `code`. Subclass via district_permission()."""

    code = ""

    def has_permission(self, request: Request, view: Any) -> bool:
        if request_district_id(request) is None:
            self.message = "Select a district: send its id in the X-District-ID header."
            return False
        self.message = "Your role in this district does not allow this."
        return has_permission(request, self.code)


def district_permission(code: str) -> type[DistrictPermission]:
    if code not in PERMISSIONS:
        raise KeyError(f"Unknown permission {code!r}")
    return type(f"DistrictPermission[{code}]", (DistrictPermission,), {"code": code})

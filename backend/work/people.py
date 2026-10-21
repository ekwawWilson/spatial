"""How an officer is shown on a record; kept apart from services so the
modules' views can use it without importing every other module."""

from typing import Any

from core.models import User


def officer_json(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    name = f"{user.first_name} {user.last_name}".strip()
    return {"id": user.pk, "name": name or user.email}

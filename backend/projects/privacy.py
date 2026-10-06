"""Restricted fields: attributes that hold personal data (ownership, names,
phone numbers) under the Data Protection Act, 2012 (Act 843). A layer marks
them in its schema ("sensitive": true). Roles without the data.sensitive
permission never receive their values, wherever attributes leave the server:
feature details and lists, map tiles, history, the field package and sync."""

from typing import Any

from django.core.exceptions import ValidationError

from core import privacy

from .models import Layer


def sensitive_fields(schema: list[dict[str, Any]]) -> list[str]:
    return [f["name"] for f in schema if isinstance(f, dict) and f.get("sensitive")]


def hidden_fields(layer: Layer) -> list[str]:
    """The fields the current caller may not see (none for those allowed)."""
    return [] if privacy.allowed() else sensitive_fields(layer.schema)


def redact(properties: dict[str, Any] | None, hidden: list[str]) -> dict[str, Any]:
    properties = properties or {}
    if not hidden:
        return properties
    return {key: value for key, value in properties.items() if key not in hidden}


def visible_schema(layer: Layer) -> list[dict[str, Any]]:
    hidden = set(hidden_fields(layer))
    return [f for f in layer.schema if f.get("name") not in hidden]


def check_write(layer: Layer, properties: Any) -> None:
    """Refuses a write to a restricted field by someone who can't see it."""
    if not isinstance(properties, dict):
        return
    touched = sorted(set(properties) & set(hidden_fields(layer)))
    if touched:
        raise ValidationError(
            {name: ["is restricted: your role can't see or change it"] for name in touched}
        )

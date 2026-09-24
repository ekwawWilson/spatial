"""Layer field schemas and feature property validation.

The single source of truth for what a feature's properties may contain: used
by the API, the importer (Phase 5) and field sync (Phase 10). The web and
mobile forms mirror these rules for instant feedback, but the server decides.

A schema is a list of field definitions:
    {"name": "use", "label": "Use", "type": "choice", "required": true,
     "choices": ["residential", "commercial"], "default": "residential"}
"""

import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError

FIELD_TYPES = ("text", "integer", "decimal", "boolean", "date", "choice")
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
MAX_FIELDS = 200
MAX_TEXT = 10_000


def _check_value(field: dict[str, Any], value: Any) -> Any:
    """The value converted to its stored JSON form; ValueError if it doesn't fit."""
    kind = field["type"]
    if kind == "text":
        if not isinstance(value, str):
            raise ValueError("must be text")
        if len(value) > MAX_TEXT:
            raise ValueError(f"must be at most {MAX_TEXT} characters")
        return value
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            if isinstance(value, float) and value.is_integer():
                return int(value)
            raise ValueError("must be a whole number")
        return value
    if kind == "decimal":
        if isinstance(value, bool) or not isinstance(value, int | float):
            if isinstance(value, str):
                try:
                    return float(Decimal(value))
                except InvalidOperation:
                    pass
            raise ValueError("must be a number")
        return float(value)
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value
    if kind == "date":
        if not isinstance(value, str):
            raise ValueError("must be a date (YYYY-MM-DD)")
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("must be a date (YYYY-MM-DD)") from None
    if kind == "choice":
        if value not in field["choices"]:
            raise ValueError(f"must be one of: {', '.join(map(str, field['choices']))}")
        return value
    raise ValueError(f"unknown type {kind}")


def validate_schema(schema: Any) -> list[dict[str, Any]]:
    """Checks and normalises a layer schema; ValidationError lists every problem."""
    if not isinstance(schema, list):
        raise ValidationError("The schema must be a list of fields.")
    if len(schema) > MAX_FIELDS:
        raise ValidationError(f"A layer can have at most {MAX_FIELDS} fields.")
    errors: list[str] = []
    seen: set[str] = set()
    normalised: list[dict[str, Any]] = []
    for i, raw in enumerate(schema, start=1):
        if not isinstance(raw, dict):
            errors.append(f"Field {i}: must be an object.")
            continue
        name = raw.get("name")
        where = f"Field {i} ({name})" if isinstance(name, str) else f"Field {i}"
        if not isinstance(name, str) or not NAME_PATTERN.match(name):
            errors.append(
                f"{where}: name must start with a lowercase letter and use only "
                "lowercase letters, digits and underscores (max 63)."
            )
            continue
        if name in seen:
            errors.append(f"{where}: duplicate name.")
            continue
        seen.add(name)
        kind = raw.get("type")
        if kind not in FIELD_TYPES:
            errors.append(f"{where}: type must be one of {', '.join(FIELD_TYPES)}.")
            continue
        field: dict[str, Any] = {
            "name": name,
            "label": str(raw.get("label") or name.replace("_", " ").capitalize()),
            "type": kind,
            "required": bool(raw.get("required", False)),
        }
        if kind == "choice":
            choices = raw.get("choices")
            if (
                not isinstance(choices, list)
                or not choices
                or len(set(map(str, choices))) != len(choices)
            ):
                errors.append(f"{where}: a choice field needs a list of distinct choices.")
                continue
            field["choices"] = choices
        if raw.get("default") is not None:
            try:
                field["default"] = _check_value(field, raw["default"])
            except ValueError as exc:
                errors.append(f"{where}: default {exc}.")
                continue
        normalised.append(field)
    unknown = [
        f"Field {i}: unknown keys {sorted(set(r) - _KEYS)}."
        for i, r in enumerate(schema, 1)
        if isinstance(r, dict) and set(r) - _KEYS
    ]
    errors.extend(unknown)
    if errors:
        raise ValidationError(errors)
    return normalised


_KEYS = {"name", "label", "type", "required", "choices", "default"}


def validate_properties(
    schema: list[dict[str, Any]], properties: Any, *, partial: bool = False
) -> dict[str, Any]:
    """Checks feature properties against a schema.

    Returns the cleaned properties, with defaults filled in for new features
    (partial=False). Unknown keys are refused, so data never silently drops out
    of the schema. Null clears a value (unless the field is required).
    """
    if not isinstance(properties, dict):
        raise ValidationError({"properties": ["must be an object"]})
    fields = {f["name"]: f for f in schema}
    errors: dict[str, list[str]] = {}
    for key in properties:
        if key not in fields:
            errors[key] = ["is not a field of this layer"]
    cleaned: dict[str, Any] = {}
    for name, field in fields.items():
        if name not in properties:
            if not partial and "default" in field:
                cleaned[name] = field["default"]
            elif not partial and field["required"]:
                errors[name] = ["is required"]
            continue
        value = properties[name]
        if value is None or value == "":
            if field["required"]:
                errors[name] = ["is required"]
            else:
                cleaned[name] = None
            continue
        try:
            cleaned[name] = _check_value(field, value)
        except ValueError as exc:
            errors[name] = [str(exc)]
    if errors:
        raise ValidationError(errors)
    return cleaned


def incompatible_values(new_field: dict[str, Any], values: Iterable[tuple[int, Any]]) -> list[int]:
    """Ids of features whose value for a field wouldn't fit its new definition."""
    bad = []
    for feature_id, value in values:
        if value is None:
            continue
        try:
            _check_value(new_field, value)
        except ValueError:
            bad.append(feature_id)
    return bad

"""Layer display styles.

{"kind": "single", "fill": "#3a7d44", "stroke": "#1d3d22", "stroke_width": 1.5,
 "point_radius": 5, "fill_opacity": 0.5, "label_field": null}
{"kind": "categorized", "field": "use", "categories": [{"value": "residential",
 "fill": "#f4d35e", ...}], "default": {...symbol...}, "label_field": "name"}
"""

import re
from typing import Any

from django.core.exceptions import ValidationError

COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_SYMBOL: dict[str, Any] = {
    "fill": "#3a7d44",
    "stroke": "#1d3d22",
    "stroke_width": 1.5,
    "point_radius": 5,
    "fill_opacity": 0.4,
}
MAX_CATEGORIES = 100


def _symbol(raw: Any, where: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be an object.")
        return dict(DEFAULT_SYMBOL)
    symbol = {**DEFAULT_SYMBOL, **{k: raw[k] for k in DEFAULT_SYMBOL if k in raw}}
    for key in ("fill", "stroke"):
        if not isinstance(symbol[key], str) or not COLOUR.match(symbol[key]):
            errors.append(f"{where}: {key} must be a colour like #1d3d22.")
    for key, low, high in (
        ("stroke_width", 0, 20),
        ("point_radius", 1, 30),
        ("fill_opacity", 0, 1),
    ):
        value = symbol[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not low <= value <= high
        ):
            errors.append(f"{where}: {key} must be between {low} and {high}.")
    return symbol


def default_style() -> dict[str, Any]:
    return {"kind": "single", **DEFAULT_SYMBOL, "label_field": None}


def validate_style(style: Any, schema: list[dict[str, Any]]) -> dict[str, Any]:
    if not style:
        return default_style()
    if not isinstance(style, dict):
        raise ValidationError("The style must be an object.")
    errors: list[str] = []
    field_names = {f["name"] for f in schema}
    label = style.get("label_field")
    if label is not None and label not in field_names:
        errors.append(f"label_field: {label!r} is not a field of this layer.")
    kind = style.get("kind", "single")
    if kind == "single":
        result = {"kind": "single", **_symbol(style, "style", errors), "label_field": label}
    elif kind == "categorized":
        field = style.get("field")
        if field not in field_names:
            errors.append(f"field: {field!r} is not a field of this layer.")
        categories = style.get("categories")
        if not isinstance(categories, list) or len(categories) > MAX_CATEGORIES:
            errors.append(f"categories: must be a list of at most {MAX_CATEGORIES}.")
            categories = []
        cleaned = []
        for i, category in enumerate(categories, start=1):
            if not isinstance(category, dict) or "value" not in category:
                errors.append(f"Category {i}: needs a value.")
                continue
            cleaned.append(
                {"value": category["value"], **_symbol(category, f"Category {i}", errors)}
            )
        result = {
            "kind": "categorized",
            "field": field,
            "categories": cleaned,
            "default": _symbol(style.get("default", {}), "default", errors),
            "label_field": label,
        }
    else:
        errors.append("kind must be 'single' or 'categorized'.")
        result = {}
    if errors:
        raise ValidationError(errors)
    return result

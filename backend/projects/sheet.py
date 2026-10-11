"""A plan sheet: the project's layers drawn to a true scale in the project's
own coordinate system, with the things a plan carries: a title block, a
legend, grid coordinates, a scale bar and a north arrow.

Coordinates go from the database to the page untouched (no reprojection):
a distance on the sheet times the scale is the distance in the grid. Layers
kept in another coordinate system than the project's are left out and named.
"""

import io
import math
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError

from . import geometry as geo
from . import privacy
from .models import Layer, PlanProject

MM = 72.0 / 25.4  # points per millimetre
PAPERS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0)}
SCALES = (250, 500, 1000, 1250, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000, 250000)
MARGIN_MM = 10.0
PANEL_MM = 72.0  # the title block and legend, down the right-hand side
MAX_FEATURES = 20_000  # per layer
MAX_LABELS = 400
MAX_LEGEND = 28


def frame_mm(paper: str) -> tuple[float, float]:
    """The map frame's width and height on a paper size (landscape)."""
    width, height = PAPERS[paper]
    return width - 2 * MARGIN_MM - PANEL_MM - 4.0, height - 2 * MARGIN_MM


def fit_scale(extent: tuple[float, float, float, float], unit_m: float, paper: str) -> int:
    """The largest standard scale at which the extent fits the frame."""
    width, height = frame_mm(paper)
    span_x = (extent[2] - extent[0]) * unit_m * 1000.0
    span_y = (extent[3] - extent[1]) * unit_m * 1000.0
    for scale in SCALES:
        if span_x / scale <= width * 0.96 and span_y / scale <= height * 0.96:
            return scale
    return SCALES[-1]


def project_extent(
    project: PlanProject, layers: list[Layer]
) -> tuple[float, float, float, float] | None:
    """What the sheet should show: the planning area if it has one, else
    everything in the layers."""
    boxes = []
    boundary = project.boundary_feature
    if boundary is not None and boundary.layer.crs_id == project.crs_id:
        box = geo.extent(boundary.layer)["native"]  # the boundary layer holds only the boundary
        if box:
            return (box[0], box[1], box[2], box[3])
    for layer in layers:
        box = geo.extent(layer)["native"]
        if box:
            boxes.append(box)
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _round_interval(target: float) -> float:
    """A round number near `target`: 1, 2 or 5 times a power of ten."""
    if target <= 0:
        return 1.0
    power = 10 ** math.floor(math.log10(target))
    for step in (1, 2, 5, 10):
        if step * power >= target:
            return float(step * power)
    return float(10 * power)


def _symbol(style: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    if style.get("kind") == "categorized":
        value = properties.get(style.get("field"))
        for category in style.get("categories", []):
            if str(category.get("value")) == str(value):
                return dict(category)
        return dict(style.get("default", {}))
    return style


def _rings(geometry: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    """(kind, parts): "area" with rings, "line" with paths, "point" with positions."""
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon":
        return [("area", coordinates)]
    if kind == "MultiPolygon":
        return [("area", polygon) for polygon in coordinates]
    if kind == "LineString":
        return [("line", [coordinates])]
    if kind == "MultiLineString":
        return [("line", coordinates)]
    if kind == "Point":
        return [("point", [coordinates])]
    if kind == "MultiPoint":
        return [("point", coordinates)]
    if kind == "GeometryCollection":
        return [part for g in geometry.get("geometries", []) for part in _rings(g)]
    return []


def plan_sheet(
    project: PlanProject,
    *,
    paper: str = "A3",
    scale: int | None = None,
    title: str = "",
    prepared_by: str = "",
) -> tuple[bytes, int]:
    """The sheet as a PDF, and the scale it was drawn at."""
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.pdfgen import canvas as pdf_canvas

    if paper not in PAPERS:
        raise ValidationError({"paper": [f"One of {', '.join(PAPERS)}."]})
    crs = project.crs
    if not crs.unit_to_metre:
        raise ValidationError(
            "The project's coordinate system is in degrees: a plan sheet needs a grid in feet"
            " or metres."
        )
    unit_m = float(crs.unit_to_metre)
    every = list(project.layers.filter(visible=True).select_related("crs").order_by("order", "id"))
    layers = [layer for layer in every if layer.crs_id == crs.pk]
    left_out = [layer.name for layer in every if layer.crs_id != crs.pk]
    extent = project_extent(project, layers)
    if extent is None:
        raise ValidationError("There is nothing to draw yet: the project's layers are empty.")
    if scale is None:
        scale = fit_scale(extent, unit_m, paper)
    if not 50 <= scale <= 1_000_000:
        raise ValidationError({"scale": ["Between 1:50 and 1:1,000,000."]})

    page_w, page_h = PAPERS[paper]
    frame_w, frame_h = frame_mm(paper)
    x0, y0 = MARGIN_MM, MARGIN_MM
    per_unit = unit_m * 1000.0 / scale  # millimetres on paper per coordinate unit
    centre_x, centre_y = (extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2
    west, south = centre_x - frame_w / 2 / per_unit, centre_y - frame_h / 2 / per_unit
    east, north = west + frame_w / per_unit, south + frame_h / per_unit

    def to_page(x: float, y: float) -> tuple[float, float]:
        return (x0 + (x - west) * per_unit) * MM, (y0 + (y - south) * per_unit) * MM

    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=(page_w * MM, page_h * MM))
    c.setTitle(title or project.name)
    c.setAuthor(prepared_by)

    # --- The map -----------------------------------------------------------------------------
    c.saveState()
    clip = c.beginPath()
    clip.rect(x0 * MM, y0 * MM, frame_w * MM, frame_h * MM)
    c.clipPath(clip, stroke=0, fill=0)
    legend: list[tuple[str, dict[str, Any], str]] = []
    truncated: list[str] = []
    labels = 0
    for layer in layers:
        hidden = set(privacy.hidden_fields(layer))
        style = layer.style or {}
        label_field = style.get("label_field")
        if label_field in hidden:
            label_field = None
        features = geo.in_box(layer, (west, south, east, north), MAX_FEATURES + 1)
        if len(features) > MAX_FEATURES:
            truncated.append(layer.name)
            features = features[:MAX_FEATURES]
        if not features:
            continue
        if style.get("kind") == "categorized":
            present = {str(p.get(style.get("field"))) for _id, p, _g in features}
            for category in style.get("categories", []):
                if str(category.get("value")) in present:
                    legend.append(
                        (
                            f"{layer.name}: {category.get('value')}",
                            dict(category),
                            layer.geometry_type,
                        )
                    )
        else:
            legend.append((layer.name, style, layer.geometry_type))
        for _feature_id, properties, geometry in features:
            symbol = _symbol(style, properties)
            fill = HexColor(symbol.get("fill", "#3a7d44"))
            stroke = HexColor(symbol.get("stroke", "#1d3d22"))
            c.setStrokeColor(stroke)
            c.setLineWidth(max(0.2, float(symbol.get("stroke_width", 1.5)) * 0.5))
            anchor: tuple[float, float] | None = None
            for kind, parts in _rings(geometry):
                if kind == "area":
                    path = c.beginPath()
                    for ring in parts:
                        if len(ring) < 3:
                            continue
                        px, py = to_page(ring[0][0], ring[0][1])
                        path.moveTo(px, py)
                        for position in ring[1:]:
                            px, py = to_page(position[0], position[1])
                            path.lineTo(px, py)
                        path.close()
                    c.setFillColor(fill)
                    c.setFillAlpha(float(symbol.get("fill_opacity", 0.4)))
                    c.drawPath(path, stroke=1, fill=1, fillMode=0)  # even-odd: holes stay open
                    c.setFillAlpha(1)
                    if anchor is None and parts and parts[0]:
                        ring = parts[0]
                        anchor = (
                            sum(p[0] for p in ring) / len(ring),
                            sum(p[1] for p in ring) / len(ring),
                        )
                elif kind == "line":
                    for line in parts:
                        if len(line) < 2:
                            continue
                        path = c.beginPath()
                        px, py = to_page(line[0][0], line[0][1])
                        path.moveTo(px, py)
                        for position in line[1:]:
                            px, py = to_page(position[0], position[1])
                            path.lineTo(px, py)
                        c.drawPath(path, stroke=1, fill=0)
                        if anchor is None:
                            middle = line[len(line) // 2]
                            anchor = (middle[0], middle[1])
                else:
                    radius = max(0.6, float(symbol.get("point_radius", 5)) * 0.25) * MM
                    for position in parts:
                        px, py = to_page(position[0], position[1])
                        c.setFillColor(fill)
                        c.circle(px, py, radius, stroke=1, fill=1)
                        if anchor is None:
                            anchor = (position[0], position[1])
            label = properties.get(label_field) if label_field else None
            if label not in (None, "") and anchor is not None and labels < MAX_LABELS:
                labels += 1
                px, py = to_page(*anchor)
                c.setFillColor(black)
                c.setFont("Helvetica", 6)
                c.drawCentredString(px, py - 2, str(label)[:40])

    # Grid crosses, at a round interval about 5 cm apart on the sheet.
    interval = _round_interval(50.0 / per_unit)
    c.setStrokeColor(black)
    c.setLineWidth(0.25)
    first_x = math.ceil(west / interval) * interval
    first_y = math.ceil(south / interval) * interval
    xs = [first_x + i * interval for i in range(int((east - first_x) / interval) + 1)]
    ys = [first_y + i * interval for i in range(int((north - first_y) / interval) + 1)]
    arm = 1.5 * MM
    for gx in xs:
        for gy in ys:
            px, py = to_page(gx, gy)
            c.line(px - arm, py, px + arm, py)
            c.line(px, py - arm, px, py + arm)
    c.restoreState()

    # --- The frame and its coordinates ----------------------------------------------------
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.rect(x0 * MM, y0 * MM, frame_w * MM, frame_h * MM, stroke=1, fill=0)
    c.setFont("Helvetica", 6)
    c.setFillColor(black)
    for gx in xs:
        px, _py = to_page(gx, south)
        c.line(px, y0 * MM, px, (y0 - 1.5) * MM)
        c.drawCentredString(px, (y0 - 4) * MM, f"{gx:,.0f}")
    for gy in ys:
        _px, py = to_page(west, gy)
        c.line(x0 * MM, py, (x0 - 1.5) * MM, py)
        c.saveState()
        c.translate((x0 - 2.5) * MM, py)
        c.rotate(90)
        c.drawCentredString(0, 0, f"{gy:,.0f}")
        c.restoreState()

    # --- The panel: title block, north arrow, scale bar, legend ----------------------------
    panel_x = x0 + frame_w + 4.0
    panel_w = PANEL_MM
    c.rect(panel_x * MM, y0 * MM, panel_w * MM, frame_h * MM, stroke=1, fill=0)
    cursor = y0 + frame_h - 6.0  # millimetres from the bottom, moving down

    def text(value: str, size: float = 8, bold: bool = False, gap: float = 4.2) -> None:
        nonlocal cursor
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        width = (panel_w - 6) * MM
        words, line = str(value).split(), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if c.stringWidth(trial, c._fontname, size) > width and line:
                c.drawString((panel_x + 3) * MM, cursor * MM, line)
                cursor -= gap
                line = word
            else:
                line = trial
        if line:
            c.drawString((panel_x + 3) * MM, cursor * MM, line)
            cursor -= gap

    def rule() -> None:
        nonlocal cursor
        c.setLineWidth(0.4)
        c.line(panel_x * MM, (cursor + 1.5) * MM, (panel_x + panel_w) * MM, (cursor + 1.5) * MM)
        cursor -= 3.5

    text(project.district.name.upper(), 9, bold=True, gap=4.6)
    text("Physical Planning Department", 7)
    rule()
    text(title or project.name, 11, bold=True, gap=5.4)
    if project.community:
        text(project.community, 8)
    rule()
    text(f"Scale 1:{scale:,} at {paper}", 9, bold=True)
    text(f"{crs.code} {crs.name}", 7, gap=3.6)
    text(f"Grid in {crs.units}; crosses every {interval:,.0f}", 7, gap=3.6)
    rule()

    # North arrow: the grid's north, which is up the sheet.
    arrow_x, arrow_y = (panel_x + 9) * MM, (cursor - 9) * MM
    c.setFillColor(black)
    head = c.beginPath()
    head.moveTo(arrow_x, arrow_y + 9 * MM)
    head.lineTo(arrow_x - 2.6 * MM, arrow_y)
    head.lineTo(arrow_x, arrow_y + 2 * MM)
    head.lineTo(arrow_x + 2.6 * MM, arrow_y)
    head.close()
    c.drawPath(head, stroke=1, fill=1)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(arrow_x, arrow_y + 10 * MM, "N")
    c.setFont("Helvetica", 6)
    c.drawString((panel_x + 16) * MM, arrow_y + 5 * MM, "Grid north")

    # Scale bar: a round length in metres about 40 mm long.
    bar_m = _round_interval(40.0 * scale / 1000.0 / 2) * 2
    bar_mm = bar_m * 1000.0 / scale
    while bar_mm > panel_w - 26 and bar_m > 1:
        bar_m /= 2
        bar_mm = bar_m * 1000.0 / scale
    bar_x, bar_y = (panel_x + 16) * MM, arrow_y - 3 * MM
    c.setLineWidth(0.6)
    for i in range(4):
        c.setFillColor(black if i % 2 == 0 else white)
        c.rect(bar_x + i * bar_mm / 4 * MM, bar_y, bar_mm / 4 * MM, 1.6 * MM, stroke=1, fill=1)
    c.setFillColor(black)
    c.setFont("Helvetica", 6)
    c.drawString(bar_x, bar_y - 2.6 * MM, "0")
    c.drawRightString(bar_x + bar_mm * MM, bar_y - 2.6 * MM, f"{bar_m:,.0f} m")
    cursor -= 24.0
    rule()

    text("LEGEND", 8, bold=True)
    for name, symbol, kind in legend[:MAX_LEGEND]:
        sx, sy = (panel_x + 3) * MM, (cursor - 0.6) * MM
        c.setStrokeColor(HexColor(symbol.get("stroke", "#1d3d22")))
        c.setFillColor(HexColor(symbol.get("fill", "#3a7d44")))
        c.setLineWidth(0.6)
        if kind == "line":
            c.line(sx, sy + 1.2 * MM, sx + 7 * MM, sy + 1.2 * MM)
        elif kind == "point":
            c.circle(sx + 3.5 * MM, sy + 1.2 * MM, 1.2 * MM, stroke=1, fill=1)
        else:
            c.setFillAlpha(float(symbol.get("fill_opacity", 0.4)))
            c.rect(sx, sy, 7 * MM, 2.6 * MM, stroke=1, fill=1)
            c.setFillAlpha(1)
        c.setFillColor(black)
        c.setFont("Helvetica", 7)
        c.drawString(sx + 9 * MM, sy + 0.4 * MM, name[:38])
        cursor -= 4.4
        if cursor < y0 + 44:
            break
    if len(legend) > MAX_LEGEND:
        text(f"and {len(legend) - MAX_LEGEND} more", 6)

    # The foot of the panel: who drew it, who approved it, and what was left out.
    cursor = y0 + 40.0
    rule()
    for role in ("Prepared by", "Checked by", "Approved by"):
        name = prepared_by if role == "Prepared by" else ""
        text(f"{role}: {name}", 7, gap=3.2)
        c.setLineWidth(0.3)
        c.line(
            (panel_x + 22) * MM,
            (cursor + 2.6) * MM,
            (panel_x + panel_w - 3) * MM,
            (cursor + 2.6) * MM,
        )
        cursor -= 3.4
    text(f"Printed {date.today().isoformat()}. Coordinates as recorded.", 6, gap=3.0)
    for names, why in (
        (left_out, "in another coordinate system"),
        (truncated, "too many features to draw in full"),
    ):
        if names:
            text(f"Not drawn in full ({why}): {', '.join(names)}.", 6, gap=3.0)

    c.showPage()
    c.save()
    return buffer.getvalue(), scale

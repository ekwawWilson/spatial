// Turns a layer's style (the same one the web map uses) into MapLibre paint
// properties.

import type { GeometryType, LayerStyle, SymbolStyle } from "../types";

type Expr = unknown[];

function pick(style: LayerStyle, key: keyof SymbolStyle): string | number | Expr {
  if (style.kind === "single") return style[key];
  if (style.categories.length === 0) return style.default[key];
  const match: Expr = ["match", ["to-string", ["get", style.field]]];
  const seen = new Set<string>();
  for (const category of style.categories) {
    const value = String(category.value);
    if (seen.has(value)) continue;
    seen.add(value);
    match.push(value, category[key]);
  }
  match.push(style.default[key]);
  return match;
}

export interface LayerPaint {
  fill?: Record<string, unknown>;
  line?: Record<string, unknown>;
  circle?: Record<string, unknown>;
}

export function paintFor(geometryType: GeometryType, style: LayerStyle): LayerPaint {
  if (geometryType === "point") {
    return {
      circle: {
        "circle-radius": pick(style, "point_radius"),
        "circle-color": pick(style, "fill"),
        "circle-stroke-color": pick(style, "stroke"),
        "circle-stroke-width": pick(style, "stroke_width"),
      },
    };
  }
  const line = { "line-color": pick(style, "stroke"), "line-width": pick(style, "stroke_width") };
  if (geometryType === "line") return { line };
  return { fill: { "fill-color": pick(style, "fill"), "fill-opacity": pick(style, "fill_opacity") }, line };
}

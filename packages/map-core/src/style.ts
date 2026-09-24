// Layer styles (as stored on the server) -> OpenLayers styles.

import Feature from "ol/Feature";
import type { FeatureLike } from "ol/Feature";
import { Circle, Fill, Stroke, Style, Text } from "ol/style";

import type { LayerStyle, Symbol } from "./types";

function rgba(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function symbolStyle(symbol: Symbol, label?: string): Style {
  const fill = new Fill({ color: rgba(symbol.fill, symbol.fill_opacity) });
  const stroke = new Stroke({ color: symbol.stroke, width: symbol.stroke_width });
  return new Style({
    fill,
    stroke,
    image: new Circle({ radius: symbol.point_radius, fill: new Fill({ color: symbol.fill }), stroke }),
    text: label
      ? new Text({
          text: label,
          font: "12px system-ui, sans-serif",
          fill: new Fill({ color: "#1d2521" }),
          stroke: new Stroke({ color: "#ffffff", width: 3 }),
          overflow: true,
        })
      : undefined,
  });
}

/** The symbol a feature gets under a style (for legends and tests). */
export function symbolFor(style: LayerStyle, properties: Record<string, unknown>): Symbol {
  if (style.kind === "single") return style;
  const value = properties[style.field];
  return style.categories.find((c) => c.value === value) ?? style.default;
}

/** OpenLayers style function for a layer; `highlight` marks selected features. */
export function olStyleFunction(style: LayerStyle, isSelected: (id: unknown) => boolean = () => false) {
  const cache = new Map<string, Style>();
  return (feature: FeatureLike): Style => {
    const properties = (feature instanceof Feature ? feature.getProperties() : feature.getProperties()) as Record<
      string,
      unknown
    >;
    let symbol = symbolFor(style, properties);
    if (isSelected(feature.getId())) {
      symbol = { ...symbol, stroke: "#e4572e", stroke_width: Math.max(3, symbol.stroke_width + 2) };
    }
    const label = style.label_field ? properties[style.label_field] : undefined;
    const labelText = label === undefined || label === null ? undefined : String(label);
    const key = JSON.stringify([symbol, labelText]);
    let olStyle = cache.get(key);
    if (!olStyle) {
      olStyle = symbolStyle(symbol, labelText);
      cache.set(key, olStyle);
    }
    return olStyle;
  };
}

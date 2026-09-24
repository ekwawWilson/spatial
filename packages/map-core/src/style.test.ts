import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import { describe, expect, it } from "vitest";

import { formatArea, formatLength } from "./measure";
import { olStyleFunction, symbolFor } from "./style";
import type { LayerStyle } from "./types";

const base = { fill: "#3a7d44", stroke: "#1d3d22", stroke_width: 1.5, point_radius: 5, fill_opacity: 0.4 };

const categorized: LayerStyle = {
  kind: "categorized",
  field: "use",
  categories: [{ value: "commercial", ...base, fill: "#e4572e" }],
  default: base,
  label_field: "parcel_id",
};

describe("styles", () => {
  it("picks the category symbol, else the default", () => {
    expect(symbolFor(categorized, { use: "commercial" }).fill).toBe("#e4572e");
    expect(symbolFor(categorized, { use: "residential" }).fill).toBe("#3a7d44");
  });

  it("builds OpenLayers styles with fill opacity, labels and selection highlight", () => {
    const feature = new Feature({ geometry: new Point([0, 0]), use: "commercial", parcel_id: "P-7" });
    feature.setId(7);
    const style = olStyleFunction(categorized, (id) => id === 7)(feature);
    expect(style.getFill()?.getColor()).toBe("rgba(228, 87, 46, 0.4)");
    expect(style.getText()?.getText()).toBe("P-7");
    expect(style.getStroke()?.getColor()).toBe("#e4572e"); // highlighted
    expect(style.getStroke()?.getWidth()).toBe(3.5);
  });
});

describe("measurement", () => {
  it("shows project feet next to metres", () => {
    expect(formatLength(100, { units: "Gold Coast foot", unit_to_metre: 0.3047997101815088 })).toBe(
      "100.00 m (328.08 ft (GC))",
    );
    expect(formatLength(2500, { units: "metre", unit_to_metre: 1 })).toBe("2.500 km");
  });

  it("gives area in m², hectares and acres", () => {
    expect(formatArea(10_000)).toBe("10,000 m² · 1.0000 ha · 2.4711 acres");
  });
});

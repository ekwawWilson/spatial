import type { LayerStyle } from "../src/types";
import { paintFor } from "../src/utils/mapStyle";

const symbol = { fill: "#3a7d44", stroke: "#1d3d22", stroke_width: 1.5, point_radius: 5, fill_opacity: 0.4 };

describe("layer styles on the device map", () => {
  it("draws polygons with a fill and an outline", () => {
    const paint = paintFor("polygon", { kind: "single", label_field: null, ...symbol });
    expect(paint.fill).toEqual({ "fill-color": "#3a7d44", "fill-opacity": 0.4 });
    expect(paint.line).toEqual({ "line-color": "#1d3d22", "line-width": 1.5 });
    expect(paint.circle).toBeUndefined();
  });

  it("draws lines and points with their own properties", () => {
    const single: LayerStyle = { kind: "single", label_field: null, ...symbol };
    expect(paintFor("line", single)).toEqual({ line: { "line-color": "#1d3d22", "line-width": 1.5 } });
    expect(paintFor("point", single).circle).toMatchObject({ "circle-radius": 5, "circle-color": "#3a7d44" });
  });

  it("colours by category with a default for other values", () => {
    const style: LayerStyle = {
      kind: "categorized",
      field: "use",
      label_field: null,
      default: symbol,
      categories: [
        { value: "house", ...symbol, fill: "#ff0000" },
        { value: "shop", ...symbol, fill: "#0000ff" },
        { value: "house", ...symbol, fill: "#00ff00" }, // a repeated value is used once
      ],
    };
    expect(paintFor("polygon", style).fill!["fill-color"]).toEqual([
      "match", ["to-string", ["get", "use"]], "house", "#ff0000", "shop", "#0000ff", "#3a7d44",
    ]);
  });
});

import { describe, expect, it } from "vitest";

import { convert, describeAccuracy, formatPosition, parsePositions, registerSystems } from "./crs";

// What the server sends for EPSG:2136: pyproj's PROJ string plus +towgs84 from
// the operation it uses (Accra to WGS 84 (4)).
const GHANA_GRID_WEB =
  "+proj=tmerc +lat_0=4.66666666666667 +lon_0=-1 +k=0.99975 +x_0=274319.739163358 +y_0=0 " +
  "+a=6378300 +rf=296 +to_meter=0.304799710181509 +towgs84=-170,33,326 +no_defs";

// Reference values computed by PROJ 9.5 (pyproj) with the same operation.
const REFERENCE: [[number, number], [number, number]][] = [
  [[-0.2, 5.6], [1190631.4519, 337708.9446]],
  [[-1.6, 6.7], [682304.5752, 736646.3792]],
  [[-0.85, 9.4], [953940.8935, 1715977.9133]],
];

const FOOT = 0.304799710181509;

describe("proj4js with the server's definitions", () => {
  registerSystems([
    { code: "EPSG:2136", proj4: GHANA_GRID_WEB },
    { code: "EPSG:4326", proj4: "+proj=longlat +datum=WGS84 +no_defs" },
  ]);

  it.each(REFERENCE)("places %j within 1 cm of the server", (lonlat, expected) => {
    const [x, y] = convert("EPSG:4326", "EPSG:2136", lonlat);
    const errorMetres = Math.hypot(x - expected[0], y - expected[1]) * FOOT;
    expect(errorMetres).toBeLessThan(0.01);
  });

  it("goes back to (nearly) the same longitude/latitude", () => {
    // proj4js's inverse of a 2D datum shift leaves ~1 mm; fine for display.
    // Authoritative conversions run on the server, which inverts exactly.
    const [lon, lat] = convert("EPSG:2136", "EPSG:4326", convert("EPSG:4326", "EPSG:2136", [-0.2, 5.6]));
    expect(Math.abs(lon + 0.2)).toBeLessThan(1e-7); // ~1 cm
    expect(Math.abs(lat - 5.6)).toBeLessThan(1e-7);
  });
});

describe("formatting and parsing", () => {
  it("formats projected and geographic positions with their units", () => {
    expect(formatPosition({ kind: "projected", units: "Gold Coast foot" }, [1190631.45191, 337708.9])).toBe(
      "E 1190631.452 ft (GC), N 337708.900 ft (GC)",
    );
    expect(formatPosition({ kind: "geographic", units: "degree" }, [-0.2, 5.6])).toBe(
      "Lon -0.2000000°, Lat 5.6000000°",
    );
  });

  it("parses pasted coordinates and reports bad lines", () => {
    const { positions, badLines } = parsePositions("900000 1900000\n\n900100,1900050\nabc def\n12\n");
    expect(positions).toEqual([
      [900000, 1900000],
      [900100, 1900050],
    ]);
    expect(badLines).toEqual([4, 5]);
  });

  it("states accuracy in plain terms", () => {
    expect(describeAccuracy(6)).toBe("±6 m");
    expect(describeAccuracy(0.05)).toBe("±5 cm");
    expect(describeAccuracy(0)).toBe("exact");
    expect(describeAccuracy(null)).toBe("accuracy unknown");
  });
});

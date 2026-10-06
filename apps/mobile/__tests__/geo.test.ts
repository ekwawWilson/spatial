import type { Fix, Position } from "../src/types";
import { averageFixes, bounds, buildGeometry, distance, extendTrack, formatArea, formatDistance, pathLength, ringArea } from "../src/utils/geo";

const fix = (longitude: number, latitude: number, accuracy: number | null, timestamp = 0): Fix => ({ longitude, latitude, accuracy, timestamp });

describe("distances and areas", () => {
  it("measures a degree of latitude as about 111.2 km", () => {
    expect(distance([0, 5], [0, 6])).toBeGreaterThan(111_100);
    expect(distance([0, 5], [0, 6])).toBeLessThan(111_300);
  });

  it("adds up a path", () => {
    const path: Position[] = [[-0.2, 5.6], [-0.2, 5.601], [-0.199, 5.601]];
    expect(pathLength(path)).toBeCloseTo(distance(path[0]!, path[1]!) + distance(path[1]!, path[2]!), 6);
  });

  it("measures a 100 m square as about one hectare, open or closed", () => {
    const d = 100 / 111_195; // degrees of latitude for 100 m
    const dx = d / Math.cos((5.6 * Math.PI) / 180);
    const ring: Position[] = [[-0.2, 5.6], [-0.2 + dx, 5.6], [-0.2 + dx, 5.6 + d], [-0.2, 5.6 + d]];
    expect(ringArea(ring)).toBeGreaterThan(9_950);
    expect(ringArea(ring)).toBeLessThan(10_050);
    expect(ringArea([...ring, ring[0]!])).toBeCloseTo(ringArea(ring), 6);
    expect(ringArea(ring.slice(0, 2))).toBe(0);
  });

  it("formats in the project's units too", () => {
    expect(formatDistance(30.48, 0.3048, "Gold Coast foot")).toBe("30.5 m (100.0 ft)");
    expect(formatDistance(1500, 1, "metre")).toBe("1.50 km");
    expect(formatArea(10_000)).toContain("1.0000 ha");
  });
});

describe("averaging GPS readings", () => {
  it("weights better readings more and reports the mean accuracy", () => {
    const result = averageFixes([fix(0, 0, 2, 10), fix(0.0001, 0, 20, 30)], 50)!;
    expect(result.readings).toBe(2);
    expect(result.accuracy).toBe(11);
    expect(result.timestamp).toBe(30);
    // 1/4 against 1/400: the good reading counts 100 times more.
    expect(result.position[0]).toBeCloseTo(0.0001 / 101, 10);
  });

  it("ignores readings that are too poor or have no accuracy", () => {
    const result = averageFixes([fix(1, 1, 4), fix(9, 9, 80), fix(9, 9, null)], 50)!;
    expect(result.readings).toBe(1);
    expect(result.position).toEqual([1, 1]);
    expect(averageFixes([fix(9, 9, 80)], 50)).toBeNull();
  });
});

describe("walk mode", () => {
  it("keeps a reading only when it is usable and far enough from the last", () => {
    let track: Fix[] = [];
    track = extendTrack(track, fix(-0.2, 5.6, 5), 2, 50);
    expect(track).toHaveLength(1);
    expect(extendTrack(track, fix(-0.2, 5.600001, 5), 2, 50)).toBe(track); // 0.1 m away
    expect(extendTrack(track, fix(-0.2, 5.601, 90), 2, 50)).toBe(track); // too poor
    expect(extendTrack(track, fix(-0.2, 5.60005, 5), 2, 50)).toHaveLength(2); // 5.5 m away
  });
});

describe("building geometry from captured points", () => {
  const points: Position[] = [[0, 0], [1, 0], [1, 1]];

  it("makes the layer's kind of geometry", () => {
    expect(buildGeometry("point", points)).toEqual({ geometry: { type: "Point", coordinates: [1, 1] } });
    expect(buildGeometry("line", points)).toEqual({ geometry: { type: "LineString", coordinates: points } });
    expect(buildGeometry("polygon", points)).toEqual({ geometry: { type: "Polygon", coordinates: [[...points, [0, 0]]] } });
  });

  it("closes a polygon once, even if the last point repeats the first", () => {
    const result = buildGeometry("polygon", [...points, [0, 0]]);
    expect("geometry" in result && result.geometry.type === "Polygon" && result.geometry.coordinates[0]).toHaveLength(4);
  });

  it("says what is missing", () => {
    expect(buildGeometry("point", [])).toEqual({ problem: "No position yet." });
    expect(buildGeometry("line", [[0, 0]])).toEqual({ problem: "A line needs at least 2 points." });
    expect(buildGeometry("polygon", points.slice(0, 2))).toEqual({ problem: "An area needs at least 3 corners." });
  });

  it("finds bounds", () => {
    expect(bounds(points)).toEqual([0, 0, 1, 1]);
    expect(bounds([])).toBeNull();
  });
});

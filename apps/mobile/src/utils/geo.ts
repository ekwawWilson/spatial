// Geometry helpers for the device: distances, areas, averaging GPS readings.
// These are for display and capture on the phone. Coordinates of record are
// converted and measured on the server.

import type { Fix, Geometry, GeometryType, Position } from "../types";

const EARTH_RADIUS = 6371008.8; // mean radius, metres
const rad = (deg: number) => (deg * Math.PI) / 180;

/** Great-circle distance in metres. */
export function distance(a: Position, b: Position): number {
  const dLat = rad(b[1] - a[1]);
  const dLon = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function pathLength(points: Position[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += distance(points[i - 1]!, points[i]!);
  return total;
}

/** Area of a ring in square metres (spherical excess; the ring may be open or closed). */
export function ringArea(ring: Position[]): number {
  const points = ring.length > 1 && samePosition(ring[0]!, ring[ring.length - 1]!) ? ring.slice(0, -1) : ring;
  if (points.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const p1 = points[i]!;
    const p2 = points[(i + 1) % points.length]!;
    sum += rad(p2[0] - p1[0]) * (2 + Math.sin(rad(p1[1])) + Math.sin(rad(p2[1])));
  }
  return Math.abs((sum * EARTH_RADIUS * EARTH_RADIUS) / 2);
}

export function samePosition(a: Position, b: Position): boolean {
  return a[0] === b[0] && a[1] === b[1];
}

/** Readings good enough to use. A reading with no accuracy is not trusted. */
export function usable(fixes: Fix[], maxAccuracy: number): Fix[] {
  return fixes.filter((f) => f.accuracy !== null && f.accuracy <= maxAccuracy);
}

export interface AveragedFix {
  position: Position;
  /** Mean reported accuracy of the readings used, metres. */
  accuracy: number;
  readings: number;
  /** Time of the last reading used. */
  timestamp: number;
}

/** Averages readings, weighting each by 1/accuracy² so better fixes count
 * for more. Returns null when no reading is usable. */
export function averageFixes(fixes: Fix[], maxAccuracy: number): AveragedFix | null {
  const good = usable(fixes, maxAccuracy);
  if (good.length === 0) return null;
  let wSum = 0;
  let lon = 0;
  let lat = 0;
  let acc = 0;
  for (const fix of good) {
    const w = 1 / Math.max(fix.accuracy!, 0.5) ** 2;
    wSum += w;
    lon += fix.longitude * w;
    lat += fix.latitude * w;
    acc += fix.accuracy!;
  }
  return {
    position: [lon / wSum, lat / wSum],
    accuracy: acc / good.length,
    readings: good.length,
    timestamp: Math.max(...good.map((f) => f.timestamp)),
  };
}

/** Adds a reading to a walked track if it is usable and far enough from the
 * last point kept. Returns the same array when nothing was added. */
export function extendTrack(track: Fix[], fix: Fix, minDistance: number, maxAccuracy: number): Fix[] {
  if (fix.accuracy === null || fix.accuracy > maxAccuracy) return track;
  const last = track[track.length - 1];
  if (last && distance([last.longitude, last.latitude], [fix.longitude, fix.latitude]) < minDistance) return track;
  return [...track, fix];
}

/** A geometry of the layer's type from captured vertices, or the reason it
 * can't be made yet. */
export function buildGeometry(type: GeometryType, points: Position[]): { geometry: Geometry } | { problem: string } {
  if (type === "point") {
    return points.length >= 1 ? { geometry: { type: "Point", coordinates: points[points.length - 1]! } } : { problem: "No position yet." };
  }
  if (type === "line") {
    return points.length >= 2 ? { geometry: { type: "LineString", coordinates: points } } : { problem: "A line needs at least 2 points." };
  }
  const open = points.length > 1 && samePosition(points[0]!, points[points.length - 1]!) ? points.slice(0, -1) : points;
  if (open.length < 3) return { problem: "An area needs at least 3 corners." };
  return { geometry: { type: "Polygon", coordinates: [[...open, open[0]!]] } };
}

/** Every position of a geometry, flattened. */
export function positions(geometry: Geometry): Position[] {
  switch (geometry.type) {
    case "Point":
      return [geometry.coordinates];
    case "LineString":
    case "MultiPoint":
      return geometry.coordinates;
    case "Polygon":
    case "MultiLineString":
      return geometry.coordinates.flat();
    case "MultiPolygon":
      return geometry.coordinates.flat(2);
  }
}

/** [west, south, east, north] of some positions, or null if there are none. */
export function bounds(points: Position[]): [number, number, number, number] | null {
  if (points.length === 0) return null;
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const [lon, lat] of points) {
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  return [west, south, east, north];
}

export function formatDistance(metres: number, unitToMetre: number | null, units: string): string {
  const main = metres >= 1000 ? `${(metres / 1000).toFixed(2)} km` : `${metres.toFixed(1)} m`;
  if (!unitToMetre || Math.abs(unitToMetre - 1) < 1e-9) return main;
  return `${main} (${(metres / unitToMetre).toFixed(1)} ${shortUnit(units)})`;
}

export function formatArea(squareMetres: number): string {
  const hectares = squareMetres / 10_000;
  const acres = squareMetres / 4046.8564224;
  return `${hectares.toFixed(4)} ha · ${acres.toFixed(4)} acres · ${Math.round(squareMetres).toLocaleString("en-GB")} m²`;
}

function shortUnit(units: string): string {
  return /foot|feet/i.test(units) ? "ft" : units;
}

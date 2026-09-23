// Client-side coordinate handling for maps and forms. The server is the
// authority for transformations; proj4js here uses the server's definitions
// (which carry its datum shift) so what the map shows matches the server.

import proj4 from "proj4";

import type { CoordinateSystem, Position } from "./types";

/** Registers systems with proj4js under their codes (e.g. "EPSG:2136"). */
export function registerSystems(systems: Pick<CoordinateSystem, "code" | "proj4">[]): void {
  for (const system of systems) {
    if (system.proj4) proj4.defs(system.code, system.proj4);
  }
}

export function isRegistered(code: string): boolean {
  return proj4.defs(code) !== undefined;
}

/** Converts a position between registered systems (x/y = east/north or lon/lat). */
export function convert(from: string, to: string, position: Position): Position {
  if (from === to) return position;
  const [x, y] = proj4(from, to, position);
  return [x as number, y as number];
}

/** Sensible decimal places for a system's units: millimetres for metres/feet,
 * roughly centimetres for degrees. */
export function decimalsFor(system: Pick<CoordinateSystem, "kind">): number {
  return system.kind === "geographic" ? 7 : 3;
}

const UNIT_ABBREVIATIONS: Record<string, string> = {
  metre: "m",
  "Gold Coast foot": "ft (GC)",
  degree: "°",
};

export function unitLabel(system: Pick<CoordinateSystem, "units">): string {
  return UNIT_ABBREVIATIONS[system.units] ?? system.units;
}

/** "E 1190631.452 ft (GC), N 337708.945 ft (GC)" or "Lon -0.2000000°, Lat 5.6000000°". */
export function formatPosition(system: Pick<CoordinateSystem, "kind" | "units">, [x, y]: Position): string {
  const d = decimalsFor(system);
  if (system.kind === "geographic") return `Lon ${x.toFixed(d)}°, Lat ${y.toFixed(d)}°`;
  const unit = unitLabel(system);
  return `E ${x.toFixed(d)} ${unit}, N ${y.toFixed(d)} ${unit}`;
}

/** Parses "x y" or "x,y" per line (a pasted list of coordinates). Returns the
 * positions and the 1-based numbers of lines that couldn't be read. */
export function parsePositions(text: string): { positions: Position[]; badLines: number[] } {
  const positions: Position[] = [];
  const badLines: number[] = [];
  text.split(/\r?\n/).forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const parts = trimmed.split(/[\s,;]+/).map(Number);
    const [x, y] = parts;
    if (parts.length < 2 || x === undefined || y === undefined || !Number.isFinite(x) || !Number.isFinite(y)) {
      badLines.push(index + 1);
    } else {
      positions.push([x, y]);
    }
  });
  return { positions, badLines };
}

/** Accuracy statement for a transformation, for display next to results. */
export function describeAccuracy(accuracyM: number | null): string {
  if (accuracyM === null) return "accuracy unknown";
  if (accuracyM === 0) return "exact";
  if (accuracyM < 1) return `±${Math.round(accuracyM * 100)} cm`;
  return `±${accuracyM} m`;
}

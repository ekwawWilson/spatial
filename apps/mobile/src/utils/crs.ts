// Shows positions in the project's coordinate system. The definition comes
// from the server (the one the web map uses), so the numbers agree with it.
// Display only: the server converts captured positions itself.

import proj4 from "proj4";

import type { PackageCrs, Position } from "../types";

export function toProject(crs: PackageCrs, position: Position): Position | null {
  try {
    const [x, y] = proj4("EPSG:4326", crs.proj4, position);
    return Number.isFinite(x) && Number.isFinite(y) ? [x!, y!] : null;
  } catch {
    return null;
  }
}

export function formatPosition(crs: PackageCrs, position: Position): string {
  if (crs.kind === "geographic") return `${position[1].toFixed(6)}°, ${position[0].toFixed(6)}°`;
  const projected = toProject(crs, position);
  if (!projected) return `${position[1].toFixed(6)}°, ${position[0].toFixed(6)}°`;
  const unit = /foot|feet/i.test(crs.units) ? "ft" : "m";
  return `E ${projected[0].toFixed(2)}  N ${projected[1].toFixed(2)} ${unit} (${crs.code})`;
}

// Measurement display: metres/hectares plus the project's own units.

import type { CoordinateSystem } from "./types";

const FOOT_GOLD_COAST = 0.3047997101815088;

/** Length in metres -> "123.45 m (405.03 ft (GC))" for a feet-based project. */
export function formatLength(metres: number, project?: Pick<CoordinateSystem, "units" | "unit_to_metre">): string {
  const base = metres >= 1000 ? `${(metres / 1000).toFixed(3)} km` : `${metres.toFixed(2)} m`;
  const extra = projectUnits(metres, project, 1);
  return extra ? `${base} (${extra})` : base;
}

/** Area in square metres -> "1,234.5 m² · 0.1235 ha · 0.3051 acres". */
export function formatArea(squareMetres: number): string {
  const m2 = squareMetres.toLocaleString("en-GB", { maximumFractionDigits: 1 });
  const ha = (squareMetres / 10_000).toFixed(4);
  const acres = (squareMetres / 4046.8564224).toFixed(4);
  return `${m2} m² · ${ha} ha · ${acres} acres`;
}

function projectUnits(
  metres: number,
  project: Pick<CoordinateSystem, "units" | "unit_to_metre"> | undefined,
  power: number,
): string | null {
  if (!project?.unit_to_metre || project.unit_to_metre === 1) return null;
  const value = metres / project.unit_to_metre ** power;
  const unit = project.unit_to_metre === FOOT_GOLD_COAST ? "ft (GC)" : project.units;
  return `${value.toFixed(2)} ${unit}`;
}

import type { PermitClock, PermitRegistry, PermitSummary } from "@spatial/map-core";

/** What the permit screens' tests share: the registry, a deadline and an application row. */
export const registry: PermitRegistry = {
  categories: [
    { code: "building", label: "Erection of a building or structure", kind: "development" },
    { code: "change_of_use", label: "Change of use", kind: "planning" },
  ],
  requirements: [
    { code: "site_plan", label: "Site plan at 1:2500, conforming to the local plan", applies: ["planning", "development"], rule: "r.44(3)(b), r.45(9)(a)" },
    { code: "traffic", label: "Traffic impact report", applies: ["where_applicable"], rule: "r.44(3)(f), r.45(9)(g)" },
  ],
  clocks: [{ code: "acknowledge", label: "Acknowledge receipt in writing", days: 7, rule: "r.44(6)" }],
  inspection_points: [
    { code: "plot_size", label: "The plot size" },
    { code: "started", label: "Whether development has started" },
  ],
  considerations: ["Land use", "Building lines and setbacks"],
  permit_valid_years: 5,
};

export function clock(extra: Partial<PermitClock> = {}): PermitClock {
  return { code: "acknowledge", label: "Acknowledge receipt in writing", rule: "r.44(6)", days: 7, due_on: "2026-10-18", done_on: null, late: false, overdue: false, ...extra };
}

export function summary(id: number, extra: Partial<PermitSummary> = {}): PermitSummary {
  return {
    id,
    project: 5,
    number: `DA/DP/2026/000${id}`,
    kind: "development",
    category: "building",
    category_label: "Erection of a building or structure",
    status: "received",
    status_label: "Received",
    applicant_name: "Ama Mensah",
    proposed_use: "Residential",
    proposed_floors: 2,
    site: 40,
    received_on: "2026-10-11",
    decided_on: null,
    issued_on: null,
    expires_on: null,
    expired: false,
    habitation_on: null,
    next_due: clock(),
    check_counts: { pass: 4, fail: 0, warn: 0, unknown: 1 },
    ...extra,
  };
}

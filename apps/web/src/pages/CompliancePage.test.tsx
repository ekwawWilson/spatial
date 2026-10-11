import type { Compliance } from "@spatial/map-core";
import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const clean: Compliance = {
  as_of: "2026-10-11",
  overdue: 0,
  permits: { open: 0, overdue: 0, overdue_by_step: { acknowledge: 0, inspect: 0, report: 0, issue: 0 }, received_this_year: 0, decided_this_year: 0, decided_within_limit_pct: null, average_days_to_decision: null, limit_days: 30, late: [] },
  requests: { open: 0, overdue: 0, answered_this_year: 0, answered_within_limit_pct: null, limit_days: 5 },
  enforcement: { open: 0, overdue: 0, late: [] },
  zoning: { schemes: 0, overdue: 0, late: [] },
  dataroom: { is_open: false, published_projects: 0, documents_on_display: 0 },
  week_ahead: [],
};

const busy: Compliance = {
  ...clean,
  overdue: 3,
  permits: { ...clean.permits, open: 4, overdue: 1, received_this_year: 12, decided_this_year: 8, decided_within_limit_pct: 75, average_days_to_decision: 24.5, late: [{ id: 7, project: 5, number: "SMA/DP/2026/0007", step: "Acknowledge receipt in writing", rule: "r.44(6)", due_on: "2026-09-08", days_late: 33 }] },
  requests: { open: 2, overdue: 1, answered_this_year: 9, answered_within_limit_pct: 88.9, limit_days: 5 },
  zoning: { schemes: 1, overdue: 1, late: [{ project: 5, scheme: "Kasoa scheme", duty: "Send a copy to LUSPA", rule: "r.29(6): a copy to LUSPA within 28 days of approval", due_on: "2026-09-29" }] },
  dataroom: { is_open: true, published_projects: 2, documents_on_display: 3 },
  week_ahead: [{ id: 9, project: 5, number: "SMA/DP/2026/0009", step: "Acknowledge receipt in writing", due_on: "2026-10-15" }],
};

const backend = (data: Compliance) => fakeBackend({ "GET /api/auth/me/": () => ({ body: makeMe() }), "GET /api/reports/compliance/": () => ({ body: data }) });

describe("statutory deadlines", () => {
  it("says so when nothing is late", async () => {
    renderApp(backend(clean).fetch, { tokens: signedIn, route: "/deadlines" });
    expect(await screen.findByRole("status")).toHaveTextContent("Nothing is past its date.");
    expect(screen.queryByRole("region", { name: "Permit applications past a deadline" })).not.toBeInTheDocument();
  });

  it("counts each duty, how often it is met, and links to what is late", async () => {
    renderApp(backend(busy).fetch, { tokens: signedIn, route: "/deadlines" });
    expect(await screen.findByRole("status")).toHaveTextContent("3 duties are past the date the Regulations set.");
    const duties = screen.getByRole("table", { name: "Duties" });
    expect(within(duties).getByRole("row", { name: /Permit applications/ })).toHaveTextContent("4175% of 8 decided");
    expect(within(duties).getByRole("row", { name: /Requests for information/ })).toHaveTextContent("2188.9% of 9 answered");
    const late = screen.getByRole("region", { name: "Permit applications past a deadline" });
    expect(within(late).getByRole("link", { name: "SMA/DP/2026/0007" })).toHaveAttribute("href", "/projects/5/permits/7");
    expect(late).toHaveTextContent("33");
    expect(screen.getByRole("region", { name: "Other duties past their date" })).toHaveTextContent("Kasoa scheme: Send a copy to LUSPA, due 2026-09-29");
    expect(screen.getByRole("region", { name: "Due this week" })).toHaveTextContent("SMA/DP/2026/0009: Acknowledge receipt in writing, by 2026-10-15");
    expect(screen.getByText(/Average time from receipt to decision this year: 24.5 days/)).toBeInTheDocument();
  });
});

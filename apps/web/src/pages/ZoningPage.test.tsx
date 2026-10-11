import type { NationalZones, ZoningScheme } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const zones: NationalZones = {
  source: "LUSPA Revised Zoning Guidelines and Planning Standards (2025)",
  zones: [
    {
      code: "Re A",
      name: "Residential Zone A: low density",
      group: "Residential",
      colour: "#CC7722",
      pattern: "",
      height: "up to 2 storeys",
      standard: { min_plot_m2: 930, min_width_m: 21.3, max_coverage_pct: 40, min_floors: null, max_floors: 2, front_setback_m: 6, side_setback_m: 3, rear_setback_m: 5, prohibited_uses: ["cemetery"] },
      permitted: ["Detached, duplex and courtyard houses"],
      prohibited: ["Block of flats"],
    },
    { code: "CBD", name: "Central business district", group: "Commercial", colour: "#2E4DA7", pattern: "", height: "", standard: null, permitted: [], prohibited: [] },
  ],
};

const scheme: ZoningScheme = {
  id: 4,
  project: 5,
  name: "Kasoa zoning scheme",
  status: "approved",
  structure_plan_approved_on: null,
  approved_on: "2026-08-01",
  effective_on: null,
  sent_to_luspa_on: null,
  update_every_months: 60,
  notes: "",
  deadlines: {
    send_to_luspa: { rule: "r.29(6): a copy to LUSPA within 28 days of approval", due_on: "2026-08-29", done_on: null, overdue: true },
    update: { rule: "r.29(3): the scheme's schedule for periodic updates", due_on: "2031-08-01", overdue: false },
  },
  updated_at: "",
};

function backend(schemes: ZoningScheme[], extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/relations/zones/": () => ({ body: zones }),
    "GET /api/zoning-schemes/": () => ({ body: schemes }),
    ...extra,
  });
}

describe("zoning page", () => {
  it("lists the national zones with their colours and site standards", async () => {
    renderApp(backend([]).fetch, { tokens: signedIn, route: "/projects/5/zoning" });
    const section = await screen.findByRole("region", { name: "National zones" });
    const row = (await within(section).findByText("Re A")).closest("tr")!;
    expect(row).toHaveTextContent("Plot at least 930 m², at least 21.3 m wide; coverage up to 40%; up to 2 storeys; setbacks 6 m front, 3 m side, 5 m back");
    expect(within(row).getByRole("img", { name: "Re A colour #CC7722" })).toBeInTheDocument();
    expect(row).toHaveTextContent("Block of flats");
    expect(within(section).getByText("CBD").closest("tr")).toHaveTextContent("—");
  });

  it("shows what the register says is due, and records a scheme", async () => {
    const api = backend([scheme], { "POST /api/zoning-schemes/": () => ({ status: 201, body: { ...scheme, id: 9 } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/zoning" });
    const register = await screen.findByRole("region", { name: "Zoning scheme register" });
    const entry = await within(register).findByRole("article", { name: "Kasoa zoning scheme" });
    expect(entry).toHaveTextContent("Send a copy to LUSPA: overdue since 2026-08-29");
    expect(entry).toHaveTextContent("Next update: due 2031-08-01");

    await userEvent.click(within(register).getByRole("button", { name: "Record a zoning scheme" }));
    const form = within(register).getByRole("form", { name: "Zoning scheme" });
    await userEvent.type(within(form).getByLabelText("Name"), "Essam scheme");
    await userEvent.type(within(form).getByLabelText("Structure plan approved on"), "2026-07-01");
    await userEvent.click(within(form).getByRole("button", { name: "Save scheme" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "POST")).toBe(true));
    expect(api.calls.find((c) => c.method === "POST")!.body).toMatchObject({ project: 5, name: "Essam scheme", status: "draft", structure_plan_approved_on: "2026-07-01", update_every_months: 60 });
  });

  it("colours the zoning layer and says which zones weren't recognised", async () => {
    const api = backend([], { "POST /api/projects/5/zoning-style/": () => ({ body: { layer: 3, coloured: ["ReB"], unknown: ["Chief's palace"] } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/zoning" });
    await userEvent.click(await screen.findByRole("button", { name: "Colour the zoning layer in the national colours" }));
    expect(await screen.findByRole("status")).toHaveTextContent("coloured by zone: ReB. Not recognised, left grey: Chief's palace.");
  });

  it("is read-only for people who can't edit relationships", async () => {
    const viewer = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "viewer", permissions: ["district.view", "project.view"] }] });
    renderApp(backend([scheme], { "GET /api/auth/me/": () => ({ body: viewer }) }).fetch, { tokens: signedIn, route: "/projects/5/zoning" });
    expect(await screen.findByRole("article", { name: "Kasoa zoning scheme" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record a zoning scheme" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Colour the zoning layer in the national colours" })).not.toBeInTheDocument();
  });
});

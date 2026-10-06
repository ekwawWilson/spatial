import type { Layer, RelationsRegistry, RelationsRun, RelationshipLink } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { describeLink } from "./RelationsPage";
import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const registry: RelationsRegistry = {
  roles: [
    { code: "properties", label: "Properties (buildings)", domain: "C", geometry: ["polygon", "point"], fields: [] },
    { code: "streets", label: "Streets", domain: "D", geometry: ["line"], fields: [] },
    { code: "drains", label: "Drains", domain: "E", geometry: ["line"], fields: [] },
  ],
  link_types: [
    { code: "connected_to", subject: "properties", verb: "is connected to", object: "drains", inverse: "drains", procedure: "drainage" },
    { code: "violates", subject: "properties", verb: "violates", object: "", inverse: "is violated by", procedure: "rules" },
  ],
  procedures: [
    { code: "drainage", does: "The drain each property probably uses" },
    { code: "rules", does: "Developments that break the standards" },
    { code: "aggregation", does: "Totals" },
  ],
  defaults: {},
};

const layer = (id: number, name: string, geometry_type: string) => ({ id, name, geometry_type, project: 5 }) as unknown as Layer;
const layers = [layer(1, "buildings", "polygon"), layer(2, "streets", "line"), layer(3, "drains", "line")];

function link(id: number, extra: Partial<RelationshipLink> = {}): RelationshipLink {
  return {
    id,
    type: "connected_to",
    verb: "is connected to",
    inverse: "drains",
    subject: { feature: 10 + id, layer: "buildings", label: `B-00${id}` },
    object: { feature: 99, layer: "drains", label: "D-001" },
    rule: "",
    method: "inferred",
    status: "active",
    confidence: 0.71,
    details: { distance_m: 7, within_m: 15 },
    decided_by: null,
    decided_at: null,
    note: "",
    created_at: "",
    ...extra,
  };
}

const run: RelationsRun = {
  id: 3,
  trigger: "manual",
  status: "done",
  started_at: "2026-10-06T10:00:00Z",
  finished_at: "2026-10-06T10:00:02Z",
  started_by: "ama@example.test",
  report: {
    drainage: { connected_to: { found: 3, added: 3, updated: 0, removed: 0, kept: 0 } },
    rules: { skipped: "Not set: Parcels." },
  },
  summary: { project: { properties: 6, in_flood_area: 1, with_violations: 1 }, communities: [{ feature: 7, name: "Community A", properties: 6, in_flood_area: 1 }] },
  error: "",
};

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/relations/registry/": () => ({ body: registry }),
    "GET /api/layers/": () => ({ body: layers }),
    "GET /api/projects/5/layer-roles/": () => ({
      body: { roles: [{ role: "properties", layer: 1, config: {}, suggested: null }, { role: "streets", layer: null, config: {}, suggested: 2 }, { role: "drains", layer: null, config: {}, suggested: null }] },
    }),
    "GET /api/projects/5/relations/run/": () => ({ body: { latest: run, summary: run.summary } }),
    "GET /api/relationships/": () => ({ body: { count: 1, next: null, previous: null, results: [link(1)] } }),
    "GET /api/standards/": () => ({ body: [] }),
    ...extra,
  });
}

describe("relationships page", () => {
  it("offers suggested layers and saves the choices", async () => {
    const api = backend({ "PUT /api/projects/5/layer-roles/": () => ({ body: { roles: [] } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/relations" });
    const form = await screen.findByRole("region", { name: "Layers" });
    expect(within(form).getByLabelText("Layer for Streets")).toHaveValue("2"); // suggested, not yet saved
    expect(within(form).getByText("Not saved yet.")).toBeInTheDocument();
    // Only layers of the right kind are offered: a line layer can't hold properties.
    expect(within(within(form).getByLabelText("Layer for Properties (buildings)")).queryByRole("option", { name: "streets" })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText("Layer for Drains"), "3");
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
        roles: [
          { role: "properties", layer: 1, config: {} },
          { role: "streets", layer: 2, config: {} },
          { role: "drains", layer: 3, config: {} },
        ],
      }),
    );
  });

  it("shows what the last run found, what it skipped and the totals", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5/relations" });
    const section = await screen.findByRole("region", { name: "Run" });
    expect(await within(section).findByText(/is connected to: 3 found, 3 new/)).toBeInTheDocument();
    expect(within(section).getByText("Skipped. Not set: Parcels.")).toBeInTheDocument();
    const totals = screen.getByRole("region", { name: "Totals" });
    expect(totals).toHaveTextContent("In a flood-prone area1");
    expect(within(totals).getByRole("row", { name: /Community A/ })).toHaveTextContent("Community A61");
  });

  it("lets a person confirm or reject an inferred link", async () => {
    const api = backend({ "POST /api/relationships/1/confirm/": () => ({ body: link(1, { method: "confirmed" }) }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/relations" });
    const section = await screen.findByRole("region", { name: "Links" });
    const row = (await within(section).findByText("B-001")).closest("tr")!;
    expect(row).toHaveTextContent("Inferred (71% sure)");
    expect(row).toHaveTextContent("7 m away");
    await userEvent.click(within(row).getByRole("button", { name: "Confirm B-001 is connected to D-001" }));
    await waitFor(() => expect(api.calls.some((c) => c.path === "/api/relationships/1/confirm/")).toBe(true));
  });

  it("runs the procedures on request", async () => {
    const api = backend({ "POST /api/projects/5/relations/run/": () => ({ status: 201, body: run }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/relations" });
    await userEvent.click(await screen.findByRole("button", { name: "Run now" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "POST" && c.path === "/api/projects/5/relations/run/")).toBe(true));
  });

  it("describes a breach in plain words", () => {
    const breach = link(2, { type: "violates", object: null, rule: "setback", method: "calculated", details: { measured_m: 0.5, required_m: 3, zone: "default" } });
    expect(describeLink(breach)).toBe("Too close to the plot boundary: 0.5 m, needs 3 m (default standard)");
  });
});

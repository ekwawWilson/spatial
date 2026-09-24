import type { Checklist, ChecklistItem, Layer, Project } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { bindChoices, type LayerChoice } from "../components/workspace/ImportWizard";
import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

vi.mock("../components/map/MapView", () => ({ MapView: () => <div data-testid="map" />, GEOJSON_LIMIT: 2000 }));

beforeEach(() => localStorage.clear());

const crsBrief = { id: 1, code: "EPSG:2136", name: "Accra / Ghana National Grid", units: "Gold Coast foot", kind: "projected" as const };

const project = {
  id: 5,
  name: "Kasoa local plan",
  community: "Kasoa",
  description: "",
  crs: 1,
  crs_detail: crsBrief,
  status: "draft",
  layer_count: 0,
  created_at: "",
  updated_at: "",
} as unknown as Project;

function item(id: number, extra: Partial<ChecklistItem> = {}): ChecklistItem {
  return {
    id,
    group: "existing",
    key: `item-${id}`,
    title: `Item ${id}`,
    description: "",
    kind: "document",
    domain: "",
    geometry_type: "",
    rules: {},
    status: "not_started",
    owner: null,
    owner_name: null,
    due_date: null,
    notes: "",
    linked_layer: null,
    attachments: [],
    metrics: null,
    checks: [],
    rules_met: true,
    complete: false,
    blockers: [],
    ...extra,
  };
}

const streets = item(7, {
  key: "streets",
  title: "Streets and access",
  kind: "layer",
  domain: "D",
  geometry_type: "line",
  rules: { min_features: 1 },
  checks: [{ ok: false, label: "Layer linked", problem: "No layer linked yet: import, draw or pick one." }],
  rules_met: false,
});

const checklist: Checklist = {
  project: 5,
  project_name: "Kasoa local plan",
  score: 5,
  complete: 1,
  total: 2,
  groups: [{ group: "existing", label: "4. Existing situation", total: 2, complete: 1 }],
  items: [item(3, { title: "Population data", status: "ready", complete: true }), streets],
  blockers: [{ item: 7, title: "Streets and access", problem: "Overdue since 2026-01-01." }],
};

const streetsLayer = {
  id: 30,
  project: 5,
  name: "Streets and access",
  domain: "D",
  geometry_type: "line",
  crs: 1,
  crs_detail: crsBrief,
  schema: [],
  style: { kind: "single", fill: "#000", stroke: "#000", stroke_width: 1, point_radius: 4, fill_opacity: 0.4, label_field: null },
  order: 1,
  visible: true,
  opacity: 1,
  source: "drawn",
  feature_count: 0,
  created_at: "",
  updated_at: "",
} as unknown as Layer;

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/projects/5/checklist/": () => ({ body: checklist }),
    "GET /api/memberships/": () => ({ body: { count: 0, next: null, previous: null, results: [] } }),
    ...extra,
  });
}

describe("checklist page", () => {
  it("shows the score, group progress and blockers", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5/checklist" });
    expect(await screen.findByLabelText("Readiness score")).toHaveTextContent("5%");
    expect(screen.getByRole("progressbar", { name: "4. Existing situation" })).toHaveAttribute("aria-valuenow", "50");
    expect(within(screen.getByRole("region", { name: "Blockers" })).getByText(/Overdue since 2026-01-01/)).toBeInTheDocument();
  });

  it("changes an item's status and explains a refusal", async () => {
    const api = backend({
      "PATCH /api/checklist-items/7/": () => ({ status: 400, body: { status: ["Covers 40% of the planning area; needs 80%."] } }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/checklist" });
    await userEvent.selectOptions(await screen.findByLabelText("Status of Streets and access"), "ready");
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ status: "ready" });
    expect(await screen.findByText(/Covers 40% of the planning area/)).toBeInTheDocument();
  });

  it("offers import, export, draw and a disabled send-to-field on layer items", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5/checklist" });
    await userEvent.click(await screen.findByRole("button", { name: "Streets and access", expanded: false }));
    const actions = screen.getByRole("group", { name: "Actions" });
    expect(within(actions).getByRole("button", { name: "Import" })).toBeEnabled();
    expect(within(actions).getByRole("button", { name: "Export" })).toBeDisabled(); // no layer yet
    expect(within(actions).getByRole("button", { name: "Draw" })).toBeEnabled();
    expect(within(actions).getByRole("button", { name: "Send to field" })).toBeDisabled();
  });

  it("draw creates the item's layer and opens the workspace drawing on it", async () => {
    let layers: Layer[] = [];
    const api = backend({
      "POST /api/checklist-items/7/create-layer/": () => {
        layers = [streetsLayer];
        return { status: 201, body: { ...streets, linked_layer: 30, layer: 30 } };
      },
      "GET /api/projects/5/": () => ({ body: project }),
      "GET /api/layers/": () => ({ body: layers }),
      "GET /api/crs/systems/": () => ({ body: [] }),
      "GET /api/basemaps/": () => ({ body: [] }),
      "GET /api/projects/5/boundary/": () => ({ body: { exists: false } }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/checklist" });
    await userEvent.click(await screen.findByRole("button", { name: "Streets and access", expanded: false }));
    await userEvent.click(screen.getByRole("button", { name: "Draw" }));
    const editing = await screen.findByRole("region", { name: "Editing" });
    expect(editing).toHaveTextContent("Editing Streets and access");
    await waitFor(() => expect(within(editing).getByRole("button", { name: "Draw" })).toHaveAttribute("aria-pressed", "true"));
  });
});

describe("import binding", () => {
  const choice = (name: string): LayerChoice => ({
    include: true,
    plan: { source: name, crs: "EPSG:2136", crs_confirmed: true, new_layer: { name, domain: "other", geometry_type: "point" }, fields: [] },
  });

  it("sends the first source layer to a new layer named after the item, and leaves the rest out", () => {
    const [first, second] = bindChoices([choice("a"), choice("b")], { title: "Streets and access", layerId: null, domain: "D", geometryType: "line" });
    expect(first!.plan.new_layer).toEqual({ name: "Streets and access", domain: "D", geometry_type: "line" });
    expect(second!.include).toBe(false);
  });

  it("targets the item's linked layer when it has one", () => {
    const [first] = bindChoices([choice("a")], { title: "Streets", layerId: 30, domain: "D" });
    expect(first!.plan.target_layer).toBe(30);
    expect(first!.plan.new_layer).toBeUndefined();
  });
});

describe("readiness page", () => {
  it("lists the district's projects with their scores", async () => {
    const api = backend({
      "GET /api/readiness/": () => ({
        body: { score: 40, projects: [{ project: 5, name: "Kasoa local plan", status: "draft", score: 40, complete: 8, total: 21, groups: [], blockers: [] }] },
      }),
      "GET /api/readiness/template/": () => ({ body: { id: 1, name: "Platform default", own: false, items: [] } }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/readiness" });
    expect(await screen.findByLabelText("District readiness")).toHaveTextContent("40%");
    expect(screen.getByRole("link", { name: "Kasoa local plan" })).toHaveAttribute("href", "/projects/5/checklist");
    expect(await screen.findByRole("button", { name: "Customise for this district" })).toBeInTheDocument();
  });
});

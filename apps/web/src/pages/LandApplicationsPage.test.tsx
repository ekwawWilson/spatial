import type { LandApplication, LandClock, LandRegistry, LandSummary } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const registry: LandRegistry = {
  kinds: [
    { code: "rezoning", label: "Re-zoning", form: "33A and 33B", rule: "r.33; Act 925 s.93", comment_days: 28, decide_days: 60, decide_rule: "r.33(15)", steps: [] },
    { code: "change_of_use", label: "Change of use", form: "", rule: "r.34; r.44(1)", comment_days: 0, decide_days: 30, decide_rule: "r.44(10)", steps: [] },
    { code: "subdivision", label: "Subdivision of land", form: "46", rule: "r.54; Act 925 s.139", comment_days: 14, decide_days: 60, decide_rule: "r.54(9)", steps: [] },
  ],
  grounds: [
    { code: "structure_plan", label: "To make the zoning of the land comply with the structure plan" },
    { code: "special", label: "A special circumstance has arisen that necessitates the change" },
  ],
  circumstances: [{ code: "demographics", label: "A change in the demographic pattern in the area" }],
  use_tests: [
    { code: "permissible", label: "Is within the permissible uses of the zoning scheme", rule: "r.34(1)(a)" },
    { code: "traffic", label: "Does not significantly increase traffic generation", rule: "r.34(1)(d)(i)" },
  ],
  comment_kinds: [
    { code: "comment", label: "Comment" },
    { code: "objection", label: "Objection" },
  ],
  deferred_decision_days: 30,
};

function clock(code: string, label: string, extra: Partial<LandClock> = {}): LandClock {
  return { code, label, rule: "r.33(5)(a)-(b)", days: 7, due_on: "2026-09-08", done_on: null, note: "", late: false, overdue: false, ...extra };
}

function summary(id: number, extra: Partial<LandSummary> = {}): LandSummary {
  return {
    id,
    project: 5,
    number: `SMA/RZ/2026/000${id}`,
    kind: "rezoning",
    kind_label: "Re-zoning",
    applicant_name: "Ama Mensah",
    summary: "",
    status: "received",
    status_label: "Being considered",
    received_on: "2026-09-01",
    decided_on: null,
    comments_close_on: null,
    next_step: clock("display", "Displayed in the Public Data Room and on the Assembly's notice board", { overdue: true }),
    ...extra,
  };
}

function full(extra: Partial<LandApplication> = {}): LandApplication {
  return {
    ...summary(1),
    summary: "the re-zoning of P-002 from residential to Re B",
    form: "33A and 33B",
    rule: "r.33; Act 925 s.93",
    applicant_phone: "0240000000",
    applicant_email: "",
    applicant_address: "",
    description: "",
    parcels: [{ id: 21, label: "P-002", zone: "residential", area_m2: 900 }],
    abutting: [
      { id: 20, label: "P-001", owner: "Kofi Antwi", area_m2: 900 },
      { id: 22, label: "P-003", owner: "", area_m2: 900 },
    ],
    current_zone: "residential",
    proposed_zone: "Re B",
    ground: "structure_plan",
    circumstance: "",
    current_use: "",
    proposed_use: "",
    lots: null,
    zone: { value: "residential", national: null, name: null, prohibited_uses: [] },
    assessment: {},
    clocks: [
      clock("display", "Displayed in the Public Data Room and on the Assembly's notice board", { overdue: true }),
      clock("posted", "Notice posted at three places near the land", { rule: "r.33(12)", days: null, due_on: null }),
      clock("decide", "Decision", { rule: "r.33(15)", days: null, due_on: null }),
    ],
    comment_rule: "r.33(7)",
    comments: [],
    deferred_on: null,
    defer_reason: "",
    conditions: "",
    reasons: "",
    applied_on: null,
    papers: [
      { code: "notice", label: "Public notice of the application" },
      { code: "abutting", label: "Notice to the owners of abutting land" },
    ],
    ...extra,
  };
}

function backend(item: LandApplication, routes: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/land/registry/": () => ({ body: registry }),
    "GET /api/land/applications/": () => ({ body: { results: [summary(1), summary(2, { status: "approved", status_label: "Approved", next_step: null })], summary: { total: 2, open: 1, overdue: 1 } } }),
    "GET /api/land/applications/1/": () => ({ body: item }),
    "GET /api/projects/5/layer-roles/": () => ({ body: { roles: [{ role: "parcels", layer: 8, config: { id_field: "parcel_id" }, suggested: null }] } }),
    "GET /api/layers/8/features/": () => ({ body: { type: "FeatureCollection", features: [{ type: "Feature", id: 21, geometry: null, properties: { parcel_id: "P-002" } }], total: 1, next_offset: null } }),
    ...routes,
  });
}

describe("re-zoning, change of use and subdivision", () => {
  it("lists a project's applications with what is overdue, and receives a re-zoning for a parcel", async () => {
    const api = backend(full(), { "POST /api/land/applications/": () => ({ status: 201, body: full() }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/land" });
    const table = await screen.findByRole("table", { name: "Applications" });
    expect(within(table).getByText("SMA/RZ/2026/0001").closest("tr")).toHaveTextContent("overdue since 2026-09-08");
    expect(screen.getByLabelText("Summary")).toHaveTextContent("With a step overdue1");

    await userEvent.click(screen.getByRole("button", { name: "Receive an application" }));
    const form = screen.getByRole("form", { name: "Receive an application" });
    await userEvent.type(within(form).getByLabelText("Applicant"), "Ama Mensah");
    await userEvent.type(within(form).getByLabelText("Parcel ids"), "P-002");
    await userEvent.type(within(form).getByLabelText("Zone asked for"), "Re B");
    await userEvent.selectOptions(within(form).getByLabelText("Why"), "special");
    await waitFor(() => expect(within(form).getByRole("button", { name: "Receive the application" })).toBeEnabled());
    await userEvent.click(within(form).getByRole("button", { name: "Receive the application" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "POST")).toBe(true));
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({
      project: 5,
      kind: "rezoning",
      applicant_name: "Ama Mensah",
      parcels: [21],
      proposed_zone: "Re B",
      ground: "special",
      circumstance: "demographics",
    });
    // On to the application itself.
    expect(await screen.findByRole("heading", { level: 1, name: /SMA\/RZ\/2026\/0001/ })).toBeInTheDocument();
  });

  it("shows each step with its rule and date, the abutting owners, and records a step", async () => {
    const displayed = full({ clocks: [clock("display", "Displayed in the Public Data Room and on the Assembly's notice board", { done_on: "2026-09-05", note: "Notice board" })], comments_close_on: "2026-10-03" });
    const api = backend(full(), { "POST /api/land/applications/1/step/": () => ({ body: displayed }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/land/1" });
    const steps = await screen.findByRole("region", { name: "Steps and deadlines" });
    expect(within(steps).getByText(/Displayed in the Public Data Room/).closest("tr")).toHaveTextContent("r.33(5)(a)-(b): 7 daysOverdue since 2026-09-08");
    expect(within(steps).getByText("Notice posted at three places near the land").closest("tr")).toHaveTextContent("No time set");
    // The decision is not a step to tick off.
    expect(within(steps).queryByRole("button", { name: "Done today: Decision" })).not.toBeInTheDocument();
    const abutting = screen.getByRole("region", { name: "Abutting land" });
    expect(abutting).toHaveTextContent("P-001: Kofi Antwi");
    expect(abutting).toHaveTextContent("P-003: owner not on record");

    await userEvent.type(within(steps).getByLabelText(/^Note for: Displayed/), "Notice board");
    await userEvent.click(within(steps).getByRole("button", { name: /^Done today: Displayed/ }));
    expect(await screen.findByRole("status")).toHaveTextContent("Step recorded.");
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({ step: "display", note: "Notice board" });
    expect(screen.getByLabelText("Application")).toHaveTextContent("until 2026-10-03 (r.33(7))");
    expect(within(screen.getByRole("region", { name: "Steps and deadlines" })).getByText(/Displayed in the Public Data Room/).closest("tr")).toHaveTextContent("Done 2026-09-05");
  });

  it("records an objection and the decision, then writes an approved zone to the map", async () => {
    const objected = full({ comments: [{ id: 3, kind: "objection", kind_label: "Objection", name: "Kojo Antwi", contact: "", text: "Traffic.", received_on: "2026-09-20", response: "", responded_on: null }] });
    const approved = full({ status: "approved", status_label: "Approved", decided_on: "2026-10-10", conditions: "Three storeys at most." });
    const api = backend(full(), {
      "POST /api/land/applications/1/comments/": () => ({ status: 201, body: objected }),
      "POST /api/land/applications/1/decide/": () => ({ body: approved }),
      "POST /api/land/applications/1/apply/": () => ({ body: { written: { parcels_changed: 1, field: "land_use", zoning_layer: true }, application: { ...approved, applied_on: "2026-10-11" } } }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/land/1" });
    const record = await screen.findByRole("form", { name: "Record a comment" });
    await userEvent.type(within(record).getByLabelText("From"), "Kojo Antwi");
    await userEvent.type(within(record).getByLabelText("What it says"), "Traffic.");
    await userEvent.click(within(record).getByRole("button", { name: "Record it" }));
    expect(await screen.findByText(/Kojo Antwi: Traffic\./)).toBeInTheDocument();
    expect(api.calls.find((c) => c.path.endsWith("/comments/"))!.body).toEqual({ kind: "objection", name: "Kojo Antwi", contact: "", text: "Traffic." });

    const decision = screen.getByRole("form", { name: "Decision" });
    await userEvent.type(within(decision).getByLabelText("Conditions"), "Three storeys at most.");
    await userEvent.click(within(decision).getByRole("button", { name: "Record the decision" }));
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Approved"));
    expect(api.calls.find((c) => c.path.endsWith("/decide/"))!.body).toEqual({ approve: true, conditions: "Three storeys at most." });
    expect(screen.queryByRole("form", { name: "Decision" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Write Re B to the map" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Zone written to 1 parcel(s). This project also has a zoning layer: redraw the zone there too.");
    expect(screen.getByRole("region", { name: "On the map" })).toHaveTextContent("was written to the parcels on 2026-10-11");
  });

  it("assesses a change of use against r.34, and keeps the decision from those who may not make it", async () => {
    const use = full({ kind: "change_of_use", kind_label: "Change of use", form: "", rule: "r.34; r.44(1)", abutting: [], papers: [], clocks: [clock("decide", "Decision", { rule: "r.44(10)", days: null })] });
    const api = backend(use, { "POST /api/land/applications/1/assess/": () => ({ body: { ...use, assessment: { traffic: { met: false, note: "" } } } }) });
    const view = renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/land/1" });
    const tests = await screen.findByRole("form", { name: "Tests of r.34" });
    await userEvent.selectOptions(within(tests).getByLabelText("Does not significantly increase traffic generation"), "not");
    await userEvent.click(within(tests).getByRole("button", { name: "Save the assessment" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Assessment saved.");
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({ answers: { traffic: { met: false, note: "" } } });
    expect(screen.queryByRole("region", { name: "Abutting land" })).not.toBeInTheDocument();
    view.unmount();

    const planner = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "planner", permissions: ["district.view", "project.view", "permit.view", "permit.process"] }] });
    renderApp(backend(full(), { "GET /api/auth/me/": () => ({ body: planner }) }).fetch, { tokens: signedIn, route: "/projects/5/land/1" });
    expect(await screen.findByRole("form", { name: "Record a comment" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Decision" })).not.toBeInTheDocument();
  });
});

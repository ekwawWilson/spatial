import type { AddressProposal } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const proposal: AddressProposal = {
  method: "decametric",
  method_label: "By distance, every 10 m",
  odd_side: "left",
  start_near: null,
  streets: 3,
  streets_without_a_name: 1,
  new_street_codes: [{ street: 9, code: "SMA-004" }],
  properties: 7,
  numbered: 6,
  without_a_street: 1,
  changes: 6,
  truncated: false,
  rows: [
    { property: 1, label: "B-001", street: 4, street_name: "Main Street", street_code: "SMA-001", side: "left", distance_m: 535, off_street_m: 13, number: "53", address: "53 Main Street", current: "" },
    { property: 4, label: "B-004", street: 4, street_name: "Main Street", street_code: "SMA-001", side: "right", distance_m: 535, off_street_m: 13, number: "54", address: "54 Main Street", current: "12" },
  ],
  methods: { decametric: "By distance, every 10 m", metric: "By distance, every metre", sequential: "One after another along the street" },
};

describe("street addressing", () => {
  it("shows the proposal, what is missing, and re-proposes when the convention changes", async () => {
    const api = fakeBackend({ "GET /api/auth/me/": () => ({ body: makeMe() }), "GET /api/projects/5/addressing/": () => ({ body: proposal }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/addressing" });
    const table = await screen.findByRole("table", { name: "Proposed addresses" });
    expect(within(table).getByText("B-001").closest("tr")).toHaveTextContent("Main StreetSMA-00153B-001left535 m—");
    expect(within(table).getByText("B-004").closest("tr")).toHaveTextContent("12"); // its number on the map now, which would change
    const summary = screen.getByLabelText("Summary");
    expect(summary).toHaveTextContent("3, 1 to be given a code, 1 without a name");
    expect(summary).toHaveTextContent("6 of 7");
    await userEvent.selectOptions(screen.getByLabelText("Odd numbers on the"), "right");
    await waitFor(() => expect(api.calls.at(-1)!.path).toBe("/api/projects/5/addressing/?method=decametric&odd_side=right"));
  });

  it("writes to the map only when applied, and only for those who may", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const api = fakeBackend({
      "GET /api/auth/me/": () => ({ body: makeMe() }),
      "GET /api/projects/5/addressing/": () => ({ body: proposal }),
      "POST /api/projects/5/addressing/": () => ({ body: { written: { streets: 1, properties: 6 }, numbered: 6 } }),
    });
    const view = renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/addressing" });
    await userEvent.click(await screen.findByRole("button", { name: "Apply to the map" }));
    expect(await screen.findByRole("status")).toHaveTextContent("6 property number(s) and 1 street code(s) changed");
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({ method: "decametric", odd_side: "left" });
    view.unmount();

    const viewer = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "viewer", permissions: ["district.view", "project.view"] }] });
    renderApp(fakeBackend({ "GET /api/auth/me/": () => ({ body: viewer }), "GET /api/projects/5/addressing/": () => ({ body: proposal }) }).fetch, { tokens: signedIn, route: "/projects/5/addressing" });
    expect(await screen.findByRole("button", { name: "Download the schedule (CSV)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply to the map" })).not.toBeInTheDocument();
  });
});

describe("street names", () => {
  it("takes a name from proposal through consultation to approval", async () => {
    const proposed = { id: 3, project: 5, street: 41, name: "Yaa Asantewaa Avenue", basis: "", proposed_by: "", proposed_on: "2026-10-21", consulted_on: null, consultation: "", decided_on: null, decision_note: "", published_on: null, signs_on: null, previous_name: "", status: "proposed" as const, status_label: "Proposed", clashes: [] };
    const consulted = { ...proposed, status: "consulted" as const, consulted_on: "2026-10-21" };
    const approved = { ...consulted, status: "approved" as const, decided_on: "2026-10-21", previous_name: "Market Road" };
    const api = fakeBackend({
      "GET /api/auth/me/": () => ({ body: makeMe() }),
      "GET /api/projects/5/addressing/": () => ({ body: proposal }),
      "GET /api/street-names/": () => ({ body: { results: [] } }),
      "GET /api/projects/5/layer-roles/": () => ({ body: { roles: [{ role: "streets", layer: 8, config: {}, suggested: null }] } }),
      "GET /api/layers/8/features/": () => ({ body: { type: "FeatureCollection", features: [{ type: "Feature", id: 41, geometry: null, properties: { name: "Market Road" } }], next_offset: null } }),
      "POST /api/street-names/": () => ({ status: 201, body: proposed }),
      "POST /api/street-names/3/consult/": () => ({ body: consulted }),
      "POST /api/street-names/3/decide/": () => ({ body: approved }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/addressing" });
    const form = await screen.findByRole("form", { name: "Propose a street name" });
    await waitFor(() => expect(within(form).getByRole("option", { name: "Market Road" })).toBeInTheDocument());
    await userEvent.selectOptions(within(form).getByLabelText("Street"), "41");
    await userEvent.type(within(form).getByLabelText("Proposed name"), "Yaa Asantewaa Avenue");
    await userEvent.click(within(form).getByRole("button", { name: "Propose" }));
    const names = await screen.findByRole("table", { name: "Names" });
    expect(api.calls.find((c) => c.path === "/api/street-names/" && c.method === "POST")!.body).toEqual({ project: 5, street: 41, name: "Yaa Asantewaa Avenue", basis: "", proposed_by: "" });
    await userEvent.click(within(names).getByRole("button", { name: "Consulted" }));
    await userEvent.click(await within(names).findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Yaa Asantewaa Avenue approved and written to the map.")).toBeInTheDocument();
    expect(within(names).getByText("Market Road")).toBeInTheDocument(); // its old name
  });
});

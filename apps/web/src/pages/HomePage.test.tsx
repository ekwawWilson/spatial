import type { WorkItem, WorkList } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

function item(overrides: Partial<WorkItem>): WorkItem {
  return {
    kind: "permit",
    kind_label: "Permit application",
    id: 7,
    project: 5,
    number: "SMA/DP/2026/0007",
    title: "Erection of a building or structure",
    who: "Kofi Boateng",
    step: "Acknowledge receipt in writing",
    rule: "r.44(6)",
    due_on: "2026-10-01",
    days: -5,
    overdue: true,
    officer: null,
    assignable: true,
    link: "/projects/5/permits/7",
    ...overrides,
  };
}

const work: WorkList = {
  counts: { overdue: 1, this_week: 1, mine: 1, unassigned: 1, all: 3 },
  items: [
    item({}),
    item({ kind: "case", kind_label: "Enforcement case", id: 3, number: "SMA/EN/2026/0003", title: "Development without a permit", step: "Serve a notice", rule: "", due_on: "2026-10-08", days: 2, overdue: false, officer: { id: 1, name: "Ama Mensah" }, link: "/projects/5/enforcement/3" }),
    item({ kind: "request", kind_label: "Request for information", id: 4, number: "SMA/IR/2026/0004", title: "Zoning of plot 12", who: null, step: "Answer the request", rule: "r.64(7)", due_on: null, days: null, overdue: false, assignable: false, link: "/data-room" }),
  ],
  setup: [
    { code: "crs", label: "Choose the district's coordinate system", done: true, link: "/crs", hint: "" },
    { code: "staff", label: "Add the planning staff", done: false, link: "/members", hint: "Planners and field officers." },
  ],
};

function backend(data: WorkList = work) {
  const assigned: unknown[] = [];
  const fake = fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/work/": () => ({ body: data }),
    "GET /api/work/officers/": () => ({ body: [{ id: 1, name: "Ama Mensah", role: "district_admin" }, { id: 2, name: "Yaw Darko", role: "field_officer" }] }),
    "POST /api/work/assign/": (body) => (assigned.push(body), { body: { kind: "permit", id: 7, officer: { id: 2, name: "Yaw Darko" } } }),
    "GET /api/search/": () => ({ body: { q: "0007", results: [{ kind: "permit", kind_label: "Permit application", id: 7, title: "SMA/DP/2026/0007", detail: "Received", link: "/projects/5/permits/7" }] } }),
  });
  return { ...fake, assigned };
}

describe("home: the day's work", () => {
  it("opens on the records assigned to me, and filters by what is late or due", async () => {
    renderApp(backend().fetch, { tokens: signedIn });
    const list = await screen.findByRole("region", { name: "Your work" });
    // My records first: only the case handed to me.
    expect(within(list).getByRole("button", { name: /Assigned to me/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByRole("link", { name: /SMA\/EN\/2026\/0003/ })).toHaveAttribute("href", "/projects/5/enforcement/3");
    expect(list).toHaveTextContent("Due in 2 days");

    await userEvent.click(within(list).getByRole("button", { name: /Late/ }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(list).toHaveTextContent("5 days late");
    expect(list).toHaveTextContent("Kofi Boateng");

    await userEvent.click(within(list).getByRole("button", { name: /Everything/ }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(list).toHaveTextContent("No date");
    await userEvent.selectOptions(within(list).getByRole("combobox", { name: "Kind of record" }), "Requests for information");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("hands a record to an officer from the list", async () => {
    const fake = backend();
    renderApp(fake.fetch, { tokens: signedIn });
    const list = await screen.findByRole("region", { name: "Your work" });
    await userEvent.click(within(list).getByRole("button", { name: /Late/ }));
    const picker = within(list).getByRole("combobox", { name: "Officer for the application" });
    await waitFor(() => expect(within(picker).getByRole("option", { name: "Yaw Darko" })).toBeInTheDocument());
    await userEvent.selectOptions(picker, "2");
    await waitFor(() => expect(fake.assigned).toEqual([{ kind: "permit", id: 7, officer: 2 }]));
  });

  it("shows the administrator what the district still has to set up", async () => {
    renderApp(backend().fetch, { tokens: signedIn });
    const setup = await screen.findByRole("region", { name: "Setting up the district" });
    expect(setup).toHaveTextContent("1 of 2 done");
    expect(within(setup).getByRole("link", { name: "Add the planning staff" })).toHaveAttribute("href", "/members");
  });

  it("says when nothing is waiting", async () => {
    renderApp(backend({ counts: { overdue: 0, this_week: 0, mine: 0, unassigned: 0, all: 0 }, items: [], setup: null }).fetch, { tokens: signedIn });
    const list = await screen.findByRole("region", { name: "Your work" });
    expect(list).toHaveTextContent("Nothing is waiting");
    expect(screen.queryByRole("region", { name: "Setting up the district" })).not.toBeInTheDocument();
  });
});

describe("quick search", () => {
  it("finds a record by number and goes to it", async () => {
    renderApp(backend().fetch, { tokens: signedIn });
    const box = await screen.findByRole("combobox", { name: "Search the district" });
    await userEvent.type(box, "0007");
    const results = await screen.findByRole("listbox", { name: "Search results" });
    expect(within(results).getByRole("option")).toHaveTextContent("Permit application");
    await userEvent.keyboard("{Enter}");
    // The permit page asks for the application.
    await waitFor(() => expect(screen.queryByRole("listbox", { name: "Search results" })).not.toBeInTheDocument());
  });
});

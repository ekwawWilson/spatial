import type { Meeting } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const committees = {
  committees: [
    { kind: "dspc", label: "District Spatial Planning Committee", members: [] },
    { kind: "tsc", label: "Technical Sub-Committee", members: [{ name: "Kofi Boateng", office: "physical_planning" }, { name: "Esi Owusu", office: "development_planning" }] },
  ],
  offices: [
    { code: "physical_planning", label: "Head of the Physical Planning Department" },
    { code: "development_planning", label: "District Development Planning Officer" },
  ],
  outcomes: [
    { code: "", label: "Not yet considered" },
    { code: "recommend_grant", label: "Recommended for grant" },
  ],
};

const meeting: Meeting = {
  id: 7,
  committee: "tsc",
  committee_label: "Technical Sub-Committee",
  held_on: "2026-10-30",
  venue: "Assembly Hall",
  items: 1,
  considered: 0,
  notice: { serve_by: "2026-10-27", served_on: null, late: false, overdue: false, rule: "r.6(2)" },
  quorum: { present: 1, needed: 1, missing_offices: ["Head of the Works Department"], met: false, rule: "r.7(3)-(4)" },
  members: committees.committees[1]!.members,
  attendance: ["Kofi Boateng"],
  agenda: [{ type: "permit", ref: 12, project: 5, title: "SMA/DP/2026/0012: Erection of a building or structure, Residential (Kasoa)", outcome: "", minute: "" }],
  notes: "",
};

function backend(routes: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/committees/": () => ({ body: committees }),
    "GET /api/committees/meetings/": () => ({ body: { results: [meeting] } }),
    "GET /api/committees/meetings/7/": () => ({ body: meeting }),
    ...routes,
  });
}

describe("committees", () => {
  it("lists meetings with their notice and quorum, and plans a new one", async () => {
    const api = backend({ "POST /api/committees/meetings/": () => ({ status: 201, body: meeting }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/committees" });
    const table = await screen.findByRole("table", { name: "Meetings" });
    expect(within(table).getByRole("link", { name: "Technical Sub-Committee, 2026-10-30" }).closest("tr")).toHaveTextContent("0 of 1 consideredServe by 2026-10-271 of 1");
    expect(screen.getByRole("region", { name: "Members" })).toHaveTextContent("Kofi Boateng (Head of the Physical Planning Department)");
    const form = screen.getByRole("form", { name: "New meeting" });
    await userEvent.type(within(form).getByLabelText("Date"), "2026-10-30");
    await userEvent.click(within(form).getByRole("button", { name: "Plan the meeting" }));
    expect(await screen.findByRole("heading", { level: 1, name: /Technical Sub-Committee/ })).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({ committee: "tsc", held_on: "2026-10-30", venue: "" });
  });

  it("records attendance and the minute on an item", async () => {
    const attended = { ...meeting, attendance: ["Kofi Boateng", "Esi Owusu"], quorum: { ...meeting.quorum, present: 2, met: true, missing_offices: [] } };
    const api = backend({ "PATCH /api/committees/meetings/7/": (body) => ({ body: { ...attended, ...(body as object) } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/committees/7" });
    expect(await screen.findByLabelText("Meeting")).toHaveTextContent("Not formed: 1 present, 1 needed (r.7(3)-(4))Absent: Head of the Works Department");
    await userEvent.click(screen.getByRole("checkbox", { name: /Esi Owusu/ }));
    await waitFor(() => expect(screen.getByLabelText("Meeting")).toHaveTextContent("Formed: 2 present"));
    expect(api.calls.find((c) => c.method === "PATCH")!.body).toEqual({ attendance: ["Kofi Boateng", "Esi Owusu"] });

    const minutes = screen.getByRole("form", { name: "Agenda and minutes" });
    expect(within(minutes).getByRole("link", { name: /SMA\/DP\/2026\/0012/ })).toHaveAttribute("href", "/projects/5/permits/12");
    await userEvent.selectOptions(within(minutes).getByLabelText("Outcome of item 1"), "recommend_grant");
    await userEvent.type(within(minutes).getByLabelText("Minute of item 1"), "Setbacks met.");
    await userEvent.click(within(minutes).getByRole("button", { name: "Save the minutes" }));
    await waitFor(() => expect(api.calls.filter((c) => c.method === "PATCH").length).toBe(2));
    expect((api.calls.filter((c) => c.method === "PATCH")[1]!.body as { agenda: unknown[] }).agenda[0]).toEqual({ ...meeting.agenda[0], outcome: "recommend_grant", minute: "Setbacks met." });
  });
});

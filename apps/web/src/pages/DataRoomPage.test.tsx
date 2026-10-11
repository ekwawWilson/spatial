import type { DataRoomSettings, InformationRequests } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { emptyPage, fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const closed: DataRoomSettings = { code: "SMA", is_open: false, show_applicants: false, welcome: "", contact: "", updated_at: "" };
const requests: InformationRequests = {
  answer_within_days: 5,
  open: 1,
  overdue: 1,
  results: [{ id: 7, reference: "SMA/IR/2026/0001", name: "Kojo Antwi", phone: "0200000000", email: "", subject: "Plot 14", body: "What is it zoned for?", received_on: "2026-10-01", status: "open", answer: "", answered_on: null, answered_by: null, due_on: "2026-10-06", late: false, overdue: true }],
};

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/dataroom/": () => ({ body: closed }),
    "GET /api/dataroom/publications/": () => ({ body: [] }),
    "GET /api/dataroom/documents/": () => ({ body: [] }),
    "GET /api/dataroom/requests/": () => ({ body: requests }),
    "GET /api/projects/": () => ({ body: { ...emptyPage, count: 1, results: [{ id: 5, name: "Kasoa local plan" }] } }),
    ...extra,
  });
}

describe("data room (staff)", () => {
  it("opens the room and publishes a project", async () => {
    const api = backend({
      "PATCH /api/dataroom/": (body) => ({ body: { ...closed, ...(body as object) } }),
      "POST /api/dataroom/publications/": () => ({ status: 201, body: { id: 1, project: 5, project_name: "Kasoa local plan", permits: true, zoning: true, published_at: "" } }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/data-room" });
    const opening = await screen.findByRole("region", { name: "Opening" });
    expect(await within(opening).findByText(/closed online/)).toBeInTheDocument();
    await userEvent.click(within(opening).getByRole("button", { name: "Open the room online" }));
    expect(await within(opening).findByRole("link", { name: "/public/SMA" })).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")!.body).toEqual({ is_open: true });

    const publish = screen.getByRole("form", { name: "Publish a project" });
    await userEvent.selectOptions(await within(publish).findByLabelText("Project to publish"), "5");
    await userEvent.click(within(publish).getByRole("button", { name: "Publish" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ project: 5 }));
  });

  it("shows requests past their five days and records the answer", async () => {
    const api = backend({ "POST /api/dataroom/requests/7/answer/": () => ({ body: { ...requests.results[0], status: "answered" } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/data-room" });
    const section = await screen.findByRole("region", { name: "Requests for information" });
    expect(await within(section).findByText(/1 past their five days/)).toBeInTheDocument();
    const item = within(section).getByRole("article", { name: "SMA/IR/2026/0001" });
    expect(item).toHaveTextContent("overdue since 2026-10-06");
    expect(within(item).getByRole("button", { name: "Record the answer" })).toBeDisabled();
    await userEvent.type(within(item).getByLabelText("Answer to SMA/IR/2026/0001"), "Re B, medium density.");
    await userEvent.click(within(item).getByRole("button", { name: "Record the answer" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ answer: "Re B, medium density.", declined: false }));
  });

  it("lets a viewer see what is published, but not change it or read people's requests", async () => {
    const viewer = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "viewer", permissions: ["district.view", "project.view", "dataroom.view"] }] });
    renderApp(backend({ "GET /api/auth/me/": () => ({ body: viewer }) }).fetch, { tokens: signedIn, route: "/data-room" });
    expect(await screen.findByRole("region", { name: "Opening" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open the room online" })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Publish a project" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Requests for information" })).not.toBeInTheDocument();
  });
});

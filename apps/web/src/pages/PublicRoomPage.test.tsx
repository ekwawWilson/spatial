import type { PublicRoom, RegisterEntry } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeBackend } from "../test/fakeBackend";
import { renderApp } from "../test/render";

const room: PublicRoom = {
  code: "SMA",
  assembly: "Sample Municipal Assembly",
  welcome: "Welcome to the data room.",
  contact: "Room 4, Assembly block\n8am to 5pm",
  answer_within_days: 5,
  fees: [{ label: "Processing fee, development permit", stage: "processing", kind: "development", amount: "150.00" }],
  documents: [{ id: 3, kind: "notice", kind_label: "Notice", title: "Draft local plan for Kasoa", description: "", name: "kasoa.pdf", size: 2_400_000, display_from: "2026-10-01", display_until: "2026-11-30" }],
  zoning_schemes: [{ name: "Kasoa zoning scheme", status: "Approved", approved_on: "2026-08-01", effective_on: null, locality: "Kasoa" }],
};

const entry = (number: string, extra: Partial<RegisterEntry> = {}): RegisterEntry => ({
  number,
  permit: "Development permit",
  for: "Erection of a building or structure",
  proposed_use: "Residential",
  locality: "Kasoa",
  applicant: null,
  status: "Permit issued",
  received_on: "2026-09-01",
  decided_on: "2026-09-20",
  issued_on: "2026-09-25",
  expires_on: "2031-09-25",
  expired: false,
  reasons: "",
  ...extra,
});

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/public/rooms/SMA/": () => ({ body: room }),
    "GET /api/public/rooms/SMA/register/": () => ({ body: { results: [entry("SMA/DP/2026/0001"), entry("SMA/DP/2026/0002", { status: "Refused", issued_on: null, expires_on: null, reasons: "In the road reservation." })] } }),
    ...extra,
  });
}

describe("public data room", () => {
  it("shows the register, the documents and the office to anyone, with no sign-in and no names", async () => {
    const api = backend();
    renderApp(api.fetch, { route: "/public/SMA" });
    expect(await screen.findByRole("heading", { name: "Sample Municipal Assembly: Public Data Room" })).toBeInTheDocument();
    const register = screen.getByRole("region", { name: "Register of permits" });
    const issued = (await within(register).findByText("SMA/DP/2026/0001")).closest("tr")!;
    expect(issued).toHaveTextContent("issued 2026-09-25; valid until 2031-09-25");
    expect(within(register).getByText("SMA/DP/2026/0002").closest("tr")).toHaveTextContent("Grounds: In the road reservation.");
    expect(within(register).queryByText("Issued to")).not.toBeInTheDocument(); // the Assembly hasn't chosen to name people
    const plans = screen.getByRole("region", { name: "Plans and notices" });
    expect(within(plans).getByRole("link", { name: "Draft local plan for Kasoa" })).toHaveAttribute("href", "/api/public/rooms/SMA/documents/3/");
    expect(plans).toHaveTextContent("Notice, 2.3 MB, on display until 2026-11-30");
    expect(plans).toHaveTextContent("Kasoa zoning scheme (Kasoa): approved on 2026-08-01");
    expect(screen.getByRole("region", { name: "Fees" })).toHaveTextContent("GHS 150.00");
    expect(api.calls.every((c) => c.headers.get("Authorization") === null)).toBe(true);
  });

  it("answers 'what can I build here?' from coordinates", async () => {
    const zone = { found: true, zone: "ReB", from: "the zoning scheme", locality: "Kasoa", code: "Re B", name: "Residential Zone B: medium density", colour: "#E5AA70", permitted: ["Local shop"], prohibited: ["Gas filling stations"], standard: { min_setback_m: null, front_setback_m: 6, side_setback_m: 3, rear_setback_m: 3, min_floors: null, max_floors: 3, max_coverage_pct: 50, min_plot_m2: 647, min_width_m: 15.2 }, note: "Every development needs a permit." };
    const api = backend({ "GET /api/public/rooms/SMA/zone/": () => ({ body: zone }) });
    renderApp(api.fetch, { route: "/public/SMA" });
    const section = await screen.findByRole("region", { name: "What can I build here?" });
    await userEvent.type(within(section).getByLabelText("Latitude"), "5.5321");
    await userEvent.type(within(section).getByLabelText("Longitude"), "-0.4250");
    await userEvent.click(within(section).getByRole("button", { name: "Find the zone" }));
    const answer = await within(section).findByRole("status");
    expect(answer).toHaveTextContent("Re B: Residential Zone B: medium density");
    expect(answer).toHaveTextContent("Plot of at least 647 m²");
    expect(answer).toHaveTextContent("Up to 3 storeys");
    expect(answer).toHaveTextContent("6 m at the front, 3 m at the sides, 3 m at the back");
    expect(answer).toHaveTextContent("Gas filling stations");
    expect(api.calls.find((c) => c.path.includes("/zone/"))!.path).toBe("/api/public/rooms/SMA/zone/?lon=-0.425&lat=5.5321");
  });

  it("checks an application by its number and takes a request for information", async () => {
    const api = backend({
      "GET /api/public/rooms/SMA/status/": () => ({ body: { number: "SMA/DP/2026/0014", permit: "Development permit", status: "Pending", received_on: "2026-10-11", decided_on: null, issued_on: null, next_step: { label: "Acknowledge receipt in writing", due_on: "2026-10-18" } } }),
      "POST /api/public/rooms/SMA/requests/": () => ({ status: 201, body: { reference: "SMA/IR/2026/0001", received_on: "2026-10-11", answer_due_on: "2026-10-16" } }),
    });
    renderApp(api.fetch, { route: "/public/SMA" });
    const check = await screen.findByRole("region", { name: "Check an application" });
    await userEvent.type(within(check).getByLabelText("Application number"), "SMA/DP/2026/0014");
    await userEvent.click(within(check).getByRole("button", { name: "Check" }));
    expect(await within(check).findByRole("status")).toHaveTextContent("Development permit: PendingReceived2026-10-11NextAcknowledge receipt in writing, by 2026-10-18");

    const ask = screen.getByRole("region", { name: "Ask for information" });
    await userEvent.type(within(ask).getByLabelText("Your name"), "Kojo Antwi");
    await userEvent.type(within(ask).getByLabelText("Phone"), "0200000000");
    await userEvent.type(within(ask).getByLabelText("About"), "Plot 14");
    await userEvent.type(within(ask).getByLabelText("What you would like to know"), "What is it zoned for?");
    await userEvent.click(within(ask).getByRole("button", { name: "Send the request" }));
    expect(await within(ask).findByRole("status")).toHaveTextContent("Your reference is SMA/IR/2026/0001; expect an answer by 2026-10-16.");
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({ name: "Kojo Antwi", subject: "Plot 14", body: "What is it zoned for?", phone: "0200000000" }));
  });

  it("says so when an Assembly's room isn't open online", async () => {
    renderApp(fakeBackend({}).fetch, { route: "/public/XYZ" });
    expect(await screen.findByRole("alert")).toHaveTextContent("isn't open online");
  });
});

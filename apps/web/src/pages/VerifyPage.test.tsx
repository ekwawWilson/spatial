import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeBackend } from "../test/fakeBackend";
import { renderApp } from "../test/render";

const found = { assembly: "Sample Municipal Assembly", number: "SMA/DP/2026/0001", permit: "Development permit", for: "Erection of a building or structure", applicant: "Ama Mensah", locality: "Kasoa", proposed_use: "Residential", issued_on: "2026-10-21", expires_on: "2031-10-21", valid: true };

describe("permit check (public)", () => {
  it("shows the Assembly's record to anyone holding the certificate, without a sign-in", async () => {
    const api = fakeBackend({ "GET /api/public/permits/abcdefghijklmnopqrstuvwx/": () => ({ body: found }) });
    renderApp(api.fetch, { route: "/verify/abcdefghijklmnopqrstuvwx" });
    expect(await screen.findByRole("heading", { name: "A genuine permit, in force" })).toBeInTheDocument();
    const record = screen.getByRole("region", { name: "Permit" });
    expect(record).toHaveTextContent("SMA/DP/2026/0001");
    expect(record).toHaveTextContent("Ama Mensah");
    expect(record).toHaveTextContent("2031-10-21");
    expect(api.calls[0]!.headers.get("Authorization")).toBeNull();
  });

  it("says so when the permit has expired, or when there is no such permit", async () => {
    const expired = fakeBackend({ "GET /api/public/permits/abcdefghijklmnopqrstuvwx/": () => ({ body: { ...found, valid: false } }) });
    const first = renderApp(expired.fetch, { route: "/verify/abcdefghijklmnopqrstuvwx" });
    expect(await screen.findByRole("heading", { name: "A genuine permit, but it has expired" })).toBeInTheDocument();
    first.unmount();
    renderApp(fakeBackend({}).fetch, { route: "/verify/made-up-code-000000000000" });
    expect(await screen.findByRole("heading", { name: "No such permit" })).toBeInTheDocument();
  });
});

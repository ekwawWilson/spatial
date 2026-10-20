import type { DistrictReturn } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const sample: DistrictReturn = {
  district: { code: "SMA", name: "Sample Municipal Assembly" },
  period: { label: "Quarter 3 of 2026", from: "2026-07-01", to: "2026-09-30" },
  permits: { received: 61, received_by_kind: { development: 55, planning: 6 }, received_by_category: [], decided: 40, granted: 36, refused: 4, issued: 30, decided_within_limit_pct: 87.5, average_days_to_decision: 22.4, limit_days: 30 },
  land: [{ kind: "Re-zoning", received: 2, approved: 1, refused: 0 }],
  enforcement: { cases_opened: 9, opened_by_contravention: [], notices_served: 12, notices_by_kind: [], cases_closed: 5, closed_by_outcome: { rectified: 3, enforced: 1, dropped: 1 }, cost_recovered: "1500.00" },
  plans: { commenced: [], drafts_on_display: ["Kasoa"], approved: [], consultations_held: 3, comments_received: 14 },
  data_room: { requests_received: 6, answered: 6, answered_within_limit_pct: 100 },
  revenue: { bills_issued: 400, billed: "84000.00", paid_on_bills_with_payments: "51000.00", betterment_schemes_completed: 1 },
};

function backend(routes: Parameters<typeof fakeBackend>[0] = {}, me = makeMe()) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: { ...me, memberships: me.memberships.map((m) => ({ ...m, permissions: [...m.permissions, "reports.view"] })) } }),
    "GET /api/reports/returns/": () => ({ body: sample }),
    "GET /api/exchange/keys/": () => ({ body: { keys: [], scopes: { permits: "Permits decided", plans: "Local plans approved", returns: "The return" } } }),
    ...routes,
  });
}

describe("returns and data exchange", () => {
  it("shows the return for a period, and asks again when the period changes", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/returns" });
    const table = await screen.findByRole("table", { name: "The return" });
    expect(within(table).getByText(/Applications received/).closest("tr")).toHaveTextContent("61 (55 / 6)");
    expect(within(table).getByText(/Decided within 30 days/).closest("tr")).toHaveTextContent("87.5%; 22.4");
    expect(within(table).getByText(/Cases closed/).closest("tr")).toHaveTextContent("5: 3 / 1 / 1");
    await userEvent.selectOptions(screen.getByLabelText("Period"), String(new Date().getFullYear()));
    await waitFor(() => expect(api.calls.some((c) => c.path === `/api/reports/returns/?period=${new Date().getFullYear()}`)).toBe(true));
  });

  it("issues a key once, and only administrators manage keys", async () => {
    const made = { id: 4, name: "LUSPA, Accra", prefix: "abcdefghijkl", scopes: ["permits"], created_at: "2026-10-20T10:00:00Z", created_by: "ama@example.test", last_used_at: null, uses: 0, revoked_at: null, key: "SMA.abcdefghijklmnop" };
    const api = backend({ "POST /api/exchange/keys/": () => ({ status: 201, body: made }) });
    const view = renderApp(api.fetch, { tokens: signedIn, route: "/returns" });
    const form = await screen.findByRole("form", { name: "New key" });
    await userEvent.type(within(form).getByLabelText("For"), "LUSPA, Accra");
    await userEvent.click(within(form).getByRole("checkbox", { name: "Local plans approved" }));
    await userEvent.click(within(form).getByRole("button", { name: "Issue the key" }));
    expect(await screen.findByText("SMA.abcdefghijklmnop")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({ name: "LUSPA, Accra", scopes: ["permits", "returns"] });
    view.unmount();

    const planner = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "planner", permissions: ["district.view", "project.view"] }] });
    renderApp(backend({}, planner).fetch, { tokens: signedIn, route: "/returns" });
    await screen.findByRole("table", { name: "The return" });
    expect(screen.queryByRole("region", { name: "Data exchange" })).not.toBeInTheDocument();
  });
});

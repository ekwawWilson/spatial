import type { BettermentScheme, RegisterProperty } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

function prop(id: number, number: string, extra: Partial<RegisterProperty> = {}): RegisterProperty {
  return {
    id,
    project: 5,
    feature: 100 + id,
    number,
    address: "",
    use: "residential",
    use_label: "Residential",
    owner_name: "",
    owner_contact: "",
    valuation_ref: "",
    rateable_value: null,
    valued_on: null,
    revenue_ref: "",
    status: "never_billed",
    bills: [],
    ...extra,
  };
}

const owing = prop(1, "B-001", {
  owner_name: "Kwame Addo",
  rateable_value: "200000.00",
  status: "unpaid",
  bills: [{ id: 9, year: 2026, reference: "SMA/PR/2026/00001", amount: "1000.00", paid: "400.00", owing: "600.00", issued_on: "2026-02-01", last_paid_on: null, source: "platform" }],
});
const summary = { properties: 2, valued: 1, by_status: { never_billed: 1, unpaid: 1, paid: 0 }, billed: "1000.00", paid: "400.00", owing: "600.00", collected_pct: 40 };

const scheme: BettermentScheme = {
  id: 3,
  project: 5,
  name: "Main Street paving",
  works: "",
  works_feature: 77,
  reach_m: "20",
  completed_on: "2026-07-01",
  basis: "sum",
  basis_label: "A fixed sum on each property",
  amount: "500",
  charges_count: 0,
  total: "0.00",
  collected: "0.00",
  clocks: { serve_by: "2026-09-29", rule: "r.40(7)", unserved: 0, served_late: 0, overdue: false, published: [{ code: "newspaper", label: "In a daily newspaper of national circulation", on: null }] },
};

function backend(routes: Parameters<typeof fakeBackend>[0] = {}, me = makeMe()) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: me }),
    "GET /api/projects/5/register/": () => ({ body: summary }),
    "GET /api/revenue/properties/": () => ({ body: { results: [owing, prop(2, "B-006")], count: 2 } }),
    "GET /api/revenue/rates/": () => ({ body: [{ id: 1, year: 2026, use: "residential", impost: "0.005000", minimum: "50.00", flat: "100.00" }] }),
    "GET /api/revenue/betterment/": () => ({ body: { results: [scheme] } }),
    "GET /api/revenue/betterment/3/": () => ({ body: { ...scheme, charges: [] } }),
    ...routes,
  });
}

describe("property rates and betterment", () => {
  it("shows the register in figures and each property's rates", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5/rates" });
    const facts = await screen.findByLabelText("Register");
    expect(facts).toHaveTextContent("Never billed1");
    expect(facts).toHaveTextContent("GHS 1,000.00 billed, GHS 400.00 collected (40%)");
    const table = await screen.findByRole("table", { name: "Properties" });
    expect(within(table).getByText("B-001").closest("tr")).toHaveTextContent("Kwame AddoGHS 200,000.00GHS 1,000.00 (2026)GHS 400.00Owing");
    expect(within(table).getByText("B-006").closest("tr")).toHaveTextContent("Never billed");
    expect(screen.getByRole("region", { name: "Rates" })).toHaveTextContent("0.005000");
  });

  it("builds the register from the map, records a payment, and filters", async () => {
    const paid = { ...owing, status: "paid" as const, bills: [{ ...owing.bills[0]!, paid: "1000.00", owing: "0.00" }] };
    const api = backend({
      "POST /api/projects/5/register/build/": () => ({ body: { added: 4, already: 2, total: 6 } }),
      "POST /api/revenue/properties/1/payment/": () => ({ body: paid }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/rates" });
    await userEvent.click(await screen.findByRole("button", { name: "Add properties from the map" }));
    expect(await screen.findByText("4 properties added from the map; 6 in the register.")).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Properties" });
    await userEvent.click(within(table).getByRole("button", { name: "B-001" }));
    await userEvent.type(screen.getByLabelText("Payment for B-001"), "600");
    await userEvent.click(screen.getByRole("button", { name: "Record the payment" }));
    await waitFor(() => expect(within(table).getByText("B-001").closest("tr")).toHaveTextContent("Paid up"));
    expect(api.calls.find((c) => c.path.endsWith("/payment/"))!.body).toEqual({ year: 2026, amount: "600" });

    await userEvent.selectOptions(screen.getByLabelText("Show"), "never_billed");
    await waitFor(() => expect(api.calls.some((c) => c.path.includes("status=never_billed"))).toBe(true));
  });

  it("finds the properties a scheme bettered; viewers only look", async () => {
    const found = { ...scheme, charges_count: 2, total: "1000.00", found: { found: 2, added: 2 }, clocks: { ...scheme.clocks, unserved: 2 } };
    const api = backend({ "POST /api/revenue/betterment/3/find/": () => ({ body: found }) });
    const view = renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/rates" });
    const article = await screen.findByRole("article", { name: "Main Street paving" });
    await userEvent.click(within(article).getByRole("button", { name: "Find the bettered properties" }));
    expect(await within(article).findByRole("status")).toHaveTextContent("Search done. 2 properties within 20 m; 2 added.");
    expect(article).toHaveTextContent("Assessment notices (Form 41) to be served by 2026-09-29 (r.40(7)): 2 not served yet");
    view.unmount();

    const viewer = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "viewer", permissions: ["district.view", "project.view", "revenue.view"] }] });
    renderApp(backend({}, viewer).fetch, { tokens: signedIn, route: "/projects/5/rates" });
    await screen.findByRole("table", { name: "Properties" });
    expect(screen.queryByRole("button", { name: "Add properties from the map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Find the bettered properties" })).not.toBeInTheDocument();
  });
});

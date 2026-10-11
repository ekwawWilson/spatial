import type { PermitApplication } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { clock, registry, summary } from "../test/permits";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

function permit(extra: Partial<PermitApplication> = {}): PermitApplication {
  return {
    ...summary(1),
    applicant_phone: "0240000000",
    applicant_email: "",
    applicant_address: "",
    description: "",
    acknowledged_on: null,
    inspected_on: null,
    reported_on: null,
    completion: null,
    clocks: [clock(), clock({ code: "inspect", label: "Technical Sub-Committee: zoning checks and site inspection", rule: "r.44(7)", days: 14, due_on: "2026-10-25" })],
    requirements: [{ code: "site_plan", label: "Site plan at 1:2500, conforming to the local plan", rule: "r.44(3)(b), r.45(9)(a)", asked_for: false, submitted: 0 }],
    extra_requirements: [],
    documents: [],
    comments: [],
    inspections: [],
    checks: {
      ran_at: "",
      zone: { value: "Re B", from: "the zoning layer", national: "Re B", name: "Residential Zone B: medium density" },
      standard: null,
      results: [
        { code: "plot_size", label: "Plot size", outcome: "pass", detail: "900 m²; the standard asks for at least 647 m²." },
        { code: "floors", label: "Storeys", outcome: "fail", detail: "4 storeys; the zone allows up to 3." },
      ],
      counts: { pass: 1, fail: 1, warn: 0, unknown: 0 },
    },
    checked_at: "",
    recommendation: "",
    report: "",
    reasons: "",
    conditions: "",
    processing_fee: null,
    processing_receipt: "",
    processing_paid_on: null,
    permit_fee: null,
    permit_receipt: "",
    permit_paid_on: null,
    verify_url: null,
    events: [{ kind: "received", on: "2026-10-11", note: "", by: "ama@example.test" }],
    ...extra,
  };
}

function backend(application: PermitApplication, extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/permits/registry/": () => ({ body: registry }),
    "GET /api/permits/applications/1/": () => ({ body: application }),
    ...extra,
  });
}

describe("permit page", () => {
  it("shows the deadlines, the checks and what is missing, and acknowledges receipt", async () => {
    const acknowledged = permit({ status: "review", status_label: "With the Technical Sub-Committee", acknowledged_on: "2026-10-11" });
    const api = backend(permit(), { "POST /api/permits/applications/1/acknowledge/": () => ({ body: acknowledged }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/permits/1" });
    expect(await screen.findByRole("heading", { name: /DA\/DP\/2026\/0001/ })).toHaveTextContent("Received");
    expect(screen.getByRole("region", { name: "Deadlines" })).toHaveTextContent("Acknowledge receipt in writing: due by 2026-10-18 (r.44(6), 7 days)");
    const checks = screen.getByRole("region", { name: "Automatic checks" });
    expect(within(checks).getByRole("row", { name: /Storeys/ })).toHaveTextContent("Doesn't meet it4 storeys; the zone allows up to 3.");
    expect(checks).toHaveTextContent("advice to the Technical Sub-Committee");
    expect(screen.getByRole("region", { name: "Documents" })).toHaveTextContent("missing");

    await userEvent.click(within(screen.getByRole("region", { name: "Next step" })).getByRole("button", { name: "Acknowledge receipt" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Receipt acknowledged");
    // Now with the Technical Sub-Committee: the inspection form lists the Regulations' points.
    const inspection = await screen.findByRole("form", { name: "Site inspection" });
    expect(within(inspection).getByLabelText("Whether development has started")).toBeInTheDocument();
    expect(within(screen.getByRole("form", { name: "Report" })).getByRole("button", { name: "Send the report" })).toBeDisabled(); // inspect first
  });

  it("records the committee's decision, with reasons for a refusal", async () => {
    const reported = permit({ status: "reported", status_label: "With the Spatial Planning Committee", recommendation: "refuse", report: "In the road reservation." });
    const refused = permit({ status: "refused", status_label: "Refused", decided_on: "2026-10-20", next_due: null });
    const api = backend(reported, { "POST /api/permits/applications/1/decide/": () => ({ body: refused }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/permits/1" });
    const form = await screen.findByRole("form", { name: "Decision" });
    expect(screen.getByRole("region", { name: "Next step" })).toHaveTextContent("The Technical Sub-Committee recommends: Refuse. In the road reservation.");
    expect(within(form).getByLabelText("Decision")).toHaveValue("refuse"); // starts from the recommendation
    await userEvent.type(within(form).getByLabelText("Reasons"), "The plot is in the road reservation.");
    await userEvent.click(within(form).getByRole("button", { name: "Record the decision" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ decision: "refuse", reasons: "The plot is in the road reservation.", conditions: "" }));
    expect(await screen.findByRole("button", { name: "Download the refusal letter" })).toBeInTheDocument();
  });

  it("leaves the decision to the district administrator and hides contact details from viewers", async () => {
    const viewer = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "viewer", permissions: ["district.view", "project.view", "permit.view"] }] });
    const reported = permit({ status: "reported", status_label: "With the Spatial Planning Committee", applicant_phone: "restricted", applicant_email: "restricted", applicant_address: "restricted" });
    renderApp(backend(reported, { "GET /api/auth/me/": () => ({ body: viewer }) }).fetch, { tokens: signedIn, route: "/projects/5/permits/1" });
    expect(await screen.findByText("The district administrator records the committee's decision.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Decision" })).not.toBeInTheDocument();
    expect(screen.queryByText(/restricted/)).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add a document" })).not.toBeInTheDocument();
  });

  it("issues the permit only once the fee's receipt is in", async () => {
    const granted = permit({ status: "granted", status_label: "Granted: permit fee due", decided_on: "2026-10-20" });
    const paid = { ...granted, permit_fee: "850.00", permit_receipt: "GCR 12", permit_paid_on: "2026-10-21" };
    const api = backend(granted, { "POST /api/permits/applications/1/fees/": () => ({ body: paid }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/permits/1" });
    const step = await screen.findByRole("region", { name: "Next step" });
    expect(within(step).getByRole("button", { name: "Issue the permit" })).toBeDisabled();
    await userEvent.type(within(step).getByLabelText("Permit fee"), "850");
    await userEvent.type(within(step).getByLabelText("Receipt number"), "GCR 12");
    await userEvent.click(within(step).getByRole("button", { name: "Record the receipt" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ stage: "permit", amount: "850", receipt: "GCR 12" }));
    await waitFor(() => expect(within(step).getByRole("button", { name: "Issue the permit" })).toBeEnabled());
    expect(step).toHaveTextContent("Permit fee: GHS 850.00, receipt GCR 12, paid 2026-10-21.");
  });
});

import type { CaseSummary, EnforcementCase, EnforcementRegistry } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const registry: EnforcementRegistry = {
  contraventions: [
    { code: "no_permit", label: "Development without a permit", section: "section 117 of Act 925" },
    { code: "public_space", label: "Encroaches on public space or a right of way", section: "section 121 of Act 925" },
  ],
  notices: [
    { code: "stop", label: "Stop Notice or Order for Discontinuance", form: "48A", rule: "r.55(1); Act 925 s.160", dated: false },
    { code: "rectification", label: "Notice for Rectification of Contravention", form: "49", rule: "r.57(1)", dated: true },
    { code: "enforcement", label: "Enforcement Notice", form: "47", rule: "r.30(2), r.55(1), r.57(3)", dated: true },
  ],
  service_methods: [
    { code: "on_land", label: "Posted in a conspicuous place on the land or building" },
    { code: "post", label: "Sent by post to the last known address" },
  ],
  days: { enforcement_after: 14, act_after: 14, entry_notice: 3, show_cause: 21 },
};

function summary(id: number, extra: Partial<CaseSummary> = {}): CaseSummary {
  return {
    id,
    project: 5,
    number: `SMA/EN/2026/000${id}`,
    officer: null,
    origin: "inspection",
    origin_label: "Found on inspection",
    contravention: "no_permit",
    contravention_label: "Development without a permit",
    section: "section 117 of Act 925",
    description: "A block wall going up",
    status: "open",
    status_label: "Open",
    feature: null,
    permit: null,
    permit_number: null,
    opened_on: "2026-09-01",
    closed_on: null,
    next_action: { label: "Serve a notice", due_on: null, overdue: false },
    ...extra,
  };
}

function full(extra: Partial<EnforcementCase> = {}): EnforcementCase {
  return { ...summary(1), owner_name: "Kwesi Appiah", owner_address: "Plot 14", owner_contact: "", outcome: "", cost: null, cost_recovered: null, opened_by: "ama@example.test", notices: [], ...extra };
}

const rectification = {
  id: 9,
  kind: "rectification",
  label: "Notice for Rectification of Contravention",
  form: "49",
  rule: "r.57(1)",
  grounds: "Building without a permit",
  required: "Remove the wall",
  issued_on: "2026-09-10",
  comply_by: "2026-09-20",
  served_on: null,
  served_by: "",
  served_by_label: "",
  served_note: "",
  complied_on: null,
  dates: {},
};

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/enforcement/registry/": () => ({ body: registry }),
    "GET /api/imagery/": () => ({ body: [] }),
    "GET /api/projects/5/detections/": () => ({ body: { results: [] } }),
    ...extra,
  });
}

describe("enforcement", () => {
  it("lists cases with the step that is overdue, and what the last comparison of images found", async () => {
    const late = summary(1, { status: "notice", status_label: "Notice served", next_action: { label: "Serve an enforcement notice (r.57(2))", due_on: "2026-10-04", overdue: true } });
    const run = { id: 3, before: "September flight", after: "October flight", layer: 12, found: 3, summary: { permitted: 1, existing: 1, new: 1 }, kinds: { permitted: "", existing: "", new: "" }, at: "", started_by: null };
    const api = backend({
      "GET /api/enforcement/cases/": () => ({ body: { results: [late, summary(2)], summary: { total: 2, open: 2, overdue: 1 } } }),
      "GET /api/projects/5/detections/": () => ({ body: { results: [run] } }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/enforcement" });
    const row = (await screen.findByText("SMA/EN/2026/0001")).closest("tr")!;
    expect(row).toHaveTextContent("Serve an enforcement notice (r.57(2)): overdue since 2026-10-04");
    expect(screen.getByLabelText("Summary")).toHaveTextContent("With a step overdue1");
    const found = screen.getByRole("region", { name: "Changes between images" });
    expect(found).toHaveTextContent("Between September flight and October flight: 3 place(s) changed.");
    expect(found).toHaveTextContent("1 new: no permit and no building on the map");
    expect(found).toHaveTextContent("Two orthophotos of the same area"); // none uploaded here: says what is needed
  });

  it("issues a notice on its form, then records how it was served", async () => {
    const issued = full({ notices: [rectification] });
    const served = full({ status: "notice", status_label: "Notice served", notices: [{ ...rectification, served_on: "2026-09-10", served_by: "post", served_by_label: "Sent by post to the last known address", dates: { enforcement_notice_due_on: "2026-10-04", overdue: true, past_comply_by: true } }] });
    const api = backend({
      "GET /api/enforcement/cases/1/": () => ({ body: full() }),
      "POST /api/enforcement/cases/1/notices/": () => ({ status: 201, body: issued }),
      "POST /api/enforcement/notices/9/serve/": () => ({ body: served }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/enforcement/1" });
    const form = await screen.findByRole("form", { name: "Issue a notice" });
    expect(within(form).getByLabelText("Notice")).toHaveValue("rectification");
    expect(within(within(form).getByLabelText("Notice")).getByRole("option", { name: "Enforcement Notice (Form 47)" })).toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText("Grounds"), "Building without a permit");
    await userEvent.type(within(form).getByLabelText("What must be done"), "Remove the wall");
    await userEvent.type(within(form).getByLabelText("To comply by"), "2026-09-20");
    await userEvent.click(within(form).getByRole("button", { name: "Issue the notice" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ kind: "rectification", grounds: "Building without a permit", remedy: "Remove the wall", comply_by: "2026-09-20" }));

    const notice = await screen.findByRole("article", { name: "Notice for Rectification of Contravention" });
    expect(notice).toHaveTextContent("Form 49, r.57(1)");
    expect(notice).toHaveTextContent("not served yet");
    await userEvent.selectOptions(within(notice).getByLabelText("How the Notice for Rectification of Contravention was served"), "post");
    await userEvent.click(within(notice).getByRole("button", { name: "Record service today" }));
    await waitFor(() => expect(api.calls.filter((c) => c.method === "POST")[1]?.body).toEqual({ method: "post" }));
    expect(await within(notice).findByText(/an enforcement notice is due by 2026-10-04 \(r.57\(2\)\), now overdue/)).toBeInTheDocument();
  });

  it("lets a field officer open a case but not serve notices or close it", async () => {
    const officer = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "field_officer", permissions: ["district.view", "project.view", "enforcement.view", "enforcement.open"] }] });
    const me = { "GET /api/auth/me/": () => ({ body: officer }) };
    const list = renderApp(backend({ ...me, "GET /api/enforcement/cases/": () => ({ body: { results: [], summary: { total: 0, open: 0, overdue: 0 } } }) }).fetch, { tokens: signedIn, route: "/projects/5/enforcement" });
    expect(await screen.findByRole("button", { name: "Open a case" })).toBeInTheDocument();
    list.unmount();
    renderApp(backend({ ...me, "GET /api/enforcement/cases/1/": () => ({ body: full({ notices: [rectification] }) }) }).fetch, { tokens: signedIn, route: "/projects/5/enforcement/1" });
    expect(await screen.findByRole("article", { name: "Notice for Rectification of Contravention" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Issue a notice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Close the case" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record service today" })).not.toBeInTheDocument();
  });
});

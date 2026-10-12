import type { PlanClock, PlanProcess, PublicPlan, PublicRoom } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

function clock(code: string, label: string, extra: Partial<PlanClock> = {}): PlanClock {
  return { code, label, rule: "r.23(1)", form: "", limit: "", decision: false, due_on: null, done_on: null, note: "", late: false, overdue: false, ...extra };
}

function process(extra: Partial<PlanProcess> = {}): PlanProcess {
  return {
    project: 5,
    origin: "committee",
    origin_label: "Prepared by the District Spatial Planning Committee",
    prepared_by: "",
    structure_plan_on: "2025-01-10",
    application_on: null,
    conditions: "",
    valid_until: null,
    clocks: [
      clock("direct", "The planning authority directs the Spatial Planning Committee to prepare the local plan", { limit: "12 months", due_on: "2026-01-10", overdue: true }),
      clock("commence", "Notice of commencement of the local plan published", { rule: "r.23(2)", form: "27" }),
      clock("approve", "Local plan approved", { rule: "r.25(1)", decision: true }),
    ],
    next_step: null,
    comment_days: 60,
    comment_rule: "r.23(5)",
    comments_close_on: null,
    comments_open: false,
    content: [
      { code: "a", label: "Population size and density for residential neighbourhoods", covered: false, note: "" },
      { code: "m", label: "Drainage system", covered: true, note: "Section 6" },
    ],
    content_rule: "r.24(1)",
    content_covered: 1,
    possible_conditions: ["A time frame for the validity of the local plan"],
    stages: [
      { code: "before", label: "Before the preparation of the plan" },
      { code: "draft", label: "On the draft plan" },
    ],
    consultations: [],
    comments: [],
    comments_unanswered: 0,
    papers: [{ code: "commence", label: "Notice of commencement of a local plan" }],
    ...extra,
  };
}

const meeting = { id: 4, stage: "before", stage_label: "Before the preparation of the plan", held_on: "2026-09-12", venue: "Chief's palace", groups: "Chiefs, traders", attendance: 84, issues: "Flooding along the drain.", outcome: "", displayed_on: null };

function backend(plan: PlanProcess, routes: Parameters<typeof fakeBackend>[0] = {}, me = makeMe()) {
  return fakeBackend({ "GET /api/auth/me/": () => ({ body: me }), "GET /api/projects/5/plan/": () => ({ body: plan }), ...routes });
}

describe("making a local plan", () => {
  it("shows each step with its rule, form and date, and records one", async () => {
    const directed = process({ clocks: [clock("direct", "The planning authority directs the Spatial Planning Committee to prepare the local plan", { limit: "12 months", due_on: "2026-01-10", done_on: "2026-10-12", late: true, note: "Resolution 14" })] });
    const api = backend(process(), { "POST /api/projects/5/plan/step/": () => ({ body: directed }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/plan" });
    const steps = await screen.findByRole("region", { name: "Steps and deadlines" });
    expect(within(steps).getByText(/The planning authority directs/).closest("tr")).toHaveTextContent("r.23(1): 12 monthsOverdue since 2026-01-10");
    expect(within(steps).getByText(/Notice of commencement of the local plan published/).closest("tr")).toHaveTextContent("(Form 27)r.23(2)No time set");
    expect(screen.getByRole("form", { name: "What the plan specifies" })).toHaveTextContent("1 of 2 (r.24(1))");

    await userEvent.type(within(steps).getByLabelText(/^Note for: The planning authority/), "Resolution 14");
    await userEvent.click(within(steps).getByRole("button", { name: /^Done today: The planning authority/ }));
    expect(await screen.findByRole("status")).toHaveTextContent("Step recorded.");
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({ step: "direct", note: "Resolution 14" });
    expect(screen.getByText(/The planning authority directs/).closest("tr")).toHaveTextContent("Done 2026-10-12, late (due 2026-01-10)");
  });

  it("saves what the plan covers, records a consultation and puts its minutes on display", async () => {
    const api = backend(process(), {
      "POST /api/projects/5/plan/content/": () => ({ body: process({ content_covered: 2 }) }),
      "POST /api/projects/5/plan/consultations/": () => ({ status: 201, body: process({ consultations: [meeting] }) }),
      "POST /api/plan-consultations/4/display/": () => ({ body: process({ consultations: [{ ...meeting, displayed_on: "2026-10-12" }] }) }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/plan" });
    const covers = await screen.findByRole("form", { name: "What the plan specifies" });
    await userEvent.click(within(covers).getByRole("checkbox", { name: /Population size and density/ }));
    await userEvent.click(within(covers).getByRole("button", { name: "Save what it covers" }));
    await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/content/"))).toBe(true));
    expect(api.calls.find((c) => c.path.endsWith("/content/"))!.body).toEqual({ items: { a: { covered: true, note: "" }, m: { covered: true, note: "Section 6" } } });

    const record = screen.getByRole("form", { name: "Record a consultation" });
    await userEvent.type(within(record).getByLabelText("Held on"), "2026-09-12");
    await userEvent.type(within(record).getByLabelText("Venue"), "Chief's palace");
    await userEvent.type(within(record).getByLabelText("Number attending"), "84");
    await userEvent.type(within(record).getByLabelText("Issues raised"), "Flooding along the drain.");
    await userEvent.click(within(record).getByRole("button", { name: "Record the consultation" }));
    const held = await screen.findByText(/2026-09-12, Chief's palace/);
    expect(held.closest("article")).toHaveTextContent("Before the preparation of the plan; 84 attending; Chiefs, traders");
    expect(api.calls.find((c) => c.path.endsWith("/consultations/"))!.body).toEqual({ stage: "before", held_on: "2026-09-12", venue: "Chief's palace", groups: "", attendance: 84, issues: "Flooding along the drain.", outcome: "" });

    await userEvent.click(screen.getByRole("button", { name: "Display the minutes of 2026-09-12" }));
    expect(await screen.findByText("On display in the Public Data Room since 2026-10-12")).toBeInTheDocument();
  });

  it("answers comments, and leaves the approval to those who may decide", async () => {
    const said = { id: 7, name: "Akua Sarpong", contact: "", topic: "k", topic_label: "Road network and circulation", text: "The market road needs a walkway.", received_on: "2026-10-01", online: true, response: "", responded_on: null };
    const open = process({ comments_close_on: "2026-11-20", comments_open: true, comments: [said], comments_unanswered: 1 });
    const api = backend(open, { "POST /api/plan-comments/7/reply/": () => ({ body: { ...open, comments: [{ ...said, response: "A walkway is added.", responded_on: "2026-10-12" }], comments_unanswered: 0 } }) });
    const view = renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/plan" });
    const comments = await screen.findByRole("region", { name: "Comments on the draft" });
    expect(comments).toHaveTextContent("1 of 1 not yet answered");
    expect(comments).toHaveTextContent("2026-10-01, Akua Sarpong (sent online) on road network and circulation: The market road needs a walkway.");
    expect(screen.getByRole("region", { name: "Steps and deadlines" })).toHaveTextContent("The public may comment on the draft until 2026-11-20");
    await userEvent.type(within(comments).getByLabelText("Response to comment 7"), "A walkway is added.");
    await userEvent.click(within(comments).getByRole("button", { name: "Record the response" }));
    expect(await within(comments).findByText(/The Committee's response \(2026-10-12\): A walkway is added\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done today: Local plan approved" })).toBeInTheDocument();
    view.unmount();

    const planner = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "planner", permissions: ["district.view", "project.view", "project.edit"] }] });
    renderApp(backend(open, {}, planner).fetch, { tokens: signedIn, route: "/projects/5/plan" });
    expect(await screen.findByRole("button", { name: /^Done today: Notice of commencement/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Done today: Local plan approved" })).not.toBeInTheDocument();
  });

  it("lets anyone read a plan's consultations and comment on its draft in the Public Data Room", async () => {
    const room: PublicRoom = { code: "SMA", assembly: "Sample Municipal Assembly", welcome: "", contact: "", answer_within_days: 5, fees: [], documents: [], zoning_schemes: [] };
    const plan: PublicPlan = {
      project: 5,
      name: "Kasoa local plan",
      locality: "Kasoa",
      commenced_on: "2026-08-01",
      draft_on_display_from: "2026-10-01",
      comments_close_on: "2026-11-30",
      comments_open: true,
      approved_on: null,
      consultations: [{ stage: "Before the preparation of the plan", held_on: "2026-09-12", venue: "Chief's palace", attendance: 84, issues: "Flooding along the drain.", outcome: "The drain reserve stays clear." }],
    };
    const api = fakeBackend({
      "GET /api/public/rooms/SMA/": () => ({ body: room }),
      "GET /api/public/rooms/SMA/register/": () => ({ body: { results: [] } }),
      "GET /api/public/rooms/SMA/plans/": () => ({ body: { results: [plan], topics: [{ code: "k", label: "Road network and circulation" }] } }),
      "POST /api/public/rooms/SMA/plans/5/comments/": () => ({ status: 201, body: { received_on: "2026-10-12", comments_close_on: "2026-11-30" } }),
    });
    renderApp(api.fetch, { route: "/public/SMA" });
    const plans = await screen.findByRole("region", { name: "Local plans being made" });
    expect(plans).toHaveTextContent("The draft is open for inspection and comment until 2026-11-30.");
    expect(plans).toHaveTextContent("2026-09-12, Chief's palace (84 attending): Flooding along the drain.Agreed: The drain reserve stays clear.");
    const form = within(plans).getByRole("form", { name: "Comment on Kasoa local plan" });
    await userEvent.type(within(form).getByLabelText("Your name, for Kasoa local plan"), "Akua Sarpong");
    await userEvent.selectOptions(within(form).getByLabelText("About, for Kasoa local plan"), "k");
    await userEvent.type(within(form).getByLabelText("Your comment on Kasoa local plan"), "The market road needs a walkway.");
    await userEvent.click(within(form).getByRole("button", { name: "Send the comment" }));
    expect(await within(plans).findByRole("status")).toHaveTextContent("Your comment on Kasoa local plan has been received");
    const sent = api.calls.find((c) => c.method === "POST")!;
    expect(sent.body).toEqual({ name: "Akua Sarpong", text: "The market road needs a walkway.", topic: "k" });
    expect(sent.headers.get("Authorization")).toBeNull();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { emptyPage, fakeBackend, makeMe } from "./test/fakeBackend";
import { renderApp, signedIn } from "./test/render";

beforeEach(() => localStorage.clear());

const member = (id: number, email: string, role = "viewer") => ({
  id,
  user: { id: id + 100, email, first_name: "", last_name: "", is_active: true },
  role,
  is_active: true,
  created_at: "2026-09-23T10:00:00Z",
});

describe("signing in", () => {
  it("shows the server's message when sign-in fails", async () => {
    const backend = fakeBackend({
      "POST /api/auth/login/": () => ({ status: 401, body: { detail: "Email or password is incorrect." } }),
    });
    renderApp(backend.fetch, { route: "/login" });
    await userEvent.type(screen.getByLabelText("Email"), "ama@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  });

  it("goes to the home page in the first district after signing in", async () => {
    const backend = fakeBackend({
      "POST /api/auth/login/": () => ({ body: { access: "A", refresh: "R", user: makeMe() } }),
    });
    renderApp(backend.fetch, { route: "/login" });
    await userEvent.type(screen.getByLabelText("Email"), "ama@example.test");
    await userEvent.type(screen.getByLabelText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Sample Municipal Assembly", { selector: "strong" })).toBeInTheDocument();
  });

  it("sends signed-out visitors to the sign-in page", async () => {
    renderApp(fakeBackend({}).fetch, { route: "/members" });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("returns to sign-in when the session can't be refreshed", async () => {
    const backend = fakeBackend({
      "GET /api/auth/me/": () => ({ status: 401, body: { detail: "expired" } }),
      "POST /api/auth/refresh/": () => ({ status: 401, body: { detail: "blacklisted" } }),
    });
    renderApp(backend.fetch, { tokens: signedIn });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("navigation follows the role in the active district", () => {
  it("district admin sees Members and Audit log", async () => {
    renderApp(fakeBackend({ "GET /api/auth/me/": () => ({ body: makeMe() }) }).fetch, { tokens: signedIn });
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(nav).findByRole("link", { name: "Members" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Audit log" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
  });

  it("switching to a district where the user is a viewer hides admin pages", async () => {
    renderApp(fakeBackend({ "GET /api/auth/me/": () => ({ body: makeMe() }) }).fetch, { tokens: signedIn });
    const nav = await screen.findByRole("navigation", { name: "Main" });
    await within(nav).findByRole("link", { name: "Members" });
    await userEvent.selectOptions(screen.getByRole("combobox"), "Other District Assembly");
    await waitFor(() => expect(within(nav).queryByRole("link", { name: "Members" })).not.toBeInTheDocument());
    expect(localStorage.getItem("spatial.district.1")).toBe("20");
  });

  it("a viewer who opens /members directly is refused", async () => {
    localStorage.setItem("spatial.district.1", "20");
    renderApp(fakeBackend({ "GET /api/auth/me/": () => ({ body: makeMe() }) }).fetch, {
      tokens: signedIn,
      route: "/members",
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Your role in this district does not allow this.");
  });

  it("system admin sees the System section", async () => {
    const backend = fakeBackend({
      "GET /api/auth/me/": () => ({ body: makeMe({ is_system_admin: true, memberships: [] }) }),
      "GET /api/districts/": () => ({
        body: [{ id: 10, name: "Sample Municipal Assembly", code: "SMA", kind: "municipal", region: 1, region_name: "GA", is_active: true }],
      }),
    });
    renderApp(backend.fetch, { tokens: signedIn });
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(nav).findByRole("link", { name: "Users" })).toBeInTheDocument();
    expect(await within(nav).findByRole("link", { name: "Members" })).toBeInTheDocument();
  });
});

describe("members page", () => {
  function backendWithMembers(onAdd: (body: unknown) => { status?: number; body?: unknown }) {
    let members = [member(1, "ama@example.test", "district_admin")];
    return fakeBackend({
      "GET /api/auth/me/": () => ({ body: makeMe() }),
      "GET /api/memberships/": () => ({ body: { ...emptyPage, count: members.length, results: members } }),
      "POST /api/memberships/": (body) => {
        const result = onAdd(body);
        if (!result.status || result.status < 400) {
          members = [...members, member(2, (body as { email: string }).email)];
        }
        return result;
      },
    });
  }

  it("requests members of the active district", async () => {
    const backend = backendWithMembers(() => ({ status: 201 }));
    renderApp(backend.fetch, { tokens: signedIn, route: "/members" });
    expect(await screen.findByRole("cell", { name: "ama@example.test" })).toBeInTheDocument();
    const call = backend.calls.find((c) => c.path.startsWith("/api/memberships/"));
    expect(call?.headers.get("X-District-ID")).toBe("10");
  });

  it("adds a member and clears the form", async () => {
    const backend = backendWithMembers(() => ({ status: 201, body: {} }));
    renderApp(backend.fetch, { tokens: signedIn, route: "/members" });
    const form = await screen.findByRole("form", { name: "Add member" });
    await userEvent.type(within(form).getByLabelText("Email"), "kofi@example.test");
    await userEvent.selectOptions(within(form).getByLabelText("Role"), "planner");
    await userEvent.click(within(form).getByRole("button", { name: "Add member" }));
    expect(await screen.findByText("kofi@example.test")).toBeInTheDocument();
    expect(within(form).getByLabelText("Email")).toHaveValue("");
    const post = backend.calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({ email: "kofi@example.test", role: "planner" });
  });

  it("keeps the input and shows the error when adding fails", async () => {
    const backend = backendWithMembers(() => ({ status: 400, body: { email: ["This person is already a member."] } }));
    renderApp(backend.fetch, { tokens: signedIn, route: "/members" });
    const form = await screen.findByRole("form", { name: "Add member" });
    await userEvent.type(within(form).getByLabelText("Email"), "ama@example.test");
    await userEvent.click(within(form).getByRole("button", { name: "Add member" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This person is already a member.");
    expect(within(form).getByLabelText("Email")).toHaveValue("ama@example.test");
  });
});

describe("password reset", () => {
  it("checks the two passwords match before calling the API", async () => {
    const backend = fakeBackend({});
    renderApp(backend.fetch, { route: "/reset-password?uid=MQ&token=t" });
    await userEvent.type(screen.getByLabelText("New password"), "A-Brand-New-Passw0rd");
    await userEvent.type(screen.getByLabelText("Repeat new password"), "different");
    await userEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("don't match");
    expect(backend.calls).toHaveLength(0);
  });

  it("sends uid and token from the emailed link", async () => {
    const backend = fakeBackend({ "POST /api/auth/password/reset/confirm/": () => ({ status: 204 }) });
    renderApp(backend.fetch, { route: "/reset-password?uid=MQ&token=abc-123" });
    await userEvent.type(screen.getByLabelText("New password"), "A-Brand-New-Passw0rd");
    await userEvent.type(screen.getByLabelText("Repeat new password"), "A-Brand-New-Passw0rd");
    await userEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Your password is set.");
    expect(backend.calls[0]?.body).toEqual({ uid: "MQ", token: "abc-123", new_password: "A-Brand-New-Passw0rd" });
  });
});

describe("status page", () => {
  it("names the failing service and its problem", async () => {
    const backend = fakeBackend({
      "GET /api/health/": () => ({
        status: 503,
        body: {
          ok: false,
          database: { ok: true, postgis: "3.5.2" },
          gdal: { ok: false, version: "3.10.3", missing_drivers: ["LIBKML"] },
          redis: { ok: true },
        },
      }),
    });
    renderApp(backend.fetch, { route: "/status" });
    expect(await screen.findByRole("status")).toHaveTextContent("Some services are failing");
    expect(screen.getByText("Missing drivers: LIBKML")).toBeInTheDocument();
  });
});

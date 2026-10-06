import type { SyncConflict, SyncConflictDetail } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const conflict: SyncConflict = {
  id: 4,
  project: 5,
  feature: 77,
  layer: 2,
  layer_name: "Buildings",
  status: "open",
  resolution: "",
  submitted_by: "kofi@example.test",
  created_at: "2026-10-06T09:00:00Z",
  base_version: 1,
  server_version: 2,
  resolved_by: null,
  resolved_at: null,
};

const detail: SyncConflictDetail = {
  ...conflict,
  schema: [
    { name: "use", label: "Use", type: "text", required: false },
    { name: "storeys", label: "Storeys", type: "integer", required: false },
    { name: "owner", label: "Owner", type: "text", required: false },
  ],
  office: { version: 2, properties: { use: "house", storeys: 2, owner: "Ama" }, geometry: null },
  field: { properties: { use: "shop", storeys: 3, owner: "Ama" }, geometry: { type: "Point", coordinates: [-0.2, 5.6] }, capture: { accuracy_m: 3.2 } },
};

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  let open = [conflict];
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/sync/conflicts/": () => ({ body: open }),
    "GET /api/sync/conflicts/4/": () => ({ body: detail }),
    "POST /api/sync/conflicts/4/resolve/": () => {
      open = [];
      return { body: { ...detail, status: "resolved" } };
    },
    ...extra,
  });
}

describe("field conflicts", () => {
  it("shows both versions side by side and marks what differs", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5/conflicts" });
    await userEvent.click(await screen.findByRole("button", { name: "Compare" }));
    const compare = await screen.findByRole("region", { name: "Compare versions" });
    const rows = within(compare).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Usehouseshop");
    expect(rows[3]).toHaveTextContent("OwnerAmasame"); // equal values aren't a choice
    expect(within(compare).queryByLabelText("Field value for Owner")).not.toBeInTheDocument();
    expect(compare).toHaveTextContent("Field GPS accuracy ±3.2 m.");
  });

  it("merges field by field: the picked values and the chosen shape are sent", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/conflicts" });
    await userEvent.click(await screen.findByRole("button", { name: "Compare" }));
    const compare = await screen.findByRole("region", { name: "Compare versions" });
    await userEvent.click(within(compare).getByLabelText("Field value for Use"));
    await userEvent.click(within(compare).getByLabelText("Use the shape from the field"));
    await userEvent.click(within(compare).getByRole("button", { name: "Save the values picked above" }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
        resolution: "merged",
        properties: { use: "shop", storeys: 2, owner: "Ama" },
        use_field_geometry: true,
      }),
    );
    expect(await screen.findByText("No conflicts waiting.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saved the merged version.");
  });

  it("keeps one side whole", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/conflicts" });
    await userEvent.click(await screen.findByRole("button", { name: "Compare" }));
    await userEvent.click(await screen.findByRole("button", { name: "Keep the field version" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ resolution: "keep_field" }));
  });

  it("is read-only for roles that can't resolve", async () => {
    const me = makeMe();
    me.memberships[0]!.permissions = me.memberships[0]!.permissions.filter((p) => p !== "sync.resolve");
    renderApp(backend({ "GET /api/auth/me/": () => ({ body: me }) }).fetch, { tokens: signedIn, route: "/projects/5/conflicts" });
    await userEvent.click(await screen.findByRole("button", { name: "Compare" }));
    expect(await screen.findByText("Planners and district administrators resolve conflicts.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Keep the office version" })).not.toBeInTheDocument();
  });
});

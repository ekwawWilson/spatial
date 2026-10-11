import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

describe("plan sheet", () => {
  it("asks for the paper, scale and title, and says what scale the sheet was drawn at", async () => {
    URL.createObjectURL = vi.fn(() => "blob:sheet");
    URL.revokeObjectURL = vi.fn();
    const base = fakeBackend({
      "GET /api/auth/me/": () => ({ body: makeMe() }),
      "GET /api/projects/5/": () => ({ body: { id: 5, name: "Kasoa local plan", crs_detail: { code: "EPSG:2136", name: "Accra / Ghana National Grid" } } }),
    });
    const calls: string[] = [];
    const fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/sheet/")) {
        calls.push(url);
        return new Response(new Blob(["%PDF"]), { status: 200, headers: { "X-Sheet-Scale": "2500", "content-type": "application/pdf" } });
      }
      return base.fetch(input, init);
    }) as typeof globalThis.fetch;
    renderApp(fetch, { tokens: signedIn, route: "/projects/5/sheet" });
    expect(await screen.findByText(/EPSG:2136 Accra \/ Ghana National Grid/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Paper"), "A1");
    await userEvent.selectOptions(screen.getByLabelText("Scale"), "2500");
    await userEvent.type(screen.getByLabelText("Title"), "Base map");
    await userEvent.click(screen.getByRole("button", { name: "Download the plan sheet" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Drawn at 1:2,500 on A1.");
    await waitFor(() => expect(calls).toEqual(["/api/projects/5/sheet/?paper=A1&scale=2500&title=Base+map"]));
  });
});

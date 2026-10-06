import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
}

async function api(page: Page, method: string, path: string, body?: unknown) {
  return page.evaluate(
    async ({ method, path, body }) => {
      const tokens = JSON.parse(localStorage.getItem("spatial.tokens") ?? "{}");
      const me = await (await fetch("/api/auth/me/", { headers: { Authorization: `Bearer ${tokens.access}` } })).json();
      const response = await fetch(path, {
        method,
        headers: {
          Authorization: `Bearer ${tokens.access}`,
          "X-District-ID": String(me.memberships[0].district.id),
          "Content-Type": "application/json",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return { status: response.status, body: response.status === 204 ? null : await response.json() };
    },
    { method, path, body },
  );
}

const square = (x: number, y: number, size: number) => ({
  type: "Polygon",
  coordinates: [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]],
});

test("map layers to roles, run the procedures, and confirm an inferred link", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Relations check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);
  const project = Number(page.url().split("/").pop());

  // Two buildings (Ghana National Grid feet), one inside a flood-prone area, and a drain beside the other.
  const layer = async (name: string, geometry_type: string, schema: object[]) =>
    ((await api(page, "POST", "/api/layers/", { project, name, geometry_type, schema })).body as { id: number }).id;
  const buildings = await layer("Buildings", "polygon", [{ name: "property_id", type: "text" }]);
  const flood = await layer("Flood zones", "polygon", [{ name: "zone_id", type: "text" }]);
  const drains = await layer("Drains", "line", [{ name: "drain_id", type: "text" }]);
  const add = (layerId: number, geometry: object, properties: object) => api(page, "POST", `/api/layers/${layerId}/features/`, { geometry, properties });
  await add(buildings, square(1190600, 337700, 60), { property_id: "B-1" });
  const b2 = ((await add(buildings, square(1190900, 337700, 60), { property_id: "B-2" })).body as { id: number }).id;
  await add(flood, square(1190880, 337680, 200), { zone_id: "F-1" });
  await add(drains, { type: "LineString", coordinates: [[1190590, 337690], [1190700, 337690]] }, { drain_id: "D-1" });

  await page.getByRole("link", { name: "Relationships" }).click();
  // Layers are suggested from their names; nothing is saved until Save.
  const roles = page.getByRole("region", { name: "Layers" });
  await expect(roles.getByLabel("Layer for Properties (buildings)")).toHaveValue(String(buildings));
  await expect(roles.getByLabel("Layer for Flood-prone areas")).toHaveValue(String(flood));
  await expect(roles.getByLabel("Layer for Drains")).toHaveValue(String(drains));
  await roles.getByRole("button", { name: "Save" }).click();
  await expect(roles.getByText("Not saved yet.")).toHaveCount(0);

  await page.getByRole("button", { name: "Run now" }).click();
  const totals = page.getByRole("region", { name: "Totals" });
  await expect(totals).toContainText("Properties2");
  await expect(totals).toContainText("In a flood-prone area1");

  // The flood link is calculated; the drain link is a guess for a person to confirm.
  const links = page.getByRole("region", { name: "Links" });
  await links.getByLabel("Kind of link").selectOption("affected_by");
  await expect(links.getByRole("row").filter({ hasText: "B-2" })).toContainText("F-1");
  await links.getByLabel("Kind of link").selectOption("connected_to");
  const row = links.getByRole("row").filter({ hasText: "B-1" });
  await expect(row).toContainText("Inferred");
  await row.getByRole("button", { name: /^Confirm/ }).click();
  await expect(row).toContainText("Confirmed by a person");

  // On the map, the building's details list what it is linked to.
  await page.getByRole("link", { name: "← Back to the project" }).click();
  await page.getByRole("button", { name: "Buildings", exact: true }).click();
  await page.getByRole("region", { name: "Attributes of Buildings" }).getByRole("cell", { name: String(b2), exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Feature details" }).getByRole("group", { name: "Linked to" })).toContainText("is affected by F-1");
});

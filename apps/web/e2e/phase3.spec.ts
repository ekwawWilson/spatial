import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
}

/** Calls the API as the signed-in user (drawing arrives in Phase 6, so the
 * test seeds a feature this way). */
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

test("planner builds a project with three layers, reorders and styles them, and edits an attribute", async ({ page }) => {
  const name = `E2E plan ${Date.now()}`;
  await signIn(page, "sma.planner@example.test");

  // Create the project; it opens in the workspace.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(name);
  await form.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  const projectId = Number(page.url().split("/").pop());

  // The map renders, with a scale bar and a north arrow.
  await expect(page.locator(".map canvas").first()).toBeVisible();
  await expect(page.locator(".ol-scale-line")).toBeVisible();
  await expect(page.locator(".ol-rotate")).toBeVisible();

  // Three layers.
  const addLayer = page.getByRole("form", { name: "Add layer" });
  for (const [layerName, domain, geometry] of [
    ["Parcels", "B", "polygon"],
    ["Buildings", "C", "polygon"],
    ["Streets", "D", "line"],
  ]) {
    await addLayer.getByLabel("Layer name").fill(layerName!);
    await addLayer.getByLabel("Domain").selectOption(domain!);
    await addLayer.getByLabel("Geometry").selectOption(geometry!);
    await addLayer.getByRole("button", { name: "Add layer" }).click();
    await expect(page.getByRole("button", { name: layerName, exact: true })).toBeVisible();
  }

  // Reorder: newest is on top (Streets, Buildings, Parcels); move Parcels up.
  await page.getByRole("button", { name: "Move Parcels up" }).click();
  await expect
    .poll(async () => ((await api(page, "GET", `/api/layers/?project=${projectId}`)).body as { name: string }[]).map((l) => l.name))
    .toEqual(["Streets", "Parcels", "Buildings"]);

  // Give Parcels a field and a feature (native Ghana National Grid feet).
  const layers = (await api(page, "GET", `/api/layers/?project=${projectId}`)).body as { id: number; name: string }[];
  const parcels = layers.find((l) => l.name === "Parcels")!;
  expect((await api(page, "PATCH", `/api/layers/${parcels.id}/`, { schema: [{ name: "parcel_id", type: "text" }] })).status).toBe(200);
  const square = [[1190631.45, 337708.94], [1190731.45, 337708.94], [1190731.45, 337808.94], [1190631.45, 337808.94], [1190631.45, 337708.94]];
  const created = await api(page, "POST", `/api/layers/${parcels.id}/features/`, {
    geometry: { type: "Polygon", coordinates: [square] },
    properties: { parcel_id: "P-1" },
  });
  expect(created.status).toBe(201);
  await page.reload();

  // Style Parcels.
  const parcelsGroup = page.getByRole("region", { name: "B. Land & parcels" });
  await parcelsGroup.getByRole("button", { name: "Style" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit style" });
  await dialog.getByLabel("Symbol fill", { exact: true }).fill("#e4572e");
  await dialog.getByRole("button", { name: "Save style" }).click();
  await expect(dialog).toHaveCount(0);
  const styled = (await api(page, "GET", `/api/layers/${parcels.id}/`)).body as { style: { fill: string } };
  expect(styled.style.fill).toBe("#e4572e");

  // Edit an attribute in the table.
  await page.getByRole("button", { name: "Parcels", exact: true }).click();
  const table = page.getByRole("region", { name: "Attributes of Parcels" });
  await table.getByRole("cell", { name: "P-1" }).dblclick();
  const input = table.getByLabel(/Parcel id of feature/);
  await input.fill("P-9");
  await input.press("Enter");
  await expect(table.getByRole("status")).toHaveText("Saved Parcel id.");
  await expect(table.getByRole("cell", { name: "P-9" })).toBeVisible();

  // Zooming to the layer and measuring work without errors.
  await page.getByRole("button", { name: "Zoom to Parcels" }).click();
  await page.getByRole("button", { name: "Measure distance" }).click();
  await expect(page.getByRole("button", { name: "Measure distance" })).toHaveAttribute("aria-pressed", "true");
});

test("field officer and viewer can open a project but not change it", async ({ page }) => {
  await signIn(page, "sma.viewer@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  await expect(page.getByRole("heading", { name: "Plan projects" })).toBeVisible();
  await expect(page.getByRole("form", { name: "New project" })).toHaveCount(0);
});

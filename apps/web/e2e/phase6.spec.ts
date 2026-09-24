import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";
const FOOT = 0.3047997101815088;

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

/** Screen position of the first vertex of a layer's first feature (development
 * builds expose the OpenLayers map as window.__spatialMap). */
async function vertexPixel(page: Page, layerId: number): Promise<{ x: number; y: number }> {
  const [px, py] = await page.evaluate((id) => {
    type Source = { getFeatures(): { getGeometry(): { getCoordinates(): number[][][] } }[] };
    type OlLike = {
      getLayers(): { getArray(): { get(key: string): unknown; getSource(): Source | null }[] };
      getPixelFromCoordinate(c: number[]): number[];
    };
    const map = (window as unknown as { __spatialMap: OlLike }).__spatialMap;
    const layer = map.getLayers().getArray().find((l) => l.get("layerId") === id);
    const feature = layer?.getSource()?.getFeatures()[0];
    if (!feature) throw new Error("layer or feature not on the map");
    return map.getPixelFromCoordinate(feature.getGeometry().getCoordinates()[0]![0]!);
  }, layerId);
  const box = await page.locator(".map").boundingBox();
  return { x: box!.x + px!, y: box!.y + py! };
}

test("draw with snapping, undo and redo, and restore from history", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Editing check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);
  const projectId = Number(page.url().split("/").pop());

  // A parcels layer with one feature, created through the API (Ghana National Grid feet).
  const layer = (await api(page, "POST", "/api/layers/", { project: projectId, name: "Parcels", domain: "B", geometry_type: "polygon" })).body as { id: number };
  const square = [[1190600, 337700], [1190800, 337700], [1190800, 337900], [1190600, 337900], [1190600, 337700]];
  await api(page, "POST", `/api/layers/${layer.id}/features/`, { geometry: { type: "Polygon", coordinates: [square] } });
  await page.reload();
  await page.getByRole("button", { name: "Zoom to Parcels" }).click();
  await page.waitForTimeout(800);

  // Draw a new polygon whose first corner is clicked a few pixels off an existing corner: snapping pulls it on.
  await page.getByRole("button", { name: "Parcels", exact: true }).click();
  const editing = page.getByRole("region", { name: "Editing" });
  await editing.getByRole("button", { name: "Draw" }).click();
  const corner = await vertexPixel(page, layer.id);
  // The first corner is the square's south-west corner and zooming leaves only a
  // small margin around it, so draw up and to the right (inside the square) to
  // keep every click on the map rather than on the panels around it.
  const clicks = [
    [corner.x + 4, corner.y - 3],
    [corner.x + 80, corner.y - 5],
    [corner.x + 80, corner.y - 80],
    [corner.x + 10, corner.y - 80],
    // Clicking the first corner again closes the polygon (more reliable than a
    // double-click, which the map may also treat as "zoom in").
    [corner.x + 4, corner.y - 3],
  ] as const;
  for (const [x, y] of clicks) {
    const onMap = await page.evaluate((p) => document.elementFromPoint(p.x, p.y)?.closest(".map") !== null, { x, y });
    expect(onMap, `click at ${x},${y} is not on the map`).toBe(true);
    await page.mouse.click(x, y);
  }
  await page.waitForTimeout(1000);
  const problems = await page.getByRole("alert").allTextContents();
  await expect
    .poll(async () => (await api(page, "GET", `/api/layers/${layer.id}/features/?geometry=native`)).body.numberMatched, {
      message: `drawn polygon not saved; alerts on the page: ${JSON.stringify(problems)}`,
    })
    .toBe(2);

  // Snapping precision: the drawn corner is the existing corner, within 1 mm.
  const features = (await api(page, "GET", `/api/layers/${layer.id}/features/?geometry=native`)).body.features as { id: number; geometry: { coordinates: number[][][] } }[];
  const drawn = [...features].sort((a, b) => b.id - a.id)[0]!; // the newest
  const snapped = drawn.geometry.coordinates[0]!.map(([x, y]) => Math.hypot(x! - square[0]![0]!, y! - square[0]![1]!) * FOOT);
  expect(Math.min(...snapped)).toBeLessThan(0.001);

  // Undo removes it, redo brings it back.
  await editing.getByRole("button", { name: /^Undo/ }).click();
  await expect.poll(async () => (await api(page, "GET", `/api/layers/${layer.id}/features/`)).body.numberMatched).toBe(1);
  await editing.getByRole("button", { name: /^Redo/ }).click();
  await expect.poll(async () => (await api(page, "GET", `/api/layers/${layer.id}/features/`)).body.numberMatched).toBe(2);

  // History: change the original square through the API, then restore it from the history panel.
  const original = features.find((f) => f.id !== drawn.id)!;
  const moved = square.map(([x, y]) => [x! + 50, y!]);
  await api(page, "PATCH", `/api/features/${original.id}/`, { version: 1, geometry: { type: "Polygon", coordinates: [moved] } });
  await editing.getByRole("button", { name: "Stop editing" }).click();
  const table = page.getByRole("region", { name: "Attributes of Parcels" });
  await table.getByRole("cell", { name: String(original.id), exact: true }).click();
  const details = page.getByRole("complementary", { name: "Feature details" });
  await details.getByRole("button", { name: "History" }).click();
  await details.getByRole("button", { name: "Restore this version" }).last().click();
  await expect
    .poll(async () => ((await api(page, "GET", `/api/features/${original.id}/`)).body as { geometry: { coordinates: number[][][] } }).geometry.coordinates[0]![0])
    .toEqual(square[0]);
});

test("planning area from bearings and distances, agreed then approved", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Boundary check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();

  const panel = page.getByRole("region", { name: "Planning area" });
  await panel.getByRole("button", { name: "Bearings and distances" }).click();
  const dialog = page.getByRole("dialog", { name: "Boundary from bearings and distances" });
  await dialog.getByLabel("Start easting").fill("1190600");
  await dialog.getByLabel("Start northing").fill("337700");
  await dialog.getByRole("button", { name: "Add leg" }).click();
  const legs = [["N 0 E", "500"], ["90", "500"], ["S 0 E", "500"], ["270 00 00", "500.10"]];
  for (const [i, [bearing, distance]] of legs.entries()) {
    await dialog.getByLabel(`Leg ${i + 1} bearing`).fill(bearing!);
    await dialog.getByLabel(`Leg ${i + 1} distance`).fill(distance!);
  }
  await dialog.getByRole("button", { name: "Compute" }).click();
  await expect(dialog.getByRole("region", { name: "Traverse result" })).toContainText("Misclosure 0.1");
  await expect(dialog.getByRole("region", { name: "Traverse result" })).toContainText("1 in 20,001");
  await dialog.getByRole("button", { name: "Use as boundary" }).click();
  await expect(panel).toContainText("Draft");
  await expect(panel).toContainText("2.32"); // ≈ 500 ft x 500 ft ≈ 2.32 ha
  await panel.getByRole("button", { name: "Mark as agreed" }).click();
  await expect(panel).toContainText("Agreed with stakeholders");
  await expect(panel.getByRole("button", { name: "Approve" })).toHaveCount(0); // planners can't approve
});

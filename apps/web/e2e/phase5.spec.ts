import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";
// Playwright runs from apps/web (ES modules: no __dirname).
const FIXTURES = path.resolve(process.cwd(), "../../fixtures/generated");

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
}

test("planner imports a zipped shapefile, then exports the layer as GeoPackage", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Import check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();

  // Import: the file declares EPSG:2136, so it's preselected and needs no extra confirmation.
  await page.getByRole("button", { name: "Import data" }).click();
  const dialog = page.getByRole("dialog", { name: "Import data" });
  await dialog.getByLabel("File").setInputFiles(path.join(FIXTURES, "shp", "buildings.zip"));
  await dialog.getByRole("button", { name: "Upload and inspect" }).click();
  await expect(dialog.getByLabel("Coordinate system of buildings")).toHaveValue("EPSG:2136");
  // Shapefile truncated "property_id" to "property_i"; map it back.
  await dialog.getByLabel("New field name for property_i").fill("property_id");
  await dialog.getByRole("button", { name: "Import", exact: true }).click();
  const report = dialog.getByRole("region", { name: "Import report" });
  await expect(report).toContainText("6 imported, 0 skipped", { timeout: 30_000 });
  await dialog.getByRole("button", { name: "Close" }).click();

  // The new layer is there with its attributes.
  await page.getByRole("button", { name: "buildings", exact: true }).click();
  const table = page.getByRole("region", { name: "Attributes of buildings" });
  await expect(table.getByRole("cell", { name: "B-001" })).toBeVisible();

  // Export as GeoPackage and receive the zip.
  await page.getByRole("button", { name: "Export" }).click();
  const exportDialog = page.getByRole("dialog", { name: "Export data" });
  const download = page.waitForEvent("download");
  await exportDialog.getByRole("button", { name: "Export" }).click();
  expect((await download).suggestedFilename()).toMatch(/-gpkg-\d{8}-\d{4}\.zip$/);
});

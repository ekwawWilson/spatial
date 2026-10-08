import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";
const FIXTURES = path.resolve(process.cwd(), "../../fixtures/generated");

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
}

test("upload a drone orthophoto, then use it as the project's basemap", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Imagery check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);

  await page.getByRole("link", { name: "Imagery", exact: true }).click();
  const upload = page.getByRole("form", { name: "Upload imagery" });
  await upload.getByLabel("GeoTIFF file").setInputFiles(path.join(FIXTURES, "drone_ortho.tif"));
  await upload.getByLabel("Name").fill("Fixture flight");
  await upload.getByRole("button", { name: "Upload" }).click();

  // Processed in the background: the page keeps checking until it is ready.
  const row = page.getByRole("row").filter({ hasText: "Fixture flight" });
  await expect(row).toContainText("Ready", { timeout: 60_000 });
  await expect(row).toContainText("1.00 m"); // pixel size, read from the file
  await expect(row).toContainText("EPSG:32630");
  await expect(row.getByLabel("Capture date of Fixture flight")).toHaveValue("2026-09-01"); // from the file's tags

  // "Show on map": the project opens with the image as its basemap, zoomed to it,
  // so its tiles come back with picture in them (200), not empty (204).
  const tile = page.waitForResponse((r) => /\/api\/imagery\/\d+\/tiles\/\d+\/\d+\/\d+\.png/.test(r.url()) && r.status() === 200);
  await row.getByRole("button", { name: "Show on map" }).click();
  await page.waitForURL(/\/projects\/\d+$/);
  const basemap = page.getByRole("combobox", { name: "Basemap" });
  await expect(basemap.locator("option:checked")).toHaveText("Fixture flight (imagery)");
  await tile;
  await expect(page.getByRole("region", { name: "Basemap" }).getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Zoom to image" })).toBeVisible();
  await expect(page.getByRole("button", { name: "My location" })).toBeVisible();

  // The checklist's imagery item now measures it.
  await page.getByRole("link", { name: "Readiness checklist" }).click();
  const item = page.getByRole("row").filter({ has: page.getByRole("button", { name: /Recent imagery/ }) });
  await expect(item).toContainText("1 image(s)");
  await expect(item).toContainText("newest captured 2026-09-01");
});

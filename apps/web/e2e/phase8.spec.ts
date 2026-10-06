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

test("save a project as .spp, then open the file as a new project", async ({ page }, testInfo) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const name = `File check ${Date.now()}`;
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(name);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);

  // Some data to carry: the fixture buildings.
  await page.getByRole("button", { name: "Import data" }).click();
  const dialog = page.getByRole("dialog", { name: "Import data" });
  await dialog.getByLabel("File", { exact: true }).setInputFiles(path.join(FIXTURES, "shp", "buildings.zip"));
  await dialog.getByRole("button", { name: "Upload and inspect" }).click();
  await dialog.getByRole("button", { name: "Import", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Import report" })).toContainText("6 imported", { timeout: 30_000 });
  await dialog.getByRole("button", { name: "Close" }).click();

  // Save: one protected file, not a zip.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save as .spp" }).click();
  const saved = await download;
  expect(saved.suggestedFilename()).toMatch(/^file-check-\d+-\d{8}-\d{4}\.spp$/);
  const file = testInfo.outputPath("project.spp");
  await saved.saveAs(file);

  // Open it: the original still exists, so the copy gets a new name.
  await page.getByRole("link", { name: "Projects" }).first().click();
  const section = page.getByRole("region", { name: "Open a project file" });
  await section.getByLabel("Project file").setInputFiles(file);
  const result = section.getByRole("status", { name: "Opened project" });
  await expect(result).toContainText("1 layer, 6 features", { timeout: 30_000 });
  await expect(result).toContainText(`this copy is named "${name} (2)"`);
  await result.getByRole("link", { name: `${name} (2)` }).click();

  // The copy has the layer and its attributes.
  await page.getByRole("button", { name: "buildings", exact: true }).click();
  await expect(page.getByRole("region", { name: "Attributes of buildings" }).getByRole("cell", { name: "B-001" })).toBeVisible();
});

test("a file that isn't a .spp file is refused with an explanation", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const section = page.getByRole("region", { name: "Open a project file" });
  await section.getByLabel("Project file").setInputFiles(path.join(FIXTURES, "shp", "buildings.zip"));
  await expect(section).toContainText("This isn't a .spp project file.");
});

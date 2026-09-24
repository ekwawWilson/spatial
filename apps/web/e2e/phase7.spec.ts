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

async function newProject(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`${name} ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);
}

async function openItem(page: Page, title: string) {
  await page.getByRole("button", { name: title, expanded: false }).click();
  return page.getByRole("region", { name: `Details of ${title}` });
}

test("import from a checklist item: bound to the item, measured, and counted", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await newProject(page, "Readiness check");
  await page.getByRole("link", { name: "Readiness checklist" }).click();
  await expect(page.getByLabel("Readiness score")).toHaveText("0%");

  // Import opens the workspace's wizard bound to the item: a new layer named after it, in domain C.
  const details = await openItem(page, "Buildings and land use");
  await details.getByRole("button", { name: "Import" }).click();
  const dialog = page.getByRole("dialog", { name: "Import data" });
  await expect(dialog).toContainText("For the checklist item Buildings and land use");
  await dialog.getByLabel("File", { exact: true }).setInputFiles(path.join(FIXTURES, "shp", "buildings.zip"));
  await dialog.getByRole("button", { name: "Upload and inspect" }).click();
  await expect(dialog.getByLabel("New layer name for buildings")).toHaveValue("Buildings and land use");
  await expect(dialog.getByLabel("Domain for buildings")).toHaveValue("C");
  await dialog.getByRole("button", { name: "Import", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Import report" })).toContainText("6 imported", { timeout: 30_000 });
  await dialog.getByRole("button", { name: "Close" }).click();

  // Back on the checklist, the item is linked and measured.
  await page.getByRole("link", { name: "Readiness checklist" }).click();
  const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: "Buildings and land use" }) });
  await expect(row).toContainText("6 features");

  // A document item marked ready moves the score.
  await page.getByLabel("Status of Plan period set").selectOption("ready");
  await expect(page.getByLabel("Readiness score")).not.toHaveText("0%");

  // Exports.
  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await csv).suggestedFilename()).toMatch(/\.csv$/);
  const pdf = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export PDF" }).click();
  expect((await pdf).suggestedFilename()).toMatch(/\.pdf$/);
});

test("draw from a checklist item opens editing on a new layer for it", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await newProject(page, "Readiness draw");
  await page.getByRole("link", { name: "Readiness checklist" }).click();
  const details = await openItem(page, "Streets and access");
  await expect(details.getByRole("button", { name: "Send to field" })).toBeDisabled();
  await details.getByRole("button", { name: "Draw" }).click();
  const editing = page.getByRole("region", { name: "Editing" });
  await expect(editing).toContainText("Editing Streets and access");
  await expect(editing.getByRole("button", { name: "Draw" })).toHaveAttribute("aria-pressed", "true");
});

test("district readiness dashboard and template for administrators", async ({ page }) => {
  await signIn(page, "sma.admin@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Readiness" }).click();
  await expect(page.getByRole("heading", { name: "Plan readiness" })).toBeVisible();
  await expect(page.getByLabel("District readiness")).toBeVisible();
  await expect(page.getByRole("region", { name: "Checklist template" })).toContainText("Agreed planning-area boundary");
});

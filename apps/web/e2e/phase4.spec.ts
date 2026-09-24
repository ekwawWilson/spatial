import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
}

test("free basemaps are ready; a keyless Google basemap explains itself instead of a blank map", async ({ page }) => {
  await signIn(page, "sma.admin@example.test");
  const nav = page.getByRole("navigation", { name: "Main" });

  // OpenStreetMap and Esri imagery exist from installation, with offline use not allowed.
  await nav.getByRole("link", { name: "Basemaps" }).click();
  const osmRow = page.getByRole("row").filter({ hasText: "OpenStreetMap" }).first();
  await expect(osmRow).toContainText("Not allowed");
  await expect(page.getByRole("row").filter({ hasText: "Esri World Imagery" }).first()).toBeVisible();

  // Add Google without a key.
  const presetForm = page.getByRole("form", { name: "Add a ready-made basemap" });
  await presetForm.getByLabel("Provider").selectOption("google_roadmap");
  await presetForm.getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("status")).toHaveText("Basemap added.");
  await expect(page.getByRole("row").filter({ hasText: "Google Maps (roadmap)" }).first()).toContainText("Missing");

  // In a project, OpenStreetMap is the default; choosing Google says a key is needed.
  await nav.getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Basemap check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  const picker = page.getByRole("region", { name: "Basemap" });
  await expect(picker.getByRole("combobox")).toHaveValue(/\d+/);
  await expect(picker.getByRole("combobox").locator("option:checked")).toHaveText("OpenStreetMap");
  await picker.getByRole("combobox").selectOption({ label: "Google Maps (roadmap) (needs a key)" });
  await expect(picker.getByRole("alert")).toContainText("needs an API key");
});

test("planners can choose basemaps but not manage them", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Basemaps" })).toHaveCount(0);
});

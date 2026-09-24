import { expect, test, type Page } from "@playwright/test";

// Accounts created by `manage.py seed_demo` (see backend/core/management/commands/seed_demo.py).
const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
}

const nav = (page: Page) => page.getByRole("navigation", { name: "Main" });

test("district admin adds a member and finds the change in the audit log", async ({ page }) => {
  const email = `e2e.${Date.now()}@example.test`;
  await signIn(page, "sma.admin@example.test");

  await nav(page).getByRole("link", { name: "Members" }).click();
  const form = page.getByRole("form", { name: "Add member" });
  await form.getByLabel("Email").fill(email);
  await form.getByLabel("Role").selectOption("field_officer");
  await form.getByRole("button", { name: "Add member" }).click();
  await expect(page.getByRole("cell", { name: email })).toBeVisible();

  await nav(page).getByRole("link", { name: "Audit log" }).click();
  await page.getByLabel("Record type").selectOption("core_membership");
  await page.getByLabel("Change type").selectOption("INSERT");
  const row = page.getByRole("row").filter({ hasText: "sma.admin@example.test" }).first();
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByRole("cell", { name: '"field_officer"', exact: true })).toBeVisible();
});

test("viewer cannot reach administration pages", async ({ page }) => {
  await signIn(page, "sma.viewer@example.test");
  await expect(nav(page).getByRole("link", { name: "Members" })).toHaveCount(0);
  await expect(nav(page).getByRole("link", { name: "Audit log" })).toHaveCount(0);
  await page.goto("/members");
  await expect(page.getByRole("alert")).toHaveText("Your role in this district does not allow this.");
});

test("each district admin only sees their own district", async ({ page }) => {
  await signIn(page, "oda.admin@example.test");
  const switcher = page.getByRole("combobox");
  await expect(switcher.locator("option")).toHaveText(["Other District Assembly"]);
  await nav(page).getByRole("link", { name: "Members" }).click();
  await expect(page.getByRole("cell", { name: "oda.admin@example.test" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "sma.admin@example.test" })).toHaveCount(0);
});

test("system admin can switch to any district", async ({ page }) => {
  await signIn(page, "admin@example.test");
  const switcher = page.getByRole("combobox");
  await expect(switcher.locator("option")).toHaveText(["Other District Assembly", "Sample Municipal Assembly"]);
  await expect(nav(page).getByRole("link", { name: "Users" })).toBeVisible();
});

test("wrong password is refused without revealing whether the account exists", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("sma.planner@example.test");
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Email or password is incorrect");
});

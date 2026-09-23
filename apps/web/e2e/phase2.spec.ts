import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Coordinate systems" }).click();
}

test("planner converts GPS coordinates to the Ghana National Grid with the accuracy stated", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  const form = page.getByRole("form", { name: "Convert coordinates" });
  await form.getByLabel("From").selectOption("EPSG:4326");
  await form.getByLabel("To").selectOption("EPSG:2136");
  await form.getByRole("textbox").fill("-0.2 5.6");
  await form.getByRole("button", { name: "Convert" }).click();
  const result = page.getByRole("region", { name: "Conversion result" });
  // Reference computed with PROJ (Accra to WGS 84 (4)); server output to 3 dp.
  await expect(result).toContainText("E 1190631.452 ft (GC), N 337708.945 ft (GC)");
  await expect(result).toContainText("±6 m");
});

test("district admin sets the district default; it becomes the default for new projects", async ({ page }) => {
  await signIn(page, "sma.admin@example.test");
  await page.getByLabel("District default").selectOption({ label: "EPSG:25000 · Leigon / Ghana Metre Grid" });
  await expect(page.getByRole("status").first()).toContainText("EPSG:25000");
  await expect(page.getByRole("status").first()).toContainText("the district default");
  // Put it back so the test can run again.
  await page.getByLabel("District default").selectOption({ label: "Use the system default" });
  await expect(page.getByRole("status").first()).toContainText("the system default");
});

test("viewer can't change the district default or add systems", async ({ page }) => {
  await signIn(page, "sma.viewer@example.test");
  await expect(page.getByLabel("District default")).toBeDisabled();
  await expect(page.getByRole("form", { name: "Add coordinate system" })).toHaveCount(0);
});

import { expect, test } from "@playwright/test";

test("status page shows every service connected", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Spatial Planning Platform" })).toBeVisible();
  await expect(page.getByText("All services OK")).toBeVisible({ timeout: 15_000 });
});

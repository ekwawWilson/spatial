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

test("two flights are compared, a case is opened, and a notice is issued and served", async ({ page }) => {
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Enforcement check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);

  // Two orthophotos of the same place, a month apart.
  await page.getByRole("link", { name: "Imagery", exact: true }).click();
  const upload = page.getByRole("form", { name: "Upload imagery" });
  for (const [file, name] of [
    ["drone_ortho.tif", "September flight"],
    ["drone_ortho_later.tif", "October flight"],
  ]) {
    await upload.getByLabel("GeoTIFF file").setInputFiles(path.join(FIXTURES, file!));
    await upload.getByLabel("Name").fill(name!);
    await upload.getByRole("button", { name: "Upload" }).click();
    await expect(page.getByRole("row").filter({ hasText: name! })).toContainText("Ready", { timeout: 60_000 });
  }
  await page.getByRole("link", { name: "← Back to the project" }).click();

  // The comparison finds the two places that changed (no buildings layer here, so both are new).
  await page.getByRole("link", { name: "Enforcement", exact: true }).click();
  const compare = page.getByRole("form", { name: "Compare two images" });
  await compare.getByLabel("Earlier image").selectOption({ label: "September flight (2026-09-01)" });
  await compare.getByLabel("Later image").selectOption({ label: "October flight (2026-10-01)" });
  await compare.getByRole("button", { name: "Compare" }).click();
  const found = page.getByRole("region", { name: "Changes between images" }).getByRole("status");
  await expect(found).toContainText("2 place(s) changed", { timeout: 60_000 });
  await expect(found).toContainText("2 new: no permit and no building on the map");

  // A case, a notice to rectify on Form 49, and how it was served.
  await page.getByRole("button", { name: "Open a case" }).click();
  const open = page.getByRole("form", { name: "Open a case" });
  await open.getByLabel("How it came to light").selectOption("detection");
  await open.getByLabel("What was found").fill("A new structure on open ground, seen between two flights");
  await open.getByLabel("Owner or occupier").fill("Kwesi Appiah");
  await open.getByRole("button", { name: "Open the case" }).click();
  await page.waitForURL(/\/enforcement\/\d+$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/SMA\/EN\/\d{4}\/\d{4}/);

  const issue = page.getByRole("form", { name: "Issue a notice" });
  const inTenDays = new Date(Date.now() + 10 * 86_400_000).toISOString().slice(0, 10);
  await issue.getByLabel("Grounds").fill("A structure has been erected without a permit");
  await issue.getByLabel("What must be done").fill("Remove the structure, or apply to regularise it");
  await issue.getByLabel("To comply by").fill(inTenDays);
  await issue.getByRole("button", { name: "Issue the notice" }).click();
  const notice = page.getByRole("article", { name: "Notice for Rectification of Contravention" });
  await expect(notice).toContainText("Form 49");
  await expect(notice).toContainText(`to comply by ${inTenDays}`);
  const download = page.waitForEvent("download");
  await notice.getByRole("button", { name: "Download the notice" }).click();
  expect((await download).suggestedFilename()).toMatch(/^rectification-SMA-EN-.*\.pdf$/);
  await notice.getByLabel("How the Notice for Rectification of Contravention was served").selectOption("on_land");
  await notice.getByRole("button", { name: "Record service today" }).click();
  await expect(notice).toContainText("posted in a conspicuous place on the land or building");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Notice served");
});

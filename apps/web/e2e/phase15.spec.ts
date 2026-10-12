import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "Demo-Pass-2026!";

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

test("zoning standards, then a permit from receipt to a certificate anyone can check", async ({ page }) => {
  await signIn(page, "sma.admin@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Permit check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);
  const project = Number(page.url().split("/").pop());

  // A 100 ft plot zoned "Re B" (Ghana National Grid feet), with a street along its south side.
  const layer = async (name: string, geometry_type: string, schema: object[]) =>
    ((await api(page, "POST", "/api/layers/", { project, name, geometry_type, schema })).body as { id: number }).id;
  const parcels = await layer("Parcels", "polygon", [{ name: "parcel_id", type: "text" }, { name: "land_use", type: "text" }]);
  const streets = await layer("Streets", "line", [{ name: "name", type: "text" }]);
  const plot = { type: "Polygon", coordinates: [[[1190600, 337700], [1190700, 337700], [1190700, 337800], [1190600, 337800], [1190600, 337700]]] };
  const drawn = [
    await api(page, "POST", `/api/layers/${parcels}/features/`, { geometry: plot, properties: { parcel_id: "P-1", land_use: "Re B" } }),
    await api(page, "POST", `/api/layers/${streets}/features/`, { geometry: { type: "LineString", coordinates: [[1190400, 337680], [1190900, 337680]] }, properties: { name: "Station Road" } }),
  ];
  expect(drawn.map((d) => d.status), JSON.stringify(drawn.map((d) => d.body))).toEqual([201, 201]);
  const roles = await api(page, "PUT", `/api/projects/${project}/layer-roles/`, { roles: [{ role: "parcels", layer: parcels }, { role: "streets", layer: streets }] });
  expect(roles.status).toBe(200);

  // Phase 14: the national zones are on the Zoning page; the district adopts the standards.
  await page.getByRole("link", { name: "Zoning", exact: true }).click();
  const zones = page.getByRole("region", { name: "National zones" });
  await expect(zones.getByRole("row").filter({ hasText: "Residential Zone B" })).toContainText("setbacks 6 m front, 3 m side, 3 m back");
  await page.getByRole("link", { name: "← Back to the project" }).click();
  await page.getByRole("link", { name: "Relationships" }).click();
  const standards = page.getByRole("region", { name: "Development standards" });
  await standards.getByRole("button", { name: "Adopt LUSPA's 2025 standards" }).click();
  await expect(standards.getByRole("row").filter({ hasText: "Re B" })).toContainText("6 / 3 / 3");
  await page.getByRole("link", { name: "← Back to the project" }).click();

  // Phase 15: receive an application for five storeys on that plot.
  await page.getByRole("link", { name: "Permits", exact: true }).click();
  await page.getByRole("button", { name: "Receive an application" }).click();
  const receive = page.getByRole("form", { name: "Receive an application" });
  await receive.getByLabel("Applicant").fill("Kofi Boateng");
  await receive.getByLabel("Proposed use").fill("Residential");
  await receive.getByLabel("Storeys").fill("5");
  await receive.getByLabel("Parcel id").fill("P-1");
  const [received] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/api/permits/applications/")),
    receive.getByRole("button", { name: "Receive the application" }).click(),
  ]);
  expect(received.status(), await received.text()).toBe(201);
  await page.waitForURL(/\/permits\/\d+$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/\/DP\/\d{4}\/\d{4}/);

  // The automatic checks, against Re B: the plot is big and wide enough; five storeys is too many.
  const checks = page.getByRole("region", { name: "Automatic checks" });
  await expect(checks.getByRole("row", { name: /Zone/ })).toContainText("Re B, Residential Zone B");
  await expect(checks.getByRole("row", { name: /Plot size/ })).toContainText("Meets it");
  await expect(checks.getByRole("row", { name: /Plot width/ })).toContainText("Meets it");
  await expect(checks.getByRole("row", { name: /Storeys/ })).toContainText("Doesn't meet it");
  await expect(page.getByRole("region", { name: "Deadlines" }).getByRole("listitem")).toHaveCount(4);

  // Through the steps the Regulations set.
  const step = page.getByRole("region", { name: "Next step" });
  await step.getByRole("button", { name: "Acknowledge receipt" }).click();
  const inspection = page.getByRole("form", { name: "Site inspection" });
  await inspection.getByLabel("The plot size").fill("100 ft by 100 ft, as submitted");
  await inspection.getByRole("button", { name: "Record the inspection" }).click();
  await expect(page.getByRole("status")).toContainText("Site inspection recorded");
  const report = page.getByRole("form", { name: "Report" });
  await report.getByLabel("Findings and recommendation").fill("Grant, limited to three storeys.");
  await report.getByRole("button", { name: "Send the report" }).click();
  const decision = page.getByRole("form", { name: "Decision" });
  await decision.getByLabel("Conditions").fill("Not more than three storeys.");
  await decision.getByRole("button", { name: "Record the decision" }).click();
  await expect(step.getByRole("button", { name: "Issue the permit" })).toBeDisabled(); // the permit fee first
  await step.getByLabel("Permit fee", { exact: true }).fill("850");
  await step.getByLabel("Receipt number").fill("GCR 0012345");
  await step.getByRole("button", { name: "Record the receipt" }).click();
  await step.getByRole("button", { name: "Issue the permit" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Permit issued");
  const download = page.waitForEvent("download");
  await step.getByRole("button", { name: "Download the certificate" }).click();
  expect((await download).suggestedFilename()).toMatch(/^certificate-.*\.pdf$/);

  // Anyone with the certificate's code sees the Assembly's record, signed out.
  const href = await step.getByRole("link", { name: "What the QR code shows" }).getAttribute("href");
  await page.evaluate(() => localStorage.clear());
  await page.goto(new URL(href!).pathname);
  await expect(page.getByRole("heading", { name: "A genuine permit, in force" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Permit" })).toContainText("Kofi Boateng");
  await page.goto("/verify/not-a-real-code-0000000000");
  await expect(page.getByRole("heading", { name: "No such permit" })).toBeVisible();
});

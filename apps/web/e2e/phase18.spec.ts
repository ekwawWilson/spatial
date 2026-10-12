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

test("a re-zoning: the abutting land from the map, the display clock, and the decision", async ({ page }) => {
  await signIn(page, "sma.admin@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  await form.getByLabel("Name").fill(`Re-zoning check ${Date.now()}`);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);
  const project = Number(page.url().split("/").pop());

  // Three 100 ft plots (Ghana National Grid feet): P-1 and P-2 share a side; P-3 is across a 60 ft road.
  const made = await api(page, "POST", "/api/layers/", { project, name: "Parcels", geometry_type: "polygon", schema: [{ name: "parcel_id", type: "text" }, { name: "land_use", type: "text" }, { name: "owner", type: "text" }] });
  const parcels = (made.body as { id: number }).id;
  const plot = (x: number, y: number) => ({ type: "Polygon", coordinates: [[[x, y], [x + 100, y], [x + 100, y + 100], [x, y + 100], [x, y]]] });
  const drawn = [
    await api(page, "POST", `/api/layers/${parcels}/features/`, { geometry: plot(1190600, 337700), properties: { parcel_id: "P-1", land_use: "Re A", owner: "Ama Mensah" } }),
    await api(page, "POST", `/api/layers/${parcels}/features/`, { geometry: plot(1190700, 337700), properties: { parcel_id: "P-2", land_use: "Re A", owner: "Kofi Antwi" } }),
    await api(page, "POST", `/api/layers/${parcels}/features/`, { geometry: plot(1190600, 337540), properties: { parcel_id: "P-3", land_use: "Re A", owner: "Esi Owusu" } }),
  ];
  expect(drawn.map((d) => d.status), JSON.stringify(drawn.map((d) => d.body))).toEqual([201, 201, 201]);
  const roles = await api(page, "PUT", `/api/projects/${project}/layer-roles/`, { roles: [{ role: "parcels", layer: parcels }] });
  expect(roles.status).toBe(200);

  await page.getByRole("link", { name: "Re-zoning and subdivision" }).click();
  await page.getByRole("button", { name: "Receive an application" }).click();
  const receive = page.getByRole("form", { name: "Receive an application" });
  await receive.getByLabel("Applicant").fill("Ama Mensah");
  await receive.getByLabel("Parcel ids").fill("P-1");
  await receive.getByLabel("Zone asked for").fill("Re B");
  const [received] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/api/land/applications/")),
    receive.getByRole("button", { name: "Receive the application" }).click(),
  ]);
  expect(received.status(), await received.text()).toBe(201);
  await page.waitForURL(/\/land\/\d+$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/\/RZ\/\d{4}\/\d{4}/);
  await expect(page.getByLabel("Application")).toContainText("the re-zoning of P-1 from Re A to Re B");

  // The owners to be given notice: the plot that touches, not the one across the road.
  const abutting = page.getByRole("region", { name: "Abutting land" });
  await expect(abutting.getByRole("listitem")).toHaveCount(1);
  await expect(abutting).toContainText("P-2: Kofi Antwi");

  // Put on display: the public's 28 days start, and the step is no longer waiting.
  const steps = page.getByRole("region", { name: "Steps and deadlines" });
  await expect(steps.getByRole("row").filter({ hasText: "Displayed in the Public Data Room" })).toContainText("r.33(5)(a)-(b): 7 days");
  await steps.getByRole("button", { name: /^Done today: Displayed/ }).click();
  await expect(page.getByRole("status")).toContainText("Step recorded.");
  await expect(steps.getByRole("row").filter({ hasText: "Displayed in the Public Data Room" })).toContainText(/Done \d{4}-\d{2}-\d{2}/);
  await expect(page.getByLabel("Application")).toContainText("(r.33(7))");

  // An objection is recorded; approval must wait for the comment period, a refusal need not.
  const record = page.getByRole("form", { name: "Record a comment" });
  await record.getByLabel("From").fill("Kofi Antwi");
  await record.getByLabel("What it says").fill("It will overlook my house.");
  await record.getByRole("button", { name: "Record it" }).click();
  await expect(page.getByRole("region", { name: "Comments and objections" })).toContainText("Kofi Antwi: It will overlook my house.");
  await expect(steps.getByRole("row").filter({ hasText: "Objections referred to the applicant" })).toContainText("r.33(14): 14 days");
  const decision = page.getByRole("form", { name: "Decision" });
  await decision.getByRole("button", { name: "Record the decision" }).click();
  await expect(page.getByRole("alert")).toContainText("The public may comment until");
  await decision.getByLabel("The decision").selectOption("refuse");
  await decision.getByLabel("Reasons").fill("Contrary to the structure plan.");
  await decision.getByRole("button", { name: "Record the decision" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Refused");
  const download = page.waitForEvent("download");
  await steps.getByRole("button", { name: "Download: Decision" }).click();
  expect((await download).suggestedFilename()).toMatch(/^decision-.*\.pdf$/);
});

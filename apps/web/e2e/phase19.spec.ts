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


test("a local plan: its steps, a consultation on display, and a comment from the public", async ({ page }) => {
  await signIn(page, "sma.admin@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  const form = page.getByRole("form", { name: "New project" });
  const name = `Plan making ${Date.now()}`;
  await form.getByLabel("Name").fill(name);
  await form.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/\d+$/);
  const project = Number(page.url().split("/").pop());
  // The room is open and this project is in it (set through the API; Phase 16 covers those screens).
  expect((await api(page, "PATCH", "/api/dataroom/", { is_open: true })).status).toBe(200);
  expect([200, 201]).toContain((await api(page, "POST", "/api/dataroom/publications/", { project })).status);

  await page.getByRole("link", { name: "Local plan", exact: true }).click();
  const steps = page.getByRole("region", { name: "Steps and deadlines" });
  await expect(steps.getByRole("row").filter({ hasText: "Notice of commencement" })).toContainText("(Form 27)");
  // The draft cannot be put out before it is complete.
  await steps.getByRole("button", { name: /^Done today: Draft opened for inspection/ }).click();
  await expect(page.getByRole("alert")).toContainText("First: draft local plan completed.");
  await steps.getByRole("button", { name: /^Done today: Notice of commencement/ }).click();
  await expect(steps.getByRole("row").filter({ hasText: "Notice of commencement" })).toContainText(/Done \d{4}-\d{2}-\d{2}/);
  await steps.getByRole("button", { name: /^Done today: Draft local plan completed/ }).click();
  await expect(steps.getByRole("row").filter({ hasText: "Draft local plan completed" })).toContainText(/Done \d{4}-\d{2}-\d{2}/);
  await steps.getByRole("button", { name: /^Done today: Draft opened for inspection/ }).click();
  await expect(steps).toContainText("The public may comment on the draft until");
  // Sixty days for the public first.
  await steps.getByRole("button", { name: "Done today: Local plan approved" }).click();
  await expect(page.getByRole("alert")).toContainText("The public may comment until");

  // A consultation, and its minutes on display (r.65).
  const record = page.getByRole("form", { name: "Record a consultation" });
  const today = new Date().toISOString().slice(0, 10);
  await record.getByLabel("Held on").fill(today);
  await record.getByLabel("Venue").fill("Chief's palace");
  await record.getByLabel("Number attending").fill("84");
  await record.getByLabel("Issues raised").fill("Flooding along the drain.");
  await record.getByRole("button", { name: "Record the consultation" }).click();
  await page.getByRole("button", { name: `Display the minutes of ${today}` }).click();
  await expect(page.getByRole("region", { name: "Consultations" })).toContainText("On display in the Public Data Room since");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download the minutes" }).click();
  expect((await download).suggestedFilename()).toMatch(/^minutes-.*\.pdf$/);

  // Anyone reads the minutes and comments on the draft.
  await page.goto("/public/SMA");
  const plan = page.getByRole("region", { name: "Local plans being made" }).getByRole("article", { name });
  await expect(plan).toContainText("The draft is open for inspection and comment until");
  await expect(plan).toContainText("Chief's palace (84 attending): Flooding along the drain.");
  await plan.getByLabel(`Your name, for ${name}`).fill("Akua Sarpong");
  await plan.getByLabel(`Your comment on ${name}`).fill("The market road needs a walkway.");
  await plan.getByRole("button", { name: "Send the comment" }).click();
  await expect(plan.getByRole("status")).toContainText("has been received");

  // It reaches the planners, who answer it.
  await page.goto(`/projects/${project}/plan`);
  const comments = page.getByRole("region", { name: "Comments on the draft" });
  await expect(comments).toContainText("Akua Sarpong (sent online): The market road needs a walkway.");
  await comments.getByPlaceholder("The Committee's response").fill("A walkway is added on both sides.");
  await comments.getByRole("button", { name: "Record the response" }).click();
  await expect(comments).toContainText("0 of 1 not yet answered");
});

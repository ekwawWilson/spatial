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

test("the public data room: a visitor sees the register and asks; staff answer", async ({ page }) => {
  await signIn(page, "sma.admin@example.test");
  const name = `Data room check ${Date.now()}`;
  const project = ((await api(page, "POST", "/api/projects/", { name })).body as { id: number }).id;
  const received = await api(page, "POST", "/api/permits/applications/", { project, kind: "development", category: "building", applicant_name: "Esi Nyarko", applicant_phone: "0240000000", proposed_use: "Shop" });
  expect(received.status).toBe(201);
  const number = (received.body as { number: string }).number;

  // The administrator opens the room and publishes the project.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Public Data Room" }).click();
  const opening = page.getByRole("region", { name: "Opening" });
  await expect(opening.getByText(/The room is/)).toBeVisible();
  const open = opening.getByRole("button", { name: "Open the room online" });
  if (await open.isVisible()) await open.click();
  await expect(opening.getByRole("link", { name: "/public/SMA" })).toBeVisible();
  const publish = page.getByRole("form", { name: "Publish a project" });
  await publish.getByLabel("Project to publish").selectOption({ label: name });
  await publish.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("region", { name: "Published projects" }).getByRole("row").filter({ hasText: name })).toBeVisible();

  // Signed out: anyone can read the register, without the applicant's name or phone.
  await page.evaluate(() => localStorage.clear());
  await page.goto("/public/SMA");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Public Data Room");
  const register = page.getByRole("region", { name: "Register of permits" });
  await register.getByLabel("Find in the register").fill(number);
  const row = register.getByRole("row").filter({ hasText: number });
  await expect(row).toContainText("Pending");
  await expect(row).toContainText(name);
  await expect(register).not.toContainText("Esi Nyarko");
  await expect(page.locator("body")).not.toContainText("0240000000");

  const check = page.getByRole("region", { name: "Check an application" });
  await check.getByLabel("Application number").fill(number);
  await check.getByRole("button", { name: "Check" }).click();
  await expect(check.getByRole("status")).toContainText("Acknowledge receipt in writing, by");

  const ask = page.getByRole("region", { name: "Ask for information" });
  const subject = `Zoning of plot ${Date.now()}`;
  await ask.getByLabel("Your name").fill("Kojo Antwi");
  await ask.getByLabel("Phone").fill("0200000000");
  await ask.getByLabel("About").fill(subject);
  await ask.getByLabel("What you would like to know").fill("What is the plot zoned for?");
  await ask.getByRole("button", { name: "Send the request" }).click();
  await expect(ask.getByRole("status")).toContainText(/Your reference is SMA\/IR\/\d{4}\/\d{4}/);
  const reference = (await ask.getByRole("status").innerText()).match(/SMA\/IR\/\d{4}\/\d{4}/)![0];

  // A planner sees the request with its five-day date, and records the answer.
  await signIn(page, "sma.planner@example.test");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Public Data Room" }).click();
  const request = page.getByRole("article", { name: reference });
  await expect(request).toContainText(subject);
  await expect(request).toContainText("due by");
  await request.getByLabel(`Answer to ${reference}`).fill("Re B, medium-density residential.");
  await request.getByRole("button", { name: "Record the answer" }).click();
  await expect(request).toContainText("Answer: Re B, medium-density residential.");
  // A planner can't open or close the room.
  await expect(page.getByRole("button", { name: /the room online/ })).toHaveCount(0);
});

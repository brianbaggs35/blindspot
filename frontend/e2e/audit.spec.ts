import { expect, test } from "./fixtures";
import { newPerson, PASSWORD, uniqueName } from "./people";
import { pickOption } from "./vuetify";

test.describe("Audit log (administrator)", () => {
  test("shows what an administrator did, newest first, and narrows by action and name", async ({
    page,
    request,
    baseURL,
  }) => {
    const origin = new URL(baseURL ?? "").origin;
    const username = uniqueName("audited");
    const made = await request.post("/api/users", {
      headers: { Origin: origin },
      data: { username, display_name: "", role: "viewer", password: PASSWORD },
    });
    expect(made.status()).toBe(201);

    await page.goto("/audit");
    await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
    const events = page.getByRole("list", { name: "Audit events" });
    await pickOption(page, page, "Action", "Added an account");
    await page.getByRole("button", { name: "Apply filters" }).click();
    const added = events.locator(".v-list-item", { hasText: `username: ${username}` });
    await expect(added).toContainText("Added an account");
    await expect(added).toContainText("e2e-admin");

    await pickOption(page, page, "Action", "Deleted an account");
    await page.getByLabel("Username").fill("nobody-with-this-name");
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(page.getByText("No events match these filters")).toBeVisible();
    await page.getByRole("button", { name: "Clear the filters" }).click();
    await expect(events.locator(".v-list-item").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Clear", exact: true })).toHaveCount(0);
  });

  test("filters by outcome and since a day", async ({ page, playwright, baseURL }) => {
    const person = await newPerson(playwright, baseURL);
    const origin = new URL(baseURL ?? "").origin;
    const context = await playwright.request.newContext({
      baseURL: origin,
      ignoreHTTPSErrors: true,
    });
    await context.post("/api/auth/login", {
      headers: { Origin: origin },
      data: { username: person.username, password: "not the password at all" },
    });
    await context.dispose();

    await page.goto("/audit");
    await pickOption(page, page, "Outcome", /^Failed$/);
    await page.getByLabel("Username").fill(person.username);
    await page.getByRole("button", { name: "Apply filters" }).click();
    const events = page.getByRole("list", { name: "Audit events" });
    await expect(events.locator(".v-list-item")).toHaveCount(1);
    await expect(events).toContainText("Signed in with a password");
    await expect(events).toContainText("failed");

    // A day in the future shows nothing, today shows the event.
    await page.getByLabel("Since").fill("2999-01-01");
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(page.getByText("No events match these filters")).toBeVisible();
    await page.getByLabel("Since").fill("2000-01-01");
    await page.getByRole("button", { name: "Apply filters" }).click();
    await expect(events.locator(".v-list-item")).toHaveCount(1);
  });

  test("pages through older events", async ({ page, request, playwright, baseURL }) => {
    const origin = new URL(baseURL ?? "").origin;
    const person = await newPerson(playwright, baseURL);
    const list = await request.get("/api/users");
    const id = ((await list.json()) as { id: string; username: string }[]).find(
      (user) => user.username === person.username,
    )?.id;
    // More than a page of events, so the button to show older ones appears.
    for (let count = 0; count < 52; count += 1) {
      const answer = await request.post(`/api/users/${id ?? ""}/sign-out`, {
        headers: { Origin: origin },
      });
      expect(answer.status()).toBe(204);
    }
    await page.goto("/audit");
    const events = page.getByRole("list", { name: "Audit events" });
    await expect(events.locator(".v-list-item")).toHaveCount(50);
    await page.getByRole("button", { name: "Show older events" }).click();
    await expect(events.locator(".v-list-item")).not.toHaveCount(50);
  });
});

import { SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import { openSetup } from "./open-page";
import {
  alertOn,
  newPerson,
  PASSWORD,
  signInThroughThePage,
  signOutThroughThePage,
} from "./people";

test.describe("signing in and out", () => {
  test.use({ storageState: SIGNED_OUT });

  test("a visitor is sent to sign in and, afterwards, to the page they wanted", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in\?next=(%2F|\/)account/);
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await page.getByLabel("Username").fill(person.username);
    await page.getByLabel("Password", { exact: true }).fill(person.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole("heading", { name: "Account", level: 1 })).toBeVisible();
  });

  test("a wrong password is refused in plain words, then the right one works", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await page.goto("/sign-in");
    await page.getByLabel("Username").fill(person.username);
    await page.getByLabel("Password", { exact: true }).fill("not the password at all");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(alertOn(page)).toContainText("the account is locked");
    await expect(page).toHaveURL(/\/sign-in/);
    await page.getByLabel("Password", { exact: true }).fill(person.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  });

  test("the password can be shown while typing", async ({ page }) => {
    await page.goto("/sign-in");
    const field = page.getByLabel("Password", { exact: true });
    await field.fill("hidden words");
    await expect(field).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show the password" }).click();
    await expect(field).toHaveAttribute("type", "text");
  });

  test("an address that is not on this site is never followed after sign-in", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await page.goto("/sign-in?next=//evil.example/steal");
    await page.getByLabel("Username").fill(person.username);
    await page.getByLabel("Password", { exact: true }).fill(person.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
    expect(new URL(page.url()).host).toBe(new URL(baseURL ?? "").host);
  });

  test("signing out ends the session and the menu goes away", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await signInThroughThePage(page, person);
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    await signOutThroughThePage(page);
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await page.goto("/");
    await expect(page).toHaveURL(/\/sign-in/);
  });

  test("an account locks after repeated wrong passwords, and says nothing more than usual", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await page.goto("/sign-in");
    await page.getByLabel("Username").fill(person.username);
    for (let attempt = 0; attempt < 5; attempt += 1) {
      await page.getByLabel("Password", { exact: true }).fill(`wrong password ${String(attempt)}`);
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(alertOn(page)).toBeVisible();
    }
    const refusal = (await alertOn(page).innerText()).replace(/\s*\(reference .*\)/, "");
    await page.getByLabel("Password", { exact: true }).fill(person.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    // The right password is refused too, in the same words: a locked account looks like any other failure.
    await expect(alertOn(page)).toContainText(refusal);
    await expect(page).toHaveURL(/\/sign-in/);
  });

  test("setup is closed once an administrator exists", async ({ page }) => {
    await page.goto("/setup");
    await expect(page).toHaveURL(/\/sign-in/);
  });
});

test.describe("first-run setup", () => {
  test.use({ storageState: SIGNED_OUT });

  test("the page guides the password and sends what was typed", async ({ page }) => {
    let sent: unknown;
    await page.route("**/api/auth/setup", async (route) => {
      sent = route.request().postDataJSON();
      await route.fulfill({
        json: {
          id: "00000000-0000-7000-8000-000000000009",
          username: "first",
          display_name: "First",
          role: "admin",
          is_active: true,
          last_sign_in_at: null,
          created_at: "2026-11-23T00:00:00Z",
        },
      });
    });
    await openSetup(page);
    await expect(page.getByRole("heading", { name: "Set up Blindspot", level: 1 })).toBeVisible();

    await page.getByLabel("Setup code").fill("BLND-TEST-CODE-0001");
    await page.getByLabel("Username").fill("first");
    await page.getByLabel("Name (optional)").fill("First");
    const rules = page.getByRole("list", { name: "Password rules" });
    await expect(rules).toContainText("At least 12 characters (not yet)");
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await expect(rules).toContainText("At least 12 characters (done)");
    await page.getByLabel("Type the password again").fill("something different");
    await expect(page.getByText("The two passwords are different.")).toBeVisible();
    await page.getByLabel("Type the password again").fill(PASSWORD);
    await page.getByRole("button", { name: "Create the administrator" }).click();

    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
    expect(sent).toEqual({
      setup_code: "BLND-TEST-CODE-0001",
      username: "first",
      display_name: "First",
      password: PASSWORD,
    });
  });

  test("a refused code is shown and the form stays", async ({ page }) => {
    await page.route("**/api/auth/setup", (route) =>
      route.fulfill({
        status: 403,
        contentType: "application/problem+json",
        json: { code: "setup_code_invalid", title: "That setup code is not right" },
      }),
    );
    await openSetup(page);
    await page.getByLabel("Setup code").fill("wrong");
    await page.getByLabel("Username").fill("first");
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Type the password again").fill(PASSWORD);
    await page.getByRole("button", { name: "Create the administrator" }).click();
    await expect(alertOn(page)).toContainText("setup code is not right");
    await expect(page).toHaveURL(/\/setup/);
  });
});

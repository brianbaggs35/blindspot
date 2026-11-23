import { type Browser, type Page } from "@playwright/test";
import { SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import {
  alertOn,
  newPerson,
  PASSWORD,
  signInThroughThePage,
  uniqueName,
  type Person,
} from "./people";
import { pickOption } from "./vuetify";

const OTHER_PASSWORD = "copper meadow lantern 2027";

function row(page: Page, username: string) {
  return page.locator(".v-list-item", { hasText: username }).first();
}

async function choose(page: Page, username: string, action: string) {
  await page.getByRole("button", { name: `Actions for ${username}` }).click();
  await page.locator(".v-menu .v-list-item", { hasText: action }).click();
}

/** A second browser, signed in as `person`: what they would see while an administrator works. */
async function browserFor(
  browser: Browser,
  baseURL: string | undefined,
  person: Person,
  landsOn?: string,
) {
  const context = await browser.newContext({
    baseURL: baseURL ?? "",
    storageState: SIGNED_OUT,
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  await signInThroughThePage(page, person, { landsOn });
  return { context, page };
}

test.describe("Users (administrator)", () => {
  test("adds a user who can then sign in", async ({ page, browser, baseURL }) => {
    const username = uniqueName("added");
    await page.goto("/users");
    await expect(page.getByRole("heading", { name: "Users", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "Add a user" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Username").fill(username);
    await dialog.getByLabel("Name", { exact: true }).fill("Added Person");
    await dialog.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await dialog.getByRole("button", { name: "Add user" }).click();
    await expect(row(page, username)).toContainText("viewer");
    await expect(page.getByText(`Added ${username}.`)).toBeVisible();
    // A new account reads and accepts the terms of use before it sees the app.
    const other = await browserFor(
      browser,
      baseURL,
      { username, password: PASSWORD },
      "Terms of use",
    );
    await other.page.getByRole("checkbox", { name: /I have read these terms/ }).check();
    await other.page.getByRole("button", { name: "Accept and continue" }).click();
    await expect(other.page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
    await expect(other.page.getByRole("link", { name: "Users" })).toHaveCount(0);
    await other.context.close();
  });

  test("explains a username that is taken and a password that breaks the rules", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const existing = await newPerson(playwright, baseURL);
    await page.goto("/users");
    await page.getByRole("button", { name: "Add a user" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Username").fill(existing.username);
    await dialog.getByLabel("Password", { exact: true }).fill("short");
    await dialog.getByRole("button", { name: "Add user" }).click();
    await expect(alertOn(page)).toContainText("Check the password rules");
    await dialog.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await dialog.getByRole("button", { name: "Add user" }).click();
    await expect(alertOn(page)).toContainText("already used");
  });

  test("changes a role and stops an account signing in", async ({
    page,
    browser,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await page.goto("/users");
    await choose(page, person.username, "Edit");
    const dialog = page.getByRole("dialog");
    await pickOption(dialog, page, "Role", /Administrator/);
    // The switch's own input is hidden behind its track; its label toggles it like a click would.
    await dialog.getByText("Can sign in").click();
    await expect(dialog.getByLabel("Can sign in")).not.toBeChecked();
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(row(page, person.username)).toContainText("admin");
    await expect(row(page, person.username)).toContainText("disabled");
    const context = await browser.newContext({
      baseURL: baseURL ?? "",
      storageState: SIGNED_OUT,
      ignoreHTTPSErrors: true,
    });
    const other = await context.newPage();
    await other.goto("/sign-in");
    await other.getByLabel("Username").fill(person.username);
    await other.getByLabel("Password", { exact: true }).fill(person.password);
    await other.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(alertOn(other)).toContainText("wrong, or the account is locked");
    await context.close();
  });

  test("resets a password: the new one works and the old one does not", async ({
    page,
    browser,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    const signedIn = await browserFor(browser, baseURL, person);
    await page.goto("/users");
    await choose(page, person.username, "Reset password");
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("New password").fill(OTHER_PASSWORD);
    await dialog.getByRole("button", { name: "Reset password" }).click();
    await expect(page.getByText(`${person.username} was signed out everywhere`)).toBeVisible();
    // Their open browser was signed out by the reset.
    await signedIn.page.goto("/account");
    await expect(signedIn.page).toHaveURL(/\/sign-in/);
    await signInThroughThePage(signedIn.page, {
      username: person.username,
      password: OTHER_PASSWORD,
    });
    await signedIn.context.close();
  });

  test("signs a user out everywhere, after asking", async ({
    page,
    browser,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    const signedIn = await browserFor(browser, baseURL, person);
    await page.goto("/users");
    await choose(page, person.username, "Sign out everywhere");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(`Sign ${person.username} out everywhere?`);
    await dialog.getByRole("button", { name: "Sign out everywhere" }).click();
    await expect(page.getByText(`${person.username} was signed out everywhere.`)).toBeVisible();
    await signedIn.page.goto("/account");
    await expect(signedIn.page).toHaveURL(/\/sign-in/);
    await signedIn.context.close();
  });

  test("deletes a user after asking, and not your own account", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await page.goto("/users");
    await choose(page, person.username, "Delete");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(`Delete ${person.username}?`);
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(row(page, person.username)).toBeVisible();
    await choose(page, person.username, "Delete");
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText(`Deleted ${person.username}.`)).toBeVisible();
    await expect(page.locator(".v-list-item", { hasText: person.username })).toHaveCount(0);
    await page.getByRole("button", { name: /^Actions for e2e-admin$/ }).click();
    await expect(page.locator(".v-menu .v-list-item", { hasText: "Delete" })).toHaveClass(
      /v-list-item--disabled/,
    );
  });

  test("is in the menu for an administrator", async ({ page }) => {
    await page.goto("/");
    const menu = page.getByRole("navigation", { name: "Main" });
    await expect(menu.getByRole("link", { name: "Users" })).toBeVisible();
    await expect(menu.getByRole("link", { name: "Audit log" })).toBeVisible();
  });
});

test.describe("Users and the audit log (viewer)", () => {
  test.use({ storageState: SIGNED_OUT });

  test("a viewer has neither page nor menu entry", async ({ page, playwright, baseURL }) => {
    const person = await newPerson(playwright, baseURL, "viewer");
    await signInThroughThePage(page, person);
    const menu = page.getByRole("navigation", { name: "Main" });
    await expect(menu.getByRole("link", { name: "Account" })).toBeVisible();
    await expect(menu.getByRole("link", { name: "Users" })).toHaveCount(0);
    await expect(menu.getByRole("link", { name: "Audit log" })).toHaveCount(0);
    for (const path of ["/users", "/audit"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: "No access", level: 1 })).toBeVisible();
      await expect(page.getByText("This page is for administrators")).toBeVisible();
    }
  });
});

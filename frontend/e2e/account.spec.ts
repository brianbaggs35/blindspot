import type { BrowserContext, Page } from "@playwright/test";
import { SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import { alertOn, newPerson, signInThroughThePage, signOutThroughThePage } from "./people";

test.use({ storageState: SIGNED_OUT });

test.describe("the account page", () => {
  test("shows who is signed in, and what a viewer can do", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL, "viewer");
    await signInThroughThePage(page, person);
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Account" })
      .click();
    await expect(page.getByRole("heading", { name: "Account", level: 1 })).toBeVisible();
    await expect(page.getByText(person.username)).toBeVisible();
    await expect(page.getByText("can look, not change")).toBeVisible();
  });

  test("changes the password: the old one stops working and the new one signs in", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await signInThroughThePage(page, person);
    await page.goto("/account");

    await page.getByLabel("Current password").fill("not my current password");
    await page.getByLabel("New password", { exact: true }).fill("amber meadow compass 2027");
    await page.getByLabel("Type the new password again").fill("amber meadow compass 2027");
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(alertOn(page)).toContainText("current password is wrong");

    await page.getByLabel("Current password").fill(person.password);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.locator(".v-alert[role=status]")).toContainText("Password changed");

    await signOutThroughThePage(page);
    await page.getByLabel("Username").fill(person.username);
    await page.getByLabel("Password", { exact: true }).fill(person.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(alertOn(page)).toBeVisible();
    await page.getByLabel("Password", { exact: true }).fill("amber meadow compass 2027");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  });

  test("refuses a password that breaks the rules before asking the server", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await signInThroughThePage(page, person);
    await page.goto("/account");
    await page.getByLabel("Current password").fill(person.password);
    await page.getByLabel("New password", { exact: true }).fill("short");
    await page.getByLabel("Type the new password again").fill("short");
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(alertOn(page)).toContainText("password rules");
  });
});

test.describe("sessions", () => {
  test("lists where you are signed in and ends another browser", async ({
    page,
    browser,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await signInThroughThePage(page, person);
    const other: BrowserContext = await browser.newContext();
    const otherPage: Page = await other.newPage();
    await signInThroughThePage(otherPage, person);

    await page.goto("/account");
    const sessions = page
      .getByRole("heading", { name: "Where you are signed in" })
      .locator("../..");
    await expect(sessions.getByText("This browser")).toBeVisible();
    await sessions.getByRole("button", { name: /^Sign out / }).click();
    await expect(sessions.getByRole("button", { name: /^Sign out / })).toHaveCount(0);

    // The other browser finds out the next time it asks, and is sent to sign in again.
    await otherPage.goto("/account");
    await expect(otherPage).toHaveURL(/\/sign-in\?next=(%2F|\/)account/);
    await other.close();
  });

  test("a session that ends while a page is open sends the person to sign in", async ({
    page,
    browser,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await signInThroughThePage(page, person);
    await page.goto("/account");
    const other = await browser.newContext();
    const otherPage = await other.newPage();
    await signInThroughThePage(otherPage, person);
    // Signing out everywhere else is what changing the password does.
    await otherPage.goto("/account");
    await otherPage.getByLabel("Current password").fill(person.password);
    await otherPage.getByLabel("New password", { exact: true }).fill("copper valley signal 2028");
    await otherPage.getByLabel("Type the new password again").fill("copper valley signal 2028");
    await otherPage.getByRole("button", { name: "Change password" }).click();
    await expect(otherPage.locator(".v-alert[role=status]")).toBeVisible();
    // The first page is still open, now with a revoked session: its next request notices.
    await page
      .getByRole("button", { name: "Try again" })
      .first()
      .click({ timeout: 1000 })
      .catch(() => undefined);
    await page.reload();
    await expect(page).toHaveURL(/\/sign-in\?next=(%2F|\/)account/);
    await other.close();
  });
});

test("signing in works from the keyboard alone", async ({ page, playwright, baseURL }) => {
  const person = await newPerson(playwright, baseURL);
  await page.goto("/sign-in");
  await page.getByLabel("Username").focus();
  await page.keyboard.type(person.username);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.keyboard.type(person.password);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
});

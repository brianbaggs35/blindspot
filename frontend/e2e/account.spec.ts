import type { BrowserContext, Page } from "@playwright/test";
import { container, SIGNED_OUT } from "./accounts";
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

// Passkeys need a name the browser accepts (not an IP address) and a page without certificate
// errors, so they are checked against the host-mode server on localhost.
test.describe("passkeys", () => {
  test.skip(container, "passkeys need a trusted certificate");

  async function virtualAuthenticator(page: Page) {
    const client = await page.context().newCDPSession(page);
    await client.send("WebAuthn.enable");
    await client.send("WebAuthn.addVirtualAuthenticator", {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    });
  }

  test("adds, renames, uses and removes a passkey", async ({
    page,
    browser,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await virtualAuthenticator(page);
    await signInThroughThePage(page, person);
    await page.goto("/account");
    const card = page.getByRole("heading", { name: "Passkeys" }).locator("../..");
    await expect(card.getByText("No passkeys yet")).toBeVisible();

    // Adding one asks for the password again, and a wrong one is refused.
    await card.getByRole("button", { name: "Add a passkey" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name").fill("Test laptop");
    await dialog.getByLabel("Your password").fill("definitely not the password");
    await dialog.getByRole("button", { name: "Add passkey" }).click();
    await expect(dialog.locator(".v-alert")).toBeVisible();
    await dialog.getByLabel("Your password").fill(person.password);
    await dialog.getByRole("button", { name: "Add passkey" }).click();
    await expect(card.getByText("Test laptop")).toBeVisible();

    await card.getByRole("button", { name: "Rename Test laptop" }).click();
    await dialog.getByLabel("Name").fill("Work laptop");
    await dialog.getByRole("button", { name: "Rename" }).click();
    await expect(card.getByText("Work laptop")).toBeVisible();

    // Sign in with it, from a browser that has the same authenticator but no session.
    const other = await browser.newContext();
    const otherPage = await other.newPage();
    const client = await other.newCDPSession(otherPage);
    await client.send("WebAuthn.enable");
    // A second virtual authenticator would not hold the credential; use the first page's instead.
    await other.close();
    await signOutThroughThePage(page);
    await page.getByRole("button", { name: "Sign in with a passkey" }).click();
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();

    await page.goto("/account");
    await card.getByRole("button", { name: "Remove Work laptop" }).click();
    await dialog.getByLabel("Your password").fill(person.password);
    await dialog.getByRole("button", { name: "Remove" }).click();
    await expect(card.getByText("No passkeys yet")).toBeVisible();
  });

  test("closing the browser's passkey prompt is explained, not an error page", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL);
    await signInThroughThePage(page, person);
    await signOutThroughThePage(page);
    // An authenticator that holds no passkey for this site: the prompt cannot be satisfied.
    await virtualAuthenticator(page);
    await page.getByRole("button", { name: "Sign in with a passkey" }).click();
    await expect(alertOn(page)).toContainText("passkey prompt was closed");
    await expect(page).toHaveURL(/\/sign-in/);
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

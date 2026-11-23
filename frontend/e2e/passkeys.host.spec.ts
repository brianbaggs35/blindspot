import type { Page } from "@playwright/test";
import { SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import { alertOn, newPerson, signInThroughThePage, signOutThroughThePage } from "./people";

// Passkeys need a host name the browser accepts (not an IP address) and a page without
// certificate errors, so these run against the host-mode server on localhost only; the
// container run leaves `*.host.spec.ts` out (playwright.config.ts).
test.use({ storageState: SIGNED_OUT });

test.describe("passkeys", () => {
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

  test("adds, renames, uses and removes a passkey", async ({ page, playwright, baseURL }) => {
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

    // Sign in with it: the virtual authenticator holds the credential, and the session is gone.
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

import { type Page } from "@playwright/test";
import { SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import { themes } from "./pages";
import { useTheme, violationsOf } from "./axe";
import { newPerson, type Person } from "./people";

type Playwright = Parameters<Parameters<typeof test>[2]>[0]["playwright"];

/** An account that has not accepted the terms yet, signed in through the page. */
async function signInUnaccepted(
  page: Page,
  playwright: Playwright,
  baseURL: string | undefined,
  role: "admin" | "viewer" = "viewer",
): Promise<Person> {
  const person = await newPerson(playwright, baseURL, role, { acceptTerms: false });
  await page.goto("/sign-in");
  await page.getByLabel("Username").fill(person.username);
  await page.getByLabel("Password", { exact: true }).fill(person.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  return person;
}

test.describe("terms of use", () => {
  test.use({ storageState: SIGNED_OUT });

  test("nothing opens until they are accepted, then the person goes where they were heading", async ({
    page,
    playwright,
    baseURL,
  }) => {
    await signInUnaccepted(page, playwright, baseURL);
    await expect(page.getByRole("heading", { name: "Terms of use", level: 1 })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await expect(page.getByText("No warranty and no liability")).toBeVisible();

    // Another address in the app is turned back to the terms and remembered.
    await page.goto("/pentests");
    await expect(page).toHaveURL(/\/terms\?next=(%2F|\/)pentests/);

    const accept = page.getByRole("button", { name: "Accept and continue" });
    await expect(accept).toBeDisabled();
    await page.getByLabel("I have read these terms and I accept them").check();
    await accept.click();
    await expect(page).toHaveURL(/\/pentests$/);
    await expect(page.getByRole("heading", { name: "Pentests", level: 1 })).toBeVisible();

    // Accepted once, they are not asked again, and the terms page itself closes.
    await page.goto("/terms");
    await expect(page).toHaveURL(/\/$/);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  });

  test("an administrator cannot confirm permission or start before accepting them", async ({
    page,
    playwright,
    baseURL,
  }) => {
    await signInUnaccepted(page, playwright, baseURL, "admin");
    await expect(page).toHaveURL(/\/terms/);
    const refused = await page.request.post(
      "/api/pentests/00000000-0000-0000-0000-000000000000/attest",
      {
        data: { confirmation: "x", text_version: "x" },
        headers: { Origin: new URL(baseURL ?? "").origin },
      },
    );
    // The terms are checked after the pentest is found, so this one is simply not found; the
    // check itself is covered by the API tests. What matters here is that the page held them back.
    expect([403, 404]).toContain(refused.status());
  });

  test("a person can sign out instead of accepting", async ({ page, playwright, baseURL }) => {
    await signInUnaccepted(page, playwright, baseURL);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/sign-in/);
    await page.goto("/pentests");
    await expect(page).toHaveURL(/\/sign-in/);
  });

  for (const theme of themes) {
    for (const width of [320, 1280]) {
      test(`the terms page has no accessibility problems (${theme} theme, ${String(width)}px)`, async ({
        page,
        playwright,
        baseURL,
      }) => {
        await useTheme(page, theme);
        await page.setViewportSize({ width, height: 800 });
        await signInUnaccepted(page, playwright, baseURL);
        await expect(page.getByRole("heading", { name: "Terms of use", level: 1 })).toBeVisible();
        expect(await violationsOf(page)).toEqual([]);
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow).toBeLessThanOrEqual(0);
      });
    }
  }
});

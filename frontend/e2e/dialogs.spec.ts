import { type Page } from "@playwright/test";
import { ADMIN_STATE } from "./accounts";
import { expect, test } from "./fixtures";
import { themes } from "./pages";
import { useTheme, violationsOf } from "./axe";
import { newProvider } from "./providers";
import { uniqueName } from "./people";

// Every dialog needs a name a screen reader can say, and nothing in it may break the rules axe
// checks. Each one is opened here, in both themes, because a closed dialog is not on the page.
async function clean(page: Page): Promise<void> {
  expect(await violationsOf(page)).toEqual([]);
}

for (const theme of themes) {
  test.describe(`Dialogs (${theme} theme)`, () => {
    test.beforeEach(async ({ page }) => {
      await useTheme(page, theme);
    });

    test("the methodology dialogs", async ({ page }) => {
      await page.goto("/methodologies");
      await page.getByRole("button", { name: "Check for updates" }).click();
      await expect(page.getByRole("dialog", { name: /^Update / })).toBeVisible();
      await clean(page);
      await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
      await expect(page.getByRole("dialog")).toBeHidden();

      await page.getByRole("button", { name: /Information Gathering/ }).click();
      await page.getByRole("listitem", { name: /WSTG-INFO-02/ }).click();
      await expect(page.getByRole("dialog", { name: /^WSTG-INFO-02 · / })).toBeVisible();
      await clean(page);
      await page.getByRole("button", { name: "Edit the playbook" }).click();
      await expect(page.getByRole("dialog", { name: "Edit the playbook" })).toBeVisible();
      await clean(page);
    });

    test("the models dialog", async ({ page, playwright, baseURL }) => {
      const made = await newProvider(playwright, baseURL);
      await page.goto("/ai-providers");
      await page
        .locator(".v-card", { has: page.getByText(made.name, { exact: true }) })
        .last()
        .getByRole("button", { name: "Models" })
        .click();
      await expect(page.getByRole("dialog", { name: `Models of ${made.name}` })).toBeVisible();
      await clean(page);
    });

    test("the checklist dialog", async ({ page, playwright, baseURL }) => {
      const origin = new URL(baseURL ?? "").origin;
      const admin = await playwright.request.newContext({
        baseURL: origin,
        storageState: ADMIN_STATE,
        ignoreHTTPSErrors: true,
      });
      const made = await admin.post("/api/pentests", {
        headers: { Origin: origin },
        data: {
          name: uniqueName("dialogs"),
          methodology_id: "wstg",
          scope: { in_scope: ["https://shop.example.com"] },
        },
      });
      expect(made.status()).toBe(201);
      const { id } = (await made.json()) as { id: string };
      await admin.dispose();
      await page.goto(`/pentests/${id}/checklist`);
      await page.getByRole("textbox", { name: "Search tests, ids and notes" }).fill("WSTG-INFO-01");
      await page.getByRole("listitem", { name: /WSTG-INFO-01/ }).click();
      await expect(
        page.getByRole("dialog", { name: /Search Engine Reconnaissance/ }),
      ).toBeVisible();
      await clean(page);
    });
  });
}

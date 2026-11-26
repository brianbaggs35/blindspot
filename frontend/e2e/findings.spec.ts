import { type Page } from "@playwright/test";
import { ADMIN_STATE } from "./accounts";
import { expect, test } from "./fixtures";
import { axeResults, useTheme } from "./axe";
import { uniqueName } from "./people";
import { themes } from "./pages";
import { pickOption } from "./vuetify";

const SCOPE = "https://shop.example.com";
const VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N";

type Playwright = Parameters<Parameters<typeof test>[2]>[0]["playwright"];

/** Makes a pentest straight through the API and returns its id. */
async function makeThroughApi(playwright: Playwright, baseURL: string | undefined, name: string) {
  const origin = new URL(baseURL ?? "").origin;
  const admin = await playwright.request.newContext({
    baseURL: origin,
    storageState: ADMIN_STATE,
    ignoreHTTPSErrors: true,
  });
  const made = await admin.post("/api/pentests", {
    headers: { Origin: origin },
    data: { name, methodology_id: "wstg", scope: { in_scope: [SCOPE] } },
  });
  expect(made.status()).toBe(201);
  const { id } = (await made.json()) as { id: string };
  await admin.dispose();
  return id;
}

async function open(page: Page, id: string, name: string) {
  await page.goto(`/pentests/${id}/findings`);
  await expect(page.getByRole("heading", { name: `Findings: ${name}`, level: 1 })).toBeVisible();
}

async function write(page: Page, title: string) {
  await page.getByRole("button", { name: "Write a finding" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Title").fill(title);
  await dialog.getByLabel("What is wrong").fill("Nothing stops a script from trying passwords.");
  const vector = dialog.getByRole("textbox", { name: "CVSS 4.0 vector" });
  await vector.fill(VECTOR);
  await vector.blur();
  await expect(dialog.getByRole("status")).toContainText("High");
  await dialog.getByRole("button", { name: "Add the finding" }).click();
  await expect(page.getByText("Finding added.")).toBeVisible();
}

test.describe("Pentest findings (administrator)", () => {
  test("writes a finding that is rated from its CVSS vector, and changes its status", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("findings");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    await expect(page.getByText("No findings yet")).toBeVisible();

    await write(page, "No lockout on the login");
    await page.getByRole("link", { name: "No lockout on the login" }).click();
    await expect(
      page.getByRole("heading", { name: /F-1 No lockout on the login/, level: 1 }),
    ).toBeVisible();
    await expect(page.getByText("High", { exact: true }).first()).toBeVisible();

    await pickOption(page, page, "Move to", /^Confirmed$/);
    await page.getByRole("button", { name: "Move", exact: true }).click();
    await expect(page.getByText("Status changed.")).toBeVisible();
    await expect(page.getByText("Status changed from New to Confirmed.")).toBeVisible();

    await page.getByLabel("Write a comment").fill("Reproduced twice.");
    await page.getByRole("button", { name: "Comment", exact: true }).click();
    await expect(page.getByText("Comment added.")).toBeVisible();
    await expect(page.getByText("Reproduced twice.")).toBeVisible();
  });

  test("adds evidence, seals a secret, and reveals it on request", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("evidence");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    await write(page, "Token in the URL");
    await page.getByRole("link", { name: "Token in the URL" }).click();

    await page.getByRole("button", { name: "Add evidence" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Title").fill("The request");
    await dialog
      .getByLabel("Note")
      .fill("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789");
    await dialog.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText("Evidence added.")).toBeVisible();

    const card = page.getByLabel("The request");
    await expect(card.getByText("Sealed")).toBeVisible();
    await expect(card.getByText("abcdefghijklmnopqrstuvwxyz0123456789")).toHaveCount(0);
    await card.getByRole("button", { name: "Reveal" }).click();
    await expect(card.getByText("abcdefghijklmnopqrstuvwxyz0123456789")).toBeVisible();
  });

  test("merges one finding into another and deletes and restores one", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("merge");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    await write(page, "Weak lockout policy");
    await write(page, "No account lockout");

    await page.getByRole("link", { name: "No account lockout" }).click();
    await page.getByRole("button", { name: "Merge" }).click();
    const dialog = page.getByRole("dialog");
    await pickOption(dialog, page, "Keep this finding", /Weak lockout policy/);
    await dialog.getByRole("button", { name: "Merge" }).click();
    await expect(page.getByText("Merged into F-1.", { exact: true })).toBeVisible();
    await expect(page.getByText(/it was merged into another one/)).toBeVisible();

    await page.getByRole("link", { name: "All findings" }).click();
    await expect(page.getByText("Showing 1 of 1.")).toBeVisible();

    await page.getByRole("link", { name: "Weak lockout policy" }).click();
    await page.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Move to the trash" }).click();
    await expect(page.getByText("This finding is in the trash")).toBeVisible();
    await page.getByRole("button", { name: "Restore" }).click();
    await expect(page.getByText("Restored.")).toBeVisible();
  });

  test("the pentest page links to the findings", async ({ page, playwright, baseURL }) => {
    const name = uniqueName("link");
    const id = await makeThroughApi(playwright, baseURL, name);
    await page.goto(`/pentests/${id}`);
    await expect(page.getByText("No findings yet.")).toBeVisible();
    await page.getByRole("link", { name: "Open the findings" }).click();
    await expect(page.getByRole("heading", { name: `Findings: ${name}`, level: 1 })).toBeVisible();
  });

  for (const theme of themes) {
    for (const width of [390, 1280]) {
      test(`the list and the finding have nothing new for axe (${theme}, ${String(width)}px)`, async ({
        page,
        playwright,
        baseURL,
      }) => {
        const name = uniqueName("axe");
        const id = await makeThroughApi(playwright, baseURL, name);
        await useTheme(page, theme);
        await page.setViewportSize({ width, height: 800 });
        await open(page, id, name);
        await write(page, "Axe finding");
        const list = await axeResults(page);
        expect(list.violations.map((one) => one.id)).toEqual([]);
        await page.getByRole("link", { name: "Axe finding" }).click();
        await expect(
          page.getByRole("heading", { name: /F-1 Axe finding/, level: 1 }),
        ).toBeVisible();
        const detail = await axeResults(page);
        expect(detail.violations.map((one) => one.id)).toEqual([]);
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
        );
        expect(overflow).toBe(false);
      });
    }
  }
});

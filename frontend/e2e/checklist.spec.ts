import AxeBuilder from "@axe-core/playwright";
import { type Page } from "@playwright/test";
import { THEME_KEY, themes } from "./pages";
import { ADMIN_STATE, SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import { pickOption } from "./vuetify";
import { alertOn, newPerson, signInThroughThePage, uniqueName } from "./people";

const SCOPE = "https://shop.example.com";
const FIRST_TEST = /WSTG-INFO-01/;

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

/** How many tests the page says are finished (tests that do not apply count as finished). */
async function finishedCount(page: Page): Promise<number> {
  const words = await page
    .getByText(/\d+ of \d+ tests finished/)
    .first()
    .textContent();
  return Number(/(\d+) of/.exec(words ?? "")?.[1]);
}

async function open(page: Page, id: string, name: string) {
  await page.goto(`/pentests/${id}/checklist`);
  await expect(page.getByRole("heading", { name: `Checklist: ${name}`, level: 1 })).toBeVisible();
}

test.describe("Pentest checklist (administrator)", () => {
  test("shows the whole methodology, records a result and remembers it", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("check");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    const before = await finishedCount(page);
    await expect(page.getByText("Information Gathering").first()).toBeVisible();

    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await page.getByRole("listitem", { name: FIRST_TEST }).click();
    const dialog = page.getByRole("dialog");
    await pickOption(dialog, page, "Where it stands", /^Passed/);
    await dialog.getByLabel("Notes").fill("Nothing sensitive is indexed.");
    await dialog.getByRole("button", { name: "Add a link" }).click();
    await dialog.getByLabel("Link 1 label").fill("Search results");
    await dialog.getByLabel("Link 1 address").fill("https://evidence.example.com/search");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Saved.")).toBeVisible();

    await page.reload();
    await expect(page.getByText(`${String(before + 1)} of`).first()).toBeVisible();
    await page.getByRole("button", { name: "Passed: 1" }).click();
    await expect(page.getByText(/Showing 1 of \d+ tests\./)).toBeVisible();
    await page.getByRole("listitem", { name: FIRST_TEST }).click();
    await expect(page.getByRole("dialog").getByLabel("Notes")).toHaveValue(
      "Nothing sensitive is indexed.",
    );
    await page.getByRole("dialog").getByRole("button", { name: "Put back as untouched" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Put back" }).last().click();
    await expect(page.getByText("Put back as untouched.")).toBeVisible();
    await expect(page.getByText(`${String(before)} of`).first()).toBeVisible();
  });

  test("finds a test by search and refuses a bad evidence link", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("search");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    await page.getByRole("textbox", { name: "Search tests, ids and notes" }).fill("WSTG-INFO-01");
    await expect(page.getByText(/Showing 1 of \d+ tests\./)).toBeVisible();
    await page.getByRole("textbox", { name: "Search tests, ids and notes" }).fill("zzzz-none");
    await expect(page.getByText("No test matches that.")).toBeVisible();
    await page.getByRole("textbox", { name: "Search tests, ids and notes" }).fill("WSTG-INFO-01");

    await page.getByRole("listitem", { name: FIRST_TEST }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Add a link" }).click();
    await dialog.getByLabel("Link 1 label").fill("Bad");
    await dialog.getByLabel("Link 1 address").fill("ftp://evidence.example.com/x");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(alertOn(page)).toBeVisible();
    await expect(dialog).toBeVisible();
  });

  test("adds a test of your own and removes it again", async ({ page, playwright, baseURL }) => {
    const name = uniqueName("own");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    await page.getByRole("button", { name: "Add a test" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name", { exact: true }).fill("Check the CDN cache");
    await dialog.getByRole("button", { name: "Add test" }).click();
    await expect(page.getByText("Test added.")).toBeVisible();
    await page.getByRole("button", { name: /Custom/ }).click();
    await page.getByRole("listitem", { name: /Check the CDN cache/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Remove this test" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Remove" }).last().click();
    await expect(page.getByText("Test removed.")).toBeVisible();
    await expect(page.getByText("Check the CDN cache")).toHaveCount(0);
  });

  test("a feature the target shows turns its tests on", async ({ page, playwright, baseURL }) => {
    const name = uniqueName("features");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    await page.getByLabel("Only tests that apply").check({ force: true });
    const before = await page.getByText(/Showing \d+ of \d+ tests\./).textContent();
    await page.getByRole("combobox", { name: "Features" }).fill("saml");
    await page.getByRole("combobox", { name: "Features" }).press("Enter");
    await page.getByRole("button", { name: "Save features" }).click();
    await expect(page.getByText("Features saved.")).toBeVisible();
    await expect(page.getByText(/Showing \d+ of \d+ tests\./)).not.toHaveText(before ?? "");
  });

  test("the pentest page shows the progress and links to the checklist", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("link");
    const id = await makeThroughApi(playwright, baseURL, name);
    await page.goto(`/pentests/${id}`);
    await expect(page.getByText(/\d+ of \d+ tests finished/)).toBeVisible();
    await page.getByRole("link", { name: "Open the checklist" }).click();
    await expect(page.getByRole("heading", { name: `Checklist: ${name}`, level: 1 })).toBeVisible();
    await page.getByRole("link", { name: "Back to the pentest" }).click();
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
  });

  for (const theme of themes) {
    test(`the checklist has no accessibility problems (${theme} theme)`, async ({
      page,
      playwright,
      baseURL,
    }) => {
      await page.addInitScript(
        ([key, value]) => {
          localStorage.setItem(key as string, value as string);
        },
        [THEME_KEY, theme],
      );
      await page.emulateMedia({ reducedMotion: "reduce" });
      const name = uniqueName("axe");
      const id = await makeThroughApi(playwright, baseURL, name);
      await open(page, id, name);
      await page.getByRole("button", { name: /Information Gathering/ }).click();
      await page.evaluate(() => document.fonts.ready);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
        .analyze();
      expect(
        results.violations.map((one) => ({
          rule: one.id,
          targets: one.nodes.map((node) => node.target.join(" ")),
        })),
      ).toEqual([]);
    });
  }
});

test.describe("Pentest checklist (viewer)", () => {
  test.use({ storageState: SIGNED_OUT });

  test("a viewer can read the checklist but change nothing", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("seen");
    const id = await makeThroughApi(playwright, baseURL, name);
    const person = await newPerson(playwright, baseURL, "viewer");
    await signInThroughThePage(page, person);
    await open(page, id, name);
    await expect(page.getByRole("button", { name: "Add a test" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Save features" })).toHaveCount(0);
    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await page.getByRole("listitem", { name: FIRST_TEST }).click();
    await expect(page.getByRole("dialog").getByRole("button", { name: "Save" })).toHaveCount(0);
  });
});

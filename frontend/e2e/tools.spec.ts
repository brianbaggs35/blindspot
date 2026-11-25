import { type Page, type PlaywrightWorkerArgs } from "@playwright/test";
import { ADMIN_STATE, SIGNED_OUT } from "./accounts";
import { axeResults, useTheme } from "./axe";
import { expect, test } from "./fixtures";
import { alertOn, newPerson, signInThroughThePage, uniqueName } from "./people";
import { themes } from "./pages";
import { pickOption } from "./vuetify";

type Playwright = PlaywrightWorkerArgs["playwright"];

/** A custom tool whose program is the system's own echo, made through the API. */
async function newTool(playwright: Playwright, baseURL: string | undefined) {
  const origin = new URL(baseURL ?? "").origin;
  const admin = await playwright.request.newContext({
    baseURL: origin,
    storageState: ADMIN_STATE,
    ignoreHTTPSErrors: true,
  });
  const suffix = uniqueName("e").replaceAll("-", "").slice(0, 12);
  const id = `x.echo${suffix}`;
  const name = `Echo ${suffix}`;
  const made = await admin.post("/api/tools/custom", {
    headers: { Origin: origin },
    data: {
      id,
      name,
      binary: "/bin/echo",
      risk: "passive",
      version: { args: ["Echo version 4.5.6"], pattern: "version ([0-9.]+)" },
      params: { url: { type: "target", required: true } },
      argv: ["{url}"],
      explain: "Prints what it is given.",
      could_go_wrong: "Nothing: it only prints.",
    },
  });
  expect(made.status()).toBe(201);
  return {
    name,
    async remove() {
      await admin.delete(`/api/tools/custom/${id}`, { headers: { Origin: origin } });
      await admin.dispose();
    },
  };
}

function card(page: Page, name: string) {
  return page.getByLabel(name, { exact: true });
}

test.describe("Tools (administrator)", () => {
  test("shows each tool, and changes the default and where a tool runs", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const tool = await newTool(playwright, baseURL);
    try {
      await page.goto("/tools");
      await expect(page.getByRole("heading", { name: "Tools", level: 1 })).toBeVisible();
      await expect(page.getByRole("combobox", { name: "Where tools run" })).toBeVisible();

      await pickOption(page, page, "Where tools run", /^Prefer Local/);
      await expect(page.getByText("The default was saved.")).toBeVisible();
      await expect(page.getByText("Local, and Docker when Local cannot run.")).toBeVisible();
      await pickOption(page, page, "Where tools run", /^Auto/);
      await expect(page.getByText("The default was saved.")).toBeVisible();

      const mine = card(page, tool.name);
      await expect(mine).toContainText("Prints what it is given.");
      await expect(mine).toContainText("Local");
      // Asked to run in Docker with no Docker there, a tool is stopped, not moved to Local.
      await mine.getByRole("button", { name: "Settings" }).click();
      const dialog = page.getByRole("dialog");
      await pickOption(dialog, page, "Where it runs", /^Docker$/);
      await dialog
        .getByLabel("Image with its digest (Docker)")
        .fill(`ghcr.io/example/echo@sha256:${"a".repeat(64)}`);
      await dialog.getByRole("button", { name: "Save" }).click();
      await expect(page.getByText(`Saved the settings of ${tool.name}.`)).toBeVisible();
      await expect(mine).toContainText("Docker not reachable");
      await expect(mine.getByRole("button", { name: "Test" })).toHaveCount(0);

      await mine.getByRole("button", { name: "Settings" }).click();
      await pickOption(dialog, page, "Where it runs", /^Local$/);
      await dialog.getByLabel("Program path (Local)").fill("/bin/echo");
      await dialog.getByRole("button", { name: "Save" }).click();
      await expect(page.getByText(`Saved the settings of ${tool.name}.`)).toBeVisible();
      await expect(mine).toContainText("/bin/echo");

      await mine.getByRole("button", { name: "Test" }).click();
      const result = page.getByRole("dialog");
      await expect(result).toContainText("exit code 0");
      await expect(result).toContainText("4.5.6");
      await result.getByRole("button", { name: "Close" }).click();

      await mine.getByRole("button", { name: "Reset" }).click();
      await expect(page.getByText(`${tool.name} is back to its defaults.`)).toBeVisible();
      await expect(mine.getByRole("button", { name: "Reset" })).toHaveCount(0);
    } finally {
      await tool.remove();
    }
  });

  test("refuses a setting the server does not accept", async ({ page, playwright, baseURL }) => {
    const tool = await newTool(playwright, baseURL);
    try {
      await page.goto("/tools");
      await card(page, tool.name).getByRole("button", { name: "Settings" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("Timeout (seconds)").fill("0");
      await dialog.getByRole("button", { name: "Save" }).click();
      await expect(alertOn(page)).toBeVisible();
    } finally {
      await tool.remove();
    }
  });

  for (const theme of themes) {
    test(`has no accessibility violations with its dialogs open (${theme})`, async ({
      page,
      playwright,
      baseURL,
    }) => {
      const tool = await newTool(playwright, baseURL);
      try {
        await useTheme(page, theme);
        await page.goto("/tools");
        await expect(page.getByRole("heading", { name: "Tools", level: 1 })).toBeVisible();
        const mine = card(page, tool.name);
        await expect(mine).toBeVisible();
        expect((await axeResults(page)).violations).toEqual([]);
        await mine.getByRole("button", { name: "Settings" }).click();
        await expect(page.getByRole("dialog")).toBeVisible();
        expect((await axeResults(page)).violations).toEqual([]);
      } finally {
        await tool.remove();
      }
    });
  }
});

test.describe("Tools (viewer)", () => {
  test.use({ storageState: SIGNED_OUT });

  test("a viewer can see how tools run but change nothing", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL, "viewer");
    await signInThroughThePage(page, person);
    await page.goto("/tools");
    await expect(page.getByRole("heading", { name: "Tools", level: 1 })).toBeVisible();
    await expect(page.getByText("Only an administrator can change these settings.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Settings" })).toHaveCount(0);
  });
});

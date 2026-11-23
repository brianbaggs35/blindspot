import { SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import { newPerson, signInThroughThePage, alertOn } from "./people";

const WSTG = "OWASP Web Security Testing Guide";

// The methodologies belong to the whole installation, so the specs that change one run one after
// the other, and each puts back what it changed.
test.describe("Methodologies (administrator)", () => {
  test.describe.configure({ mode: "serial" });

  test("lists the checklist by category and narrows it by search and risk", async ({ page }) => {
    await page.goto("/methodologies");
    await expect(page.getByRole("heading", { name: "Methodologies", level: 1 })).toBeVisible();
    await expect(page.getByText(WSTG, { exact: true }).first()).toBeVisible();
    await expect(page.getByText("133 tests", { exact: true })).toBeVisible();
    await expect(page.getByText("Showing 133 of 133 tests.")).toBeVisible();

    await page.getByRole("textbox", { name: "Search tests, ids and tools" }).fill("WSTG-INFO-02");
    await expect(page.getByText("Showing 1 of 133 tests.")).toBeVisible();
    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await expect(page.getByRole("listitem", { name: /WSTG-INFO-02/ })).toBeVisible();

    await page
      .getByRole("textbox", { name: "Search tests, ids and tools" })
      .fill("no test is called this");
    await expect(page.getByText("No test matches that search.")).toBeVisible();

    await page.getByRole("textbox", { name: "Search tests, ids and tools" }).fill("");
    await page
      .getByRole("group", { name: "Risk class" })
      .getByRole("button", { name: "Intrusive" })
      .click();
    await expect(page.getByText(/^Showing \d+ of 133 tests\.$/)).not.toHaveText(
      "Showing 133 of 133 tests.",
    );
  });

  test("shows exactly what a test's agent is told to do", async ({ page }) => {
    await page.goto("/methodologies");
    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await page.getByRole("listitem", { name: /WSTG-INFO-02/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("WSTG-INFO-02 · Fingerprint Web Server");
    await expect(dialog).toContainText("What the agent is told");
    await expect(dialog).toContainText("Evidence it must bring back");
    await expect(dialog).toContainText("A finding when");
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toBeHidden();
  });

  test("changes a playbook, then puts the original back", async ({ page }) => {
    const summary = "Check page content, the way this installation wants it done";
    await page.goto("/methodologies");
    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await page.getByRole("listitem", { name: /WSTG-INFO-05/ }).click();
    const first = page.getByRole("dialog").first();
    await expect(first).toContainText("WSTG-INFO-05");
    await first.getByRole("button", { name: "Edit the playbook" }).click();
    const editor = page.getByRole("dialog").last();
    await expect(editor).toContainText("Edit the playbook");
    await editor.getByLabel("Summary").fill(summary);
    await editor.getByRole("button", { name: "Save playbook" }).click();
    await expect(first).toContainText(summary);
    await expect(first).toContainText("Changed here");

    await first.getByRole("button", { name: "Put the original back" }).click();
    await expect(first).not.toContainText(summary);
    await expect(first.getByRole("button", { name: "Put the original back" })).toHaveCount(0);
  });

  test("refuses a playbook that is not valid and keeps what was typed", async ({ page }) => {
    await page.goto("/methodologies");
    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await page.getByRole("listitem", { name: /WSTG-INFO-06/ }).click();
    await page
      .getByRole("dialog")
      .first()
      .getByRole("button", { name: "Edit the playbook" })
      .click();
    const editor = page.getByRole("dialog").last();
    await editor.getByLabel("Evidence to bring back").fill("");
    await editor.getByRole("button", { name: "Save playbook" }).click();
    await expect(alertOn(page)).toBeVisible();
    await expect(editor.getByLabel("Summary")).not.toHaveValue("");
    await editor.getByRole("button", { name: "Cancel" }).click();
  });

  test("checks for an update and finds the copy that ships is already in use", async ({ page }) => {
    await page.goto("/methodologies");
    await page.getByRole("button", { name: "Check for updates" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(`Update ${WSTG}`);
    await dialog.getByRole("button", { name: "Check for an update" }).click();
    await expect(dialog).toContainText("Nothing to update: this is already the latest.");
    await expect(dialog.getByRole("button", { name: "Apply this update" })).toHaveCount(0);
    await dialog.getByRole("button", { name: "Close" }).click();
  });

  test("reads the packs folder", async ({ page }) => {
    await page.goto("/methodologies");
    await page.getByRole("button", { name: "Read packs folder" }).click();
    await expect(page.getByText(/No new packs\./)).toBeVisible();
  });

  test("turns the methodology off and on again", async ({ page }) => {
    await page.goto("/methodologies");
    const toggle = page.getByLabel("Offer this methodology for new pentests");
    await expect(toggle).toBeChecked();
    await page.getByText("Offer this methodology for new pentests").click();
    await expect(page.getByText(`${WSTG} is off.`)).toBeVisible();
    await expect(toggle).not.toBeChecked();
    await page.getByText("Offer this methodology for new pentests").click();
    await expect(page.getByText(`${WSTG} is on.`)).toBeVisible();
    await expect(toggle).toBeChecked();
  });

  test("is in the menu", async ({ page }) => {
    await page.goto("/");
    const menu = page.getByRole("navigation", { name: "Main" });
    await menu.getByRole("link", { name: "Methodologies" }).click();
    await expect(page.getByRole("heading", { name: "Methodologies", level: 1 })).toBeVisible();
  });
});

test.describe("Methodologies (viewer)", () => {
  test.use({ storageState: SIGNED_OUT });

  test("a viewer can read every playbook but change nothing", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const person = await newPerson(playwright, baseURL, "viewer");
    await signInThroughThePage(page, person);
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Methodologies" })
      .click();
    await expect(page.getByRole("heading", { name: "Methodologies", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Read packs folder" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Check for updates" })).toHaveCount(0);
    await expect(page.getByLabel("Offer this methodology for new pentests")).toHaveCount(0);
    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await page.getByRole("listitem", { name: /WSTG-INFO-02/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("What the agent is told");
    await expect(dialog.getByRole("button", { name: "Edit the playbook" })).toHaveCount(0);
  });
});

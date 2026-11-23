import { SIGNED_OUT } from "./accounts";
import { expect, test } from "./fixtures";
import { newPerson, signInThroughThePage, uniqueName, alertOn } from "./people";
import { card, newProvider } from "./providers";
import { pickOption } from "./vuetify";

test.describe("AI providers (administrator)", () => {
  test("adds a provider, shows a failed test, and deletes it after asking", async ({ page }) => {
    const name = uniqueName("local");
    await page.goto("/ai-providers");
    await expect(page.getByRole("heading", { name: "AI providers", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "Add a provider" }).click();
    const dialog = page.getByRole("dialog");
    await pickOption(dialog, page, "Kind", /Ollama \(local\)/);
    await expect(dialog).toContainText("OLLAMA_HOST=0.0.0.0");
    await dialog.getByLabel("Name", { exact: true }).fill(name);
    await dialog.getByLabel("Address").fill("http://localhost:9");
    await dialog.getByRole("button", { name: "Add provider" }).click();
    await expect(page.getByText(`Added ${name}. Fetch its models next.`)).toBeVisible();
    const mine = card(page, name);
    await expect(mine).toContainText("No key needed");
    await expect(mine).toContainText("0 models");

    await mine.getByRole("button", { name: "Test" }).click();
    await expect(mine.locator(".v-alert")).toContainText("could not be reached");

    await mine.getByRole("button", { name: `Delete ${name}` }).click();
    await expect(page.getByRole("dialog")).toContainText(`Delete ${name}?`);
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
    await expect(mine).toBeVisible();
    await mine.getByRole("button", { name: `Delete ${name}` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText(`Deleted ${name}.`)).toBeVisible();
    await expect(page.getByText(name, { exact: true })).toHaveCount(0);
  });

  test("refuses an address the guard does not allow", async ({ page }) => {
    await page.goto("/ai-providers");
    await page.getByRole("button", { name: "Add a provider" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name", { exact: true }).fill(uniqueName("bad"));
    await dialog.getByLabel("API key").fill("sk-not-a-real-key-0123456789");
    await dialog.getByLabel("Address").fill("https://169.254.169.254");
    await dialog.getByRole("button", { name: "Add provider" }).click();
    await expect(alertOn(page)).toContainText("not allowed");
  });

  test("edits a provider's name and budget", async ({ page, playwright, baseURL }) => {
    const made = await newProvider(playwright, baseURL);
    await page.goto("/ai-providers");
    await card(page, made.name)
      .getByRole("button", { name: `Edit ${made.name}` })
      .click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("No key is saved.");
    await dialog.getByLabel("Monthly budget (USD)").fill("25");
    await dialog.getByText("Stop calls when the budget is used up").click();
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText(`Saved ${made.name}.`)).toBeVisible();
    await expect(card(page, made.name)).toContainText(
      "$0.00 of $25.00 this month, calls stop at the budget",
    );
  });

  test("adds a model by hand, makes it the default for a job, and clears it with the provider", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const made = await newProvider(playwright, baseURL);
    await page.goto("/ai-providers");
    await card(page, made.name).getByRole("button", { name: "Models" }).click();
    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toContainText("No models yet");
    await dialog.getByRole("button", { name: "Add by hand" }).click();
    const form = page.getByRole("dialog").last();
    await form.getByLabel("Model id").fill("llama3.3:70b");
    await form.getByLabel("Name", { exact: true }).fill("Llama 3.3 70B");
    await form.getByLabel("Context size (tokens)").fill("131072");
    await pickOption(form, page, "Capabilities", /Tools/);
    await page.keyboard.press("Escape");
    await form.getByRole("button", { name: "Add model" }).click();
    const row = dialog.locator(".v-list-item", { hasText: "Llama 3.3 70B" });
    await expect(row).toContainText("llama3.3:70b · 131,072 tokens");
    await expect(row).toContainText("free");
    await expect(row).not.toContainText("no tools");
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(card(page, made.name)).toContainText("1 model");

    await pickOption(page, page, "Chat: answers your questions", `${made.name} · Llama 3.3 70B`);
    await expect(page.getByText("Saved the default for chat.")).toBeVisible();
    await page.reload();
    await expect(page.getByText(`${made.name} · Llama 3.3 70B`)).toBeVisible();

    // Deleting the provider takes the default with it.
    await card(page, made.name)
      .getByRole("button", { name: `Delete ${made.name}` })
      .click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText(`Deleted ${made.name}.`)).toBeVisible();
    await expect(page.getByText(`${made.name} · Llama 3.3 70B`)).toHaveCount(0);
  });

  test("is in the menu", async ({ page }) => {
    await page.goto("/");
    const menu = page.getByRole("navigation", { name: "Main" });
    await expect(menu.getByRole("link", { name: "AI providers" })).toBeVisible();
  });
});

test.describe("AI providers (viewer)", () => {
  test.use({ storageState: SIGNED_OUT });

  test("a viewer can look but not change anything", async ({ page, playwright, baseURL }) => {
    const made = await newProvider(playwright, baseURL);
    const person = await newPerson(playwright, baseURL, "viewer");
    await signInThroughThePage(page, person);
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "AI providers" })
      .click();
    await expect(page.getByRole("heading", { name: "AI providers", level: 1 })).toBeVisible();
    const mine = card(page, made.name);
    await expect(mine).toBeVisible();
    await expect(page.getByRole("button", { name: "Add a provider" })).toHaveCount(0);
    await expect(mine.getByRole("button", { name: "Test" })).toHaveCount(0);
    await expect(mine.getByRole("button", { name: `Delete ${made.name}` })).toHaveCount(0);
    await mine.getByRole("button", { name: "Models" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("An administrator has not added any.");
    await expect(dialog.getByRole("button", { name: "Fetch models" })).toHaveCount(0);
  });
});

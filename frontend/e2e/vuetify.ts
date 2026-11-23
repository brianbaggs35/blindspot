import type { Locator, Page } from "@playwright/test";

/**
 * Vuetify's select hides its input behind the field, so the field is what gets clicked. Pass a
 * string for a searchable list (an autocomplete) and a pattern for a plain select.
 */
export async function pickOption(
  scope: Page | Locator,
  page: Page,
  label: string,
  option: string | RegExp,
) {
  await scope.locator(".v-field", { has: page.getByLabel(label, { exact: true }) }).click();
  // A text option means a searchable list: typing replaces what was there and brings it into view.
  if (typeof option === "string")
    await page.getByRole("combobox", { name: label, exact: true }).fill(option);
  await page.getByRole("option", { name: option }).click();
}

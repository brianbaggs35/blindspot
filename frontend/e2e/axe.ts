import AxeBuilder from "@axe-core/playwright";
import { type Page } from "@playwright/test";
import { THEME_KEY, type Theme } from "./pages";

/** Open the next page in this theme, with no animation so colours are measured in their final state. */
export async function useTheme(page: Page, theme: Theme): Promise<void> {
  await page.addInitScript(
    ([key, value]) => {
      localStorage.setItem(key as string, value as string);
    },
    [THEME_KEY, theme],
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
}

/** What axe finds on the page as it is now, once the fonts are in. */
export async function axeResults(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  return await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .analyze();
}

/** The rules the page breaks and where, for a test to expect to be empty. */
export async function violationsOf(page: Page) {
  const results = await axeResults(page);
  return results.violations.map((one) => ({
    rule: one.id,
    targets: one.nodes.map((node) => node.target.join(" ")),
  }));
}

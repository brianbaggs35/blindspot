import AxeBuilder from "@axe-core/playwright";
import baseline from "./axe-baseline.json" with { type: "json" };
import { expect, test } from "./fixtures";
import { pages, themes, THEME_KEY, widths } from "./pages";

interface KnownProblem {
  rule: string;
  page: string;
  theme: string;
  reason: string;
}

// Typed here because an empty list in the JSON file has no type of its own.
const known: readonly KnownProblem[] = baseline.known;

test.describe("accessibility (axe, WCAG 2.2 AA and best practice)", () => {
  test("every known problem says why it is accepted", () => {
    for (const problem of known) expect(problem.reason.trim().length).toBeGreaterThan(10);
  });

  for (const { name, path } of pages) {
    for (const theme of themes) {
      for (const width of widths) {
        test(`${name}, ${theme} theme, ${String(width)}px: nothing new`, async ({ page }) => {
          await page.addInitScript(
            ([key, value]) => {
              localStorage.setItem(key as string, value as string);
            },
            [THEME_KEY, theme],
          );
          // No animation, so colours are measured in their final state, not mid-transition.
          await page.emulateMedia({ reducedMotion: "reduce" });
          await page.setViewportSize({ width, height: 800 });
          await page.goto(path);
          await expect(page.locator(".v-application")).toBeVisible();
          await page.evaluate(() => document.fonts.ready);

          const results = await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
            .analyze();

          const isKnown = (rule: string) =>
            known.some((k) => k.rule === rule && k.page === name && k.theme === theme);
          const fresh = results.violations
            .filter((violation) => !isKnown(violation.id))
            .map((violation) => ({
              rule: violation.id,
              impact: violation.impact,
              help: violation.help,
              targets: violation.nodes.map((node) => node.target.join(" ")),
            }));
          expect(fresh).toEqual([]);
        });
      }
    }
  }
});

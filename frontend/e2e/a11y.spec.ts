import baseline from "./axe-baseline.json" with { type: "json" };
import { expect, test } from "./fixtures";
import { openPage, stateFor } from "./open-page";
import { pages, themes, widths } from "./pages";
import { axeResults, useTheme } from "./axe";

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

  for (const entry of pages) {
    const { name } = entry;
    test.describe(name, () => {
      test.use({ storageState: stateFor(entry) });
      for (const theme of themes) {
        for (const width of widths) {
          test(`${theme} theme, ${String(width)}px: nothing new`, async ({ page }) => {
            await useTheme(page, theme);
            await page.setViewportSize({ width, height: 800 });
            await openPage(page, entry);
            await expect(page.locator(".v-application")).toBeVisible();
            const results = await axeResults(page);

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
    });
  }
});

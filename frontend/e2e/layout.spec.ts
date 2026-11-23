import { expect, test } from "./fixtures";
import { openPage, stateFor } from "./open-page";
import { pages, widths } from "./pages";

test.describe("layout", () => {
  for (const entry of pages) {
    test.describe(entry.name, () => {
      test.use({ storageState: stateFor(entry) });

      for (const width of widths) {
        test(`has no horizontal scroll at ${String(width)}px`, async ({ page }) => {
          await page.setViewportSize({ width, height: 800 });
          await openPage(page, entry);
          await expect(page.locator(".v-application")).toBeVisible();
          const overflow = await page.evaluate(() => {
            const root = document.documentElement;
            return { scroll: root.scrollWidth, client: root.clientWidth };
          });
          expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
        });
      }

      test("stops animating when the system asks for reduced motion", async ({ page }) => {
        await page.emulateMedia({ reducedMotion: "reduce" });
        await openPage(page, entry);
        const button = page.getByRole("button").first();
        await expect(button).toBeVisible();
        const seconds = await button.evaluate((element) => {
          const style = getComputedStyle(element);
          return [style.transitionDuration, style.animationDuration].flatMap((value) =>
            value.split(",").map((part) => Number.parseFloat(part)),
          );
        });
        for (const duration of seconds) expect(duration).toBeLessThanOrEqual(0.001);
      });
    });
  }
});

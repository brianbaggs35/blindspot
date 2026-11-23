import { test as base } from "@playwright/test";
import { collectCoverage, newCoverageReport } from "./coverage";

export { expect } from "@playwright/test";

// Every test gets browser coverage collected for it when E2E_COVERAGE=1; otherwise this does nothing.
export const test = base.extend<{ coverage: undefined }>({
  coverage: [
    async ({ page }, use) => {
      if (!collectCoverage) {
        await use(undefined);
        return;
      }
      await page.coverage.startJSCoverage({ resetOnNavigation: false });
      await use(undefined);
      const entries = await page.coverage.stopJSCoverage();
      // A test that never opened a page (an API check) has nothing to add.
      if (entries.length > 0) await newCoverageReport().add(entries);
    },
    { auto: true },
  ],
});

import type { Page } from "@playwright/test";
import { SIGNED_OUT, ADMIN_STATE } from "./accounts";
import type { PageEntry } from "./pages";

/** The storage state a page's specs should start from. */
export function stateFor(entry: PageEntry) {
  return entry.signedIn === false ? SIGNED_OUT : ADMIN_STATE;
}

/** Fake the API's answer that setup is open, for the one page that only exists then. */
export async function openSetup(page: Page, path = "/setup"): Promise<void> {
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { setup_required: true, user: null } }),
  );
  await page.goto(path);
}

export async function openPage(page: Page, entry: PageEntry): Promise<void> {
  if (entry.mockSetup === true) await openSetup(page, entry.path);
  else await page.goto(entry.path);
}

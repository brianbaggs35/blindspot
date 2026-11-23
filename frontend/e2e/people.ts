import {
  expect,
  type APIRequestContext,
  type Page,
  type PlaywrightWorkerArgs,
} from "@playwright/test";
import { ADMIN_STATE } from "./accounts";

export const PASSWORD = "violet harbour lantern 2026";

export interface Person {
  username: string;
  password: string;
}

/** A name nobody else in the run will use, so specs never depend on each other's accounts. */
export function uniqueName(prefix: string): string {
  const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  return `${prefix}-${stamp}`;
}

/** Make an account through the API as the administrator, whatever the page under test is signed in as. */
export async function newPerson(
  playwright: PlaywrightWorkerArgs["playwright"],
  baseURL: string | undefined,
  role: "admin" | "viewer" = "viewer",
): Promise<Person> {
  const origin = new URL(baseURL ?? "").origin;
  const request = await playwright.request.newContext({
    baseURL: origin,
    storageState: ADMIN_STATE,
    ignoreHTTPSErrors: true,
  });
  const person = await createPerson(request, origin, role);
  await request.dispose();
  return person;
}

export async function createPerson(
  request: APIRequestContext,
  origin: string,
  role: "admin" | "viewer" = "viewer",
): Promise<Person> {
  const person = { username: uniqueName(role), password: PASSWORD };
  const answer = await request.post("/api/users", {
    headers: { Origin: origin },
    data: { username: person.username, display_name: `A ${role}`, role, password: person.password },
  });
  expect(answer.status()).toBe(201);
  return person;
}

/** Sign in through the page, as a person would. */
export async function signInThroughThePage(page: Page, person: Person): Promise<void> {
  await page.goto("/sign-in");
  await page.getByLabel("Username").fill(person.username);
  await page.getByLabel("Password", { exact: true }).fill(person.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
}

export async function signOutThroughThePage(page: Page): Promise<void> {
  await page.getByRole("button", { name: /^Account menu for/ }).click();
  await page.locator(".v-menu .v-list-item", { hasText: "Sign out" }).click();
  await expect(page).toHaveURL(/\/sign-in/);
}

/** The error message a form shows (Vuetify's per-field messages also say "alert", so not by role alone). */
export function alertOn(page: Page) {
  return page.locator(".v-alert[role=alert]");
}

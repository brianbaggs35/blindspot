import { randomBytes } from "node:crypto";
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
  return `${prefix}-${Date.now().toString(36)}${randomBytes(3).toString("hex")}`;
}

/** Make an account through the API as the administrator, whatever the page under test is signed in as. */
export async function newPerson(
  playwright: PlaywrightWorkerArgs["playwright"],
  baseURL: string | undefined,
  role: "admin" | "viewer" = "viewer",
  { acceptTerms = true }: { acceptTerms?: boolean } = {},
): Promise<Person> {
  const origin = new URL(baseURL ?? "").origin;
  const request = await playwright.request.newContext({
    baseURL: origin,
    storageState: ADMIN_STATE,
    ignoreHTTPSErrors: true,
  });
  const person = await createPerson(request, origin, role);
  await request.dispose();
  if (acceptTerms) await acceptTermsAs(playwright, origin, person);
  return person;
}

/** Sign the person in through the API and accept the terms of use, so the page opens at once. */
async function acceptTermsAs(
  playwright: PlaywrightWorkerArgs["playwright"],
  origin: string,
  person: Person,
): Promise<void> {
  const own = await playwright.request.newContext({
    baseURL: origin,
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { Origin: origin },
  });
  // The API is shared with every other spec, so a busy moment gets a few tries before it is a failure.
  let status = 0;
  for (let attempt = 0; attempt < 4 && status !== 200; attempt++) {
    if (attempt > 0) await new Promise((done) => setTimeout(done, 500 * attempt));
    status = (
      await own.post("/api/auth/login", {
        data: { username: person.username, password: person.password },
      })
    ).status();
  }
  expect(status, "signing in through the API to accept the terms").toBe(200);
  const terms = (await (await own.get("/api/terms")).json()) as { version: string };
  const accepted = await own.post("/api/terms/accept", { data: { version: terms.version } });
  expect(accepted.ok()).toBe(true);
  // End this session so the account starts with none, as a person who has never signed in would.
  await own.post("/api/auth/logout");
  await own.dispose();
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
export async function signInThroughThePage(
  page: Page,
  person: Person,
  { landsOn = "Overview" }: { landsOn?: string | undefined } = {},
): Promise<void> {
  await page.goto("/sign-in");
  await page.getByLabel("Username").fill(person.username);
  await page.getByLabel("Password", { exact: true }).fill(person.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: landsOn, level: 1 })).toBeVisible();
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

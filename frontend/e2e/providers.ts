import { expect, type Page, type PlaywrightWorkerArgs } from "@playwright/test";
import { ADMIN_STATE } from "./accounts";
import { uniqueName } from "./people";

export interface Made {
  id: string;
  name: string;
}

/** Make a local Ollama provider through the API as the administrator, whatever the page is signed in as. */
export async function newProvider(
  playwright: PlaywrightWorkerArgs["playwright"],
  baseURL: string | undefined,
  address = "http://localhost:9",
): Promise<Made> {
  const origin = new URL(baseURL ?? "").origin;
  const request = await playwright.request.newContext({
    baseURL: origin,
    storageState: ADMIN_STATE,
    ignoreHTTPSErrors: true,
  });
  const name = uniqueName("provider");
  const answer = await request.post("/api/providers", {
    headers: { Origin: origin },
    data: { kind: "ollama-local", name, base_url: address },
  });
  expect(answer.status()).toBe(201);
  const made = (await answer.json()) as { id: string };
  await request.dispose();
  return { id: made.id, name };
}

/** The card of one provider on the page. */
export function card(page: Page, name: string) {
  return page.locator(".v-card", { has: page.getByText(name, { exact: true }) }).last();
}

import { type Page } from "@playwright/test";
import { ADMIN_STATE } from "./accounts";
import { expect, test } from "./fixtures";
import { uniqueName } from "./people";

const SCOPE = "https://shop.example.com";

// A small, real shape of `nmap -oX`: one host, one open port and one closed.
const NMAP = `<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sT -oX - 127.0.0.1" version="7.94">
<host><status state="up"/><address addr="127.0.0.1" addrtype="ipv4"/>
<ports>
<port protocol="tcp" portid="22"><state state="closed"/><service name="ssh"/></port>
<port protocol="tcp" portid="8081"><state state="open"/><service name="http" product="Apache httpd" version="2.4.41"/></port>
</ports></host>
<runstats><finished elapsed="1.2" exit="success"/></runstats>
</nmaprun>`;

type Playwright = Parameters<Parameters<typeof test>[2]>[0]["playwright"];

/** Makes a pentest straight through the API and returns its id. */
async function makeThroughApi(playwright: Playwright, baseURL: string | undefined, name: string) {
  const origin = new URL(baseURL ?? "").origin;
  const admin = await playwright.request.newContext({
    baseURL: origin,
    storageState: ADMIN_STATE,
    ignoreHTTPSErrors: true,
  });
  const made = await admin.post("/api/pentests", {
    headers: { Origin: origin },
    data: { name, methodology_id: "wstg", scope: { in_scope: [SCOPE] } },
  });
  expect(made.status()).toBe(201);
  const { id } = (await made.json()) as { id: string };
  await admin.dispose();
  return id;
}

async function open(page: Page, id: string, name: string) {
  await page.goto(`/pentests/${id}/results`);
  await expect(page.getByRole("heading", { name: `Results: ${name}`, level: 1 })).toBeVisible();
}

test.describe("Pentest results (administrator)", () => {
  test("writes a note, edits it, deletes it and puts it back", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("notes");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);
    await expect(page.getByText("No results yet")).toBeVisible();

    await page.getByRole("button", { name: "Write a note" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Title").fill("Login form on /admin");
    await dialog.getByLabel("What you saw or tried").fill("No lockout after ten tries.");
    await dialog.getByRole("button", { name: "Add result" }).click();
    await expect(page.getByText("Note added.")).toBeVisible();

    await page.getByRole("link", { name: "Login form on /admin" }).click();
    await expect(
      page.getByRole("heading", { name: "Login form on /admin", level: 1 }),
    ).toBeVisible();
    await expect(page.getByText("No lockout after ten tries.")).toBeVisible();
    await expect(page.getByText("This is a note, so there is no tool output")).toBeVisible();

    await page.getByRole("button", { name: "Notes and tags" }).click();
    await page.getByRole("dialog").getByLabel("Title").fill("Admin login has no lockout");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Saved.")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Admin login has no lockout", level: 1 }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText("This result is in the trash.")).toBeVisible();
    await page.getByRole("button", { name: "Restore" }).click();
    await expect(page.getByText("Restored.")).toBeVisible();
    await expect(page.getByText("This result is in the trash.")).toHaveCount(0);
  });

  test("imports nmap output and reads it the friendly, technical and raw way", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("import");
    const id = await makeThroughApi(playwright, baseURL, name);
    await open(page, id, name);

    await page.getByRole("button", { name: "Import output" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Output").fill(NMAP);
    await dialog.getByRole("button", { name: "Import" }).click();
    await expect(page.getByText("Output imported.")).toBeVisible();

    await page.getByRole("link", { name: /Imported nmap xml output/ }).click();
    await expect(page.getByRole("region", { name: "Friendly view" })).toBeVisible();
    await expect(page.getByText("8081/tcp")).toBeVisible();

    await page.getByRole("button", { name: "Technical" }).click();
    await expect(page.getByRole("region", { name: "Technical view" })).toBeVisible();
    await expect(page.getByRole("table", { name: "Hosts and services" })).toBeVisible();

    await page.getByRole("button", { name: "Raw" }).click();
    await expect(page.getByRole("region", { name: "Raw view" })).toBeVisible();
    await page.getByLabel("Search the output").fill("portid");
    await expect(page.getByLabel("Matches")).toHaveText("2 matches");

    // The way of reading is remembered for this person.
    await page.reload();
    await expect(page.getByRole("region", { name: "Raw view" })).toBeVisible();
  });

  test("the pentest page links to the results", async ({ page, playwright, baseURL }) => {
    const name = uniqueName("link");
    const id = await makeThroughApi(playwright, baseURL, name);
    await page.goto(`/pentests/${id}`);
    await expect(page.getByText("Nothing has been recorded yet.")).toBeVisible();
    await page.getByRole("link", { name: "Open the results" }).click();
    await expect(page.getByRole("heading", { name: `Results: ${name}`, level: 1 })).toBeVisible();
  });
});

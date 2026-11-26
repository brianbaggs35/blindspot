import { type Page } from "@playwright/test";
import { ADMIN_STATE } from "./accounts";
import { expect, test } from "./fixtures";
import { uniqueName } from "./people";
import { pickOption } from "./vuetify";

const SCOPE = "https://shop.example.com";

type Playwright = Parameters<Parameters<typeof test>[2]>[0]["playwright"];

/** Makes a running pentest straight through the API (agents only work on a running one). */
async function runningPentest(playwright: Playwright, baseURL: string | undefined, name: string) {
  const origin = new URL(baseURL ?? "").origin;
  const admin = await playwright.request.newContext({
    baseURL: origin,
    storageState: ADMIN_STATE,
    ignoreHTTPSErrors: true,
  });
  const headers = { Origin: origin };
  const made = await admin.post("/api/pentests", {
    headers,
    data: { name, methodology_id: "wstg", scope: { in_scope: [SCOPE] } },
  });
  expect(made.status()).toBe(201);
  const { id } = (await made.json()) as { id: string };
  const attested = await admin.post(`/api/pentests/${id}/attest`, {
    headers,
    data: { confirmation: name, text_version: await attestationVersion(admin) },
  });
  expect(attested.status()).toBe(200);
  const moved = await admin.post(`/api/pentests/${id}/status`, {
    headers,
    data: { to: "running" },
  });
  expect(moved.status()).toBe(200);
  await admin.dispose();
  return id;
}

async function attestationVersion(admin: Awaited<ReturnType<Playwright["request"]["newContext"]>>) {
  const found = (await (await admin.get("/api/pentests/attestation-text")).json()) as {
    version: string;
  };
  return found.version;
}

async function openAgents(page: Page, tab?: string) {
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Agents", level: 1 })).toBeVisible();
  if (tab) await page.getByRole("tab", { name: tab }).click();
}

// The caps and the prompts belong to the whole installation, so these run one after the other and
// each puts back what it changed.
test.describe("Agents (administrator)", () => {
  test.describe.configure({ mode: "serial" });

  test("lists the commander and every test agent, and narrows them", async ({ page }) => {
    await openAgents(page);
    await expect(page.getByText("Mission Commander")).toBeVisible();
    await expect(page.getByText("133 test agents shown.")).toBeVisible();
    await page.getByRole("textbox", { name: "Search agents" }).fill("WSTG-INFO-02");
    await expect(page.getByText("1 test agent shown.")).toBeVisible();
    await page.getByRole("button", { name: "Grid" }).click();
    await expect(page.getByRole("table")).toContainText("WSTG-INFO-02");
    await page.getByRole("textbox", { name: "Search agents" }).fill("no agent is called this");
    await expect(page.getByText("No agent matches that.")).toBeVisible();
    await page.getByRole("textbox", { name: "Search agents" }).fill("");
    await page.getByRole("button", { name: "Tree" }).click();
    await page.getByRole("button", { name: /Information Gathering/ }).click();
    await expect(page.getByRole("listitem", { name: "WSTG-INFO-02" })).toBeVisible();
  });

  test("changes the default caps, keeps them, and puts the built-in ones back", async ({
    page,
  }) => {
    await openAgents(page, "Defaults and presets");
    const steps = page.getByLabel("Steps in a mission");
    await expect(steps).toHaveValue("300");
    await expect(page.getByRole("button", { name: "Save the caps" })).toBeDisabled();
    await steps.fill("0");
    await expect(page.getByText("Steps in a mission must be between 1 and 100000.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save the caps" })).toBeDisabled();
    await steps.fill("120");
    await page.getByRole("button", { name: "Save the caps" }).click();
    await expect(page.getByText("The default caps were saved.")).toBeVisible();

    await page.reload();
    await page.getByRole("tab", { name: "Defaults and presets" }).click();
    await expect(page.getByLabel("Steps in a mission")).toHaveValue("120");
    await expect(page.getByText("Passive recon only")).toBeVisible();

    await page.getByRole("button", { name: "Put back the built-in caps" }).click();
    await expect(page.getByText("The default caps were put back.")).toBeVisible();
    await expect(page.getByLabel("Steps in a mission")).toHaveValue("300");
  });

  test("adds a version of a prompt, compares it, uses it and puts the built-in one back", async ({
    page,
  }) => {
    const text = `You are a careful tester. ${uniqueName("version")} Work one test at a time.`;
    await openAgents(page, "Prompts");
    await expect(page.getByRole("list", { name: "Versions" })).toContainText("Built in");
    await page.getByRole("button", { name: "Add a version" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: "Add the version" })).toBeEnabled();
    await dialog.getByLabel("Prompt text").fill("too short");
    await expect(dialog.getByRole("button", { name: "Add the version" })).toBeDisabled();
    await dialog.getByLabel("Prompt text").fill(text);
    await dialog.getByLabel("What changed").fill("A test version");
    await dialog.getByRole("button", { name: "Add the version" }).click();
    await expect(page.getByText("A new version was added.")).toBeVisible();

    const versions = page.getByRole("list", { name: "Versions" });
    await expect(versions).toContainText("A test version");
    await expect(versions).toContainText("In use");
    await expect(page.locator("pre[aria-label='Prompt text']")).toContainText(text);

    await pickOption(page, page, "Compare with", /Built in/);
    await expect(page.locator("pre[aria-label='Prompt changes']")).toContainText(`+ ${text}`);

    await page.getByRole("button", { name: "Put back the built-in prompt" }).click();
    await expect(page.getByText("The built-in prompt is in use again.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Put back the built-in prompt" })).toHaveCount(0);
    await page
      .getByRole("button", { name: /Use Version/ })
      .first()
      .click();
    await expect(page.getByText(/Version \d+ is in use\./)).toBeVisible();
    await page.getByRole("button", { name: "Put back the built-in prompt" }).click();
    await expect(page.getByText("The built-in prompt is in use again.")).toBeVisible();
  });
});

test.describe("Deploying agents (administrator)", () => {
  test("reviews what a mission would do before anything starts", async ({
    page,
    playwright,
    baseURL,
  }) => {
    const name = uniqueName("deploy");
    const id = await runningPentest(playwright, baseURL, name);
    await page.goto(`/pentests/${id}`);
    await page.getByRole("link", { name: "Open the agents" }).click();
    await expect(page.getByRole("heading", { name: `Agents: ${name}`, level: 1 })).toBeVisible();
    await expect(page.getByText("No agents have been deployed on this pentest.")).toBeVisible();

    await page.getByRole("button", { name: "Deploy agents" }).click();
    const dialog = page.getByRole("dialog", { name: "Deploy agents" });
    await dialog.getByRole("radio", { name: /Passive recon only/ }).check();
    await dialog.getByRole("button", { name: "Next" }).click();
    await expect(dialog.getByLabel("Steps in a test")).toHaveValue("6");
    await dialog.getByRole("button", { name: "Review" }).click();
    await expect(dialog.getByText(/tests will run/)).toBeVisible();
    await expect(dialog.getByText(SCOPE)).toBeVisible();
    await expect(dialog.getByText("0 intrusive", { exact: false })).toBeVisible();

    // Nothing starts until the scope is confirmed, and no tool runner is connected yet.
    const start = dialog.getByRole("button", { name: "Start the agents" });
    await expect(start).toBeDisabled();
    await dialog.getByRole("checkbox", { name: /I confirm/ }).check();
    await expect(start).toBeDisabled();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByText("No agents have been deployed on this pentest.")).toBeVisible();
  });
});

test.describe("Following a mission", () => {
  test("shows its progress and lets an administrator review and control it", async ({ page }) => {
    let status = "running";
    let awaitingApproval = true;
    const missionId = "mission-coverage";
    const missionPath = `/api/pentests/coverage/missions/${missionId}`;
    const budget = {
      steps: 300,
      steps_per_test: 12,
      tokens: 2_000_000,
      tokens_per_test: 120_000,
      cost_usd: 25,
      seconds: 21_600,
      seconds_per_test: 900,
      concurrency: 2,
      verify_from: "medium",
    };

    await page.route("**/api/pentests/coverage", (route) =>
      route.fulfill({
        json: {
          id: "coverage",
          name: "Coverage mission",
          status: "running",
          methodology_id: "wstg",
          archived_at: null,
          deleted_at: null,
          scope: { in_scope: ["https://shop.example.com/"] },
        },
      }),
    );
    await page.route("**/api/pentests/coverage/missions", (route) =>
      route.fulfill({
        json: {
          missions: [
            {
              id: missionId,
              pentest_id: "coverage",
              status,
              budget,
              spent: { steps: 1, cost_usd: 0.5, seconds: 120 },
              plan: { runs: 1, skipped: 0, max_risk: "active" },
              prompts: { "test-agent": 0, verifier: 0 },
              stop_reason: "",
              started_at: "2026-11-25T10:00:00Z",
              finished_at: null,
              created_at: "2026-11-25T10:00:00Z",
            },
          ],
        },
      }),
    );
    await page.route("**/api/agents/overview", (route) =>
      route.fulfill({ json: { runner_ready: true } }),
    );
    await page.route(`${missionPath}**`, async (route) => {
      const method = route.request().method();
      const url = new URL(route.request().url());
      const path = url.pathname;
      if (method === "GET" && path === missionPath) {
        await route.fulfill({
          json: {
            mission: {
              id: missionId,
              pentest_id: "coverage",
              status,
              budget,
              spent: { steps: 1, cost_usd: 0.5, seconds: 120 },
              plan: { runs: 1, skipped: 0, max_risk: "active" },
              prompts: { "test-agent": 0, verifier: 0 },
              stop_reason: "",
              started_at: "2026-11-25T10:00:00Z",
              finished_at: null,
              created_at: "2026-11-25T10:00:00Z",
            },
            tasks: [
              {
                id: "commander",
                parent_id: null,
                kind: "commander",
                ref: "commander",
                name: "Mission Commander",
                phase: 0,
                position: 0,
                status: "done",
                summary: "Planned 1 test in 1 category.",
                outcome: null,
                spent: {},
              },
              {
                id: "category",
                parent_id: "commander",
                kind: "category",
                ref: "WSTG-CONF",
                name: "Configuration",
                phase: 0,
                position: 0,
                status: "running",
                summary: "",
                outcome: null,
                spent: {},
              },
              {
                id: "test",
                parent_id: "category",
                kind: "test",
                ref: "WSTG-CONF-01",
                name: "Network configuration",
                phase: 0,
                position: 0,
                status: "waiting",
                summary: "Waiting for approval.",
                outcome: null,
                spent: {},
              },
            ],
          },
        });
      } else if (method === "GET" && path.endsWith("/steps")) {
        await route.fulfill({
          json: {
            steps: awaitingApproval
              ? [
                  {
                    id: "step",
                    task_id: "test",
                    seq: 1,
                    status: "awaiting_approval",
                    tool: "c.nmap",
                    request: { target: "shop.example.com", ports: [80, 443] },
                    verdict: null,
                    result_id: null,
                    note: "",
                    created_at: "2026-11-25T10:01:00Z",
                  },
                ]
              : [],
          },
        });
      } else if (method === "GET" && path.endsWith("/events")) {
        await route.fulfill({
          json: {
            events:
              url.searchParams.get("after") === "0"
                ? [
                    {
                      id: 1,
                      task_id: null,
                      type: "mission_started",
                      data: { runs: 1, skipped: 0 },
                      created_at: "2026-11-25T10:00:00Z",
                    },
                  ]
                : [],
            next_after: 1,
          },
        });
      } else if (method === "POST") {
        if (path.endsWith("/pause")) status = "paused";
        if (path.endsWith("/resume")) status = "running";
        if (path.endsWith("/cancel")) status = "cancelling";
        if (path.endsWith("/approve")) awaitingApproval = false;
        await route.fulfill({ status: 204 });
      } else {
        await route.fulfill({ status: 404 });
      }
    });

    await page.goto("/pentests/coverage/agents");
    await expect(page.getByRole("heading", { name: "Agents: Coverage mission" })).toBeVisible();
    await expect(page.getByText("Waiting for you")).toBeVisible();
    await expect(page.getByText("Mission started: 1 tests to run, 0 skipped.")).toBeVisible();
    await expect(page.getByText("target: shop.example.com, ports: [80,443]")).toBeVisible();

    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByText("Waiting for you")).toHaveCount(0);
    await page.getByRole("button", { name: "Pause" }).click();
    const missionStatus = page.locator("section[aria-label='Mission'] .v-chip").first();
    await expect(missionStatus).toHaveText("Paused");
    await page.getByRole("button", { name: "Resume" }).click();
    await expect(missionStatus).toHaveText("Running");
    await page.getByRole("button", { name: "Cancel the mission" }).click();
    await expect(missionStatus).toHaveText("Cancelling");
    await expect(page.getByRole("button", { name: "Cancel the mission" })).toHaveCount(0);
  });
});

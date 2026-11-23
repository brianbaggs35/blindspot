import { defineConfig, devices } from "@playwright/test";

// Two ways to run the same tests (docs/how-to/development.md):
//   host       the API (uvicorn) and the built web app (vite preview) on this machine
//   container  the real image, started with .github/scripts/run-container.sh; set E2E_MODE=container
const container = process.env["E2E_MODE"] === "container";
const ci = process.env["CI"] !== undefined && process.env["CI"] !== "";
const baseURL =
  process.env["E2E_BASE_URL"] ?? (container ? "https://127.0.0.1:8443" : "http://127.0.0.1:4173");
// CI installs the browser Playwright expects; elsewhere point this at any Chromium.
const chromium = process.env["E2E_CHROMIUM"];

export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.spec.ts",
  outputDir: "e2e-results/artifacts",
  fullyParallel: true,
  forbidOnly: ci,
  retries: ci ? 1 : 0,
  ...(ci ? { workers: 2 } : {}),
  timeout: 30_000,
  expect: { timeout: 7_500 },
  // A blob report per shard is merged into one HTML report by the workflow. The host and the
  // container jobs both run shards 1 to 3, so the mode is in the name; otherwise their reports
  // overwrite each other when downloaded together.
  reporter: ci
    ? [
        [
          "blob",
          {
            outputDir: "e2e-results/blob",
            fileName: `report-${container ? "container" : "host"}-${process.env["SHARD"] ?? "1"}.zip`,
          },
        ],
        ["github"],
      ]
    : [["list"], ["html", { open: "never", outputFolder: "e2e-results/report" }]],
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL,
    // The container makes its own certificate on first start.
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(chromium === undefined ? {} : { launchOptions: { executablePath: chromium } }),
      },
    },
  ],
  // Host mode starts the API and the built web app itself; container mode finds them running.
  ...(container
    ? {}
    : {
        webServer: [
          {
            command: "uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000",
            cwd: "../backend",
            // A fixed key for the throwaway API the tests start. It protects nothing.
            env: { BLINDSPOT_SECRET_KEY: "e2e-only-key-".padEnd(48, "0") },
            url: "http://127.0.0.1:8000/api/health",
            reuseExistingServer: !ci,
            timeout: 60_000,
          },
          {
            command: "npm run preview:e2e",
            url: "http://127.0.0.1:4173",
            reuseExistingServer: !ci,
            timeout: 60_000,
          },
        ],
      }),
});

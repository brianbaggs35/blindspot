import { request, type FullConfig } from "@playwright/test";
import { ADMIN, ADMIN_STATE, SETUP_CODE } from "./accounts";
import { collectCoverage, newCoverageReport } from "./coverage";

// Start each run with an empty coverage cache and a signed-in administrator.
export default async function globalSetup(config: FullConfig): Promise<void> {
  if (collectCoverage) newCoverageReport().cleanCache();
  await signInAdministrator(config.projects[0]?.use.baseURL ?? "http://localhost:4173");
}

// The first run on a fresh database does first-run setup, with the code the API was told to use;
// every run after that just signs in. Either way the session is saved for the specs to start from.
async function signInAdministrator(baseURL: string): Promise<void> {
  const context = await request.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
    // A browser says which site a request comes from; so does this client.
    extraHTTPHeaders: { Origin: new URL(baseURL).origin },
  });
  const status = (await (await context.get("/api/auth/status")).json()) as {
    setup_required: boolean;
  };
  const answer = status.setup_required
    ? await context.post("/api/auth/setup", {
        data: {
          setup_code: SETUP_CODE,
          username: ADMIN.username,
          display_name: ADMIN.displayName,
          password: ADMIN.password,
        },
      })
    : await context.post("/api/auth/login", {
        data: { username: ADMIN.username, password: ADMIN.password },
      });
  if (!answer.ok()) {
    throw new Error(`Could not sign in the test administrator: ${String(answer.status())}`);
  }
  await context.storageState({ path: ADMIN_STATE });
  await context.dispose();
}

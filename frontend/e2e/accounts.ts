import path from "node:path";

// Everything the specs share about accounts. The values protect nothing: they exist only for the
// throwaway API and container the tests start.
export const container = process.env["E2E_MODE"] === "container";

export const SETUP_CODE = "e2e-setup-code-0123456789";

export const ADMIN = {
  username: "e2e-admin",
  displayName: "E2E Administrator",
  password: "violet harbour lantern 2026",
};

// Where global-setup saves the administrator's session, and what a signed-out visitor has.
export const ADMIN_STATE = path.resolve("e2e-results/admin-state.json");
export const SIGNED_OUT = { cookies: [], origins: [] };

// How the API the tests start is configured (host mode; the container gets the same from the
// workflow). Over http on localhost the cookie cannot be Secure, passkeys belong to `localhost`,
// and the throttle is wide so the sign-in specs cannot lock each other out.
export const API_ENV: Record<string, string> = {
  BLINDSPOT_SECRET_KEY: "e2e-only-key-".padEnd(48, "0"),
  BLINDSPOT_SETUP_CODE: SETUP_CODE,
  BLINDSPOT_COOKIE_SECURE: "false",
  BLINDSPOT_PUBLIC_ORIGIN: "http://localhost:4173",
  BLINDSPOT_THROTTLE_FAILURES: "1000",
  BLINDSPOT_PASSKEY_FAILURES: "1000",
  BLINDSPOT_DATA_DIR: path.resolve("e2e-results/data"),
  ...(process.env["BLINDSPOT_DATABASE_URL"] === undefined
    ? {}
    : { BLINDSPOT_DATABASE_URL: process.env["BLINDSPOT_DATABASE_URL"] }),
};

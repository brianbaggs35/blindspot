// Every page of the app. The accessibility and layout specs run on each one, so a pull request
// that adds a page adds it here.
export interface PageEntry {
  name: string;
  path: string;
  /** Signed in as the administrator (the default), or a visitor with no session. */
  signedIn?: boolean;
  /** The page is only shown while first-run setup is open, so the API's answer is faked. */
  mockSetup?: boolean;
}

export const pages: readonly PageEntry[] = [
  { name: "home", path: "/" },
  { name: "users", path: "/users" },
  { name: "audit log", path: "/audit" },
  { name: "account", path: "/account" },
  { name: "no access", path: "/forbidden" },
  { name: "not found", path: "/no-such-page" },
  { name: "sign in", path: "/sign-in", signedIn: false },
  { name: "setup", path: "/setup", signedIn: false, mockSetup: true },
];

// The widths the layout is checked at: small phone, phone, large phone, tablet, laptop, desktop.
export const widths = [320, 390, 600, 768, 1024, 1280] as const;

export const themes = ["midnight", "daylight"] as const;
export type Theme = (typeof themes)[number];

// The theme store keeps the choice here (src/stores/theme.ts).
export const THEME_KEY = "blindspot.theme";

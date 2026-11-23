// Every page of the app. The accessibility and layout specs run on each one, so a pull request
// that adds a page adds it here.
export const pages: readonly { name: string; path: string }[] = [
  { name: "home", path: "/" },
  { name: "not found", path: "/no-such-page" },
];

// The widths the layout is checked at: small phone, phone, large phone, tablet, laptop, desktop.
export const widths = [320, 390, 600, 768, 1024, 1280] as const;

export const themes = ["midnight", "daylight"] as const;
export type Theme = (typeof themes)[number];

// The theme store keeps the choice here (src/stores/theme.ts).
export const THEME_KEY = "blindspot.theme";

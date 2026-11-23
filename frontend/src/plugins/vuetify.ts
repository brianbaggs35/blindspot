import { aliases, mdi } from "vuetify/iconsets/mdi-svg";
import { createVuetify, type ThemeDefinition } from "vuetify";
import { cspNonce } from "../csp";

// Two themes on the same tokens. Cyan to indigo is the logo's ring; amber is for blind spots
// and warnings only; red is for critical issues; green is for passed.
export const midnight: ThemeDefinition = {
  dark: true,
  colors: {
    background: "#070b14",
    surface: "#0d1424",
    "surface-bright": "#16203a",
    primary: "#22d3ee",
    secondary: "#818cf8",
    accent: "#f59e0b",
    info: "#38bdf8",
    success: "#22c55e",
    warning: "#f59e0b",
    error: "#f87171",
  },
};

export const daylight: ThemeDefinition = {
  dark: false,
  colors: {
    background: "#f4f7fb",
    surface: "#ffffff",
    "surface-bright": "#eef2f9",
    primary: "#0e7490",
    secondary: "#4f46e5",
    accent: "#b45309",
    info: "#0369a1",
    success: "#15803d",
    warning: "#b45309",
    error: "#b91c1c",
  },
};

export function createBlindspotVuetify(defaultTheme: "midnight" | "daylight" = "midnight") {
  const nonce = cspNonce();
  return createVuetify({
    icons: { defaultSet: "mdi", aliases, sets: { mdi } },
    theme: {
      defaultTheme,
      themes: { midnight, daylight },
      ...(nonce === undefined ? {} : { cspNonce: nonce }),
    },
    defaults: {
      VBtn: { rounded: "lg" },
      VCard: { rounded: "lg" },
    },
  });
}

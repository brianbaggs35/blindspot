import { createApp } from "vue";
import { describe, expect, it } from "vitest";
import { createBlindspotVuetify, daylight, midnight } from "../src/plugins/vuetify";

// WCAG contrast ratio between two #rrggbb colours.
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => {
    const value = parseInt(hex.slice(start, start + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  const [r = 0, g = 0, b = 0] = channels;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Vuetify allows a colour to be an object; ours are all #rrggbb strings, and this checks it.
function hex(color: unknown): string {
  if (typeof color !== "string") throw new Error("expected a #rrggbb colour");
  return color;
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

describe("themes", () => {
  it("defines a dark and a light theme", () => {
    expect(midnight.dark).toBe(true);
    expect(daylight.dark).toBe(false);
  });

  it.each([
    ["midnight", midnight],
    ["daylight", daylight],
  ])("%s keeps its main colours readable on its surface (WCAG AA, 4.5:1)", (_name, theme) => {
    const colors = theme.colors ?? {};
    const surface = hex(colors.surface);
    const main = [
      colors.primary,
      colors.secondary,
      colors.warning,
      colors.error,
      colors.success,
      colors.info,
    ];
    expect(main).toHaveLength(6);
    for (const color of main) {
      expect(contrast(hex(color), surface)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("starts in the requested theme", () => {
    expect(createBlindspotVuetify("daylight").theme.name.value).toBe("daylight");
    expect(createBlindspotVuetify().theme.name.value).toBe("midnight");
  });

  it("puts the page's nonce on Vuetify's theme styles, so they pass the Content-Security-Policy", () => {
    document.head.innerHTML = '<meta name="csp-nonce" content="abc123" />';
    const app = createApp({ render: () => null }).use(createBlindspotVuetify());
    app.mount(document.createElement("div"));
    try {
      const styles = document.getElementById("vuetify-theme-stylesheet");
      expect(styles?.getAttribute("nonce")).toBe("abc123");
    } finally {
      app.unmount();
      document.head.innerHTML = "";
    }
  });
});

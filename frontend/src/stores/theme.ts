import { defineStore } from "pinia";

export type ThemeName = "midnight" | "daylight";

const STORAGE_KEY = "blindspot.theme";

function readSaved(): ThemeName | null {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "midnight" || saved === "daylight" ? saved : null;
  } catch {
    // Storage can be blocked (private windows); the theme then just isn't remembered.
    return null;
  }
}

function save(name: ThemeName): void {
  try {
    localStorage.setItem(STORAGE_KEY, name);
  } catch {
    // See readSaved.
  }
}

export function systemTheme(): ThemeName {
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "daylight" : "midnight";
}

export const useThemeStore = defineStore("theme", {
  state: (): { name: ThemeName } => ({ name: readSaved() ?? systemTheme() }),
  getters: {
    isDark: (state) => state.name === "midnight",
  },
  actions: {
    set(name: ThemeName) {
      this.name = name;
      save(name);
    },
    toggle() {
      this.set(this.name === "midnight" ? "daylight" : "midnight");
    },
  },
});

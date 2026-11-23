import { defineStore } from "pinia";
import { readSetting, writeSetting } from "../storage";

export type ThemeName = "midnight" | "daylight";

const STORAGE_KEY = "blindspot.theme";

function readSaved(): ThemeName | null {
  const saved = readSetting(STORAGE_KEY);
  return saved === "midnight" || saved === "daylight" ? saved : null;
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
      writeSetting(STORAGE_KEY, name);
    },
    toggle() {
      this.set(this.name === "midnight" ? "daylight" : "midnight");
    },
  },
});

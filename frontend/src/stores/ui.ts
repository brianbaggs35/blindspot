import { defineStore } from "pinia";
import { readSetting, writeSetting } from "../storage";

const NAV_KEY = "blindspot.nav";
const EFFECTS_KEY = "blindspot.effects";

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// What the person has chosen about how the shell looks and behaves. Effects (the radar grid,
// the pulse on live things) follow the system's "reduce motion" until the person chooses.
export const useUiStore = defineStore("ui", {
  state: () => {
    const effects = readSetting(EFFECTS_KEY);
    return {
      navCollapsed: readSetting(NAV_KEY) === "collapsed",
      effects: effects === null ? !prefersReducedMotion() : effects === "on",
      paletteOpen: false,
    };
  },
  actions: {
    toggleNav() {
      this.navCollapsed = !this.navCollapsed;
      writeSetting(NAV_KEY, this.navCollapsed ? "collapsed" : "expanded");
    },
    toggleEffects() {
      this.effects = !this.effects;
      writeSetting(EFFECTS_KEY, this.effects ? "on" : "off");
    },
    openPalette() {
      this.paletteOpen = true;
    },
    closePalette() {
      this.paletteOpen = false;
    },
  },
});

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useUiStore } from "../src/stores/ui";

function reducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: reduce, addEventListener: vi.fn() }),
  );
}

describe("ui store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts expanded, with effects on, and the palette closed", () => {
    reducedMotion(false);
    const ui = useUiStore();
    expect(ui.navCollapsed).toBe(false);
    expect(ui.effects).toBe(true);
    expect(ui.paletteOpen).toBe(false);
  });

  it("turns effects off for someone who asked their system for less motion", () => {
    reducedMotion(true);
    expect(useUiStore().effects).toBe(false);
  });

  it("lets an explicit choice win over the system", () => {
    reducedMotion(true);
    localStorage.setItem("blindspot.effects", "on");
    expect(useUiStore().effects).toBe(true);
    setActivePinia(createPinia());
    reducedMotion(false);
    localStorage.setItem("blindspot.effects", "off");
    expect(useUiStore().effects).toBe(false);
  });

  it("remembers the menu and the effects", () => {
    reducedMotion(false);
    const ui = useUiStore();
    ui.toggleNav();
    expect(localStorage.getItem("blindspot.nav")).toBe("collapsed");
    ui.toggleNav();
    expect(localStorage.getItem("blindspot.nav")).toBe("expanded");
    ui.toggleEffects();
    expect(localStorage.getItem("blindspot.effects")).toBe("off");
    ui.toggleEffects();
    expect(localStorage.getItem("blindspot.effects")).toBe("on");
    localStorage.setItem("blindspot.nav", "collapsed");
    setActivePinia(createPinia());
    expect(useUiStore().navCollapsed).toBe(true);
  });

  it("opens and closes the palette", () => {
    reducedMotion(false);
    const ui = useUiStore();
    ui.openPalette();
    expect(ui.paletteOpen).toBe(true);
    ui.closePalette();
    expect(ui.paletteOpen).toBe(false);
  });
});

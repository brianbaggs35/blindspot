import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { systemTheme, useThemeStore } from "../src/stores/theme";

function prefersLight(light: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: light, addEventListener: vi.fn() }),
  );
}

describe("theme store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("follows the system when nothing is saved", () => {
    prefersLight(true);
    expect(systemTheme()).toBe("daylight");
    expect(useThemeStore().name).toBe("daylight");
  });

  it("is dark by default", () => {
    prefersLight(false);
    const store = useThemeStore();
    expect(store.name).toBe("midnight");
    expect(store.isDark).toBe(true);
  });

  it("uses the saved choice over the system", () => {
    localStorage.setItem("blindspot.theme", "daylight");
    prefersLight(false);
    expect(useThemeStore().name).toBe("daylight");
  });

  it("ignores a saved value it doesn't know", () => {
    localStorage.setItem("blindspot.theme", "neon");
    prefersLight(false);
    expect(useThemeStore().name).toBe("midnight");
  });

  it("toggles and remembers the choice", () => {
    prefersLight(false);
    const store = useThemeStore();
    store.toggle();
    expect(store.name).toBe("daylight");
    expect(localStorage.getItem("blindspot.theme")).toBe("daylight");
    store.toggle();
    expect(store.name).toBe("midnight");
  });

  it("still works when storage is blocked", () => {
    prefersLight(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const store = useThemeStore();
    expect(store.name).toBe("midnight");
    store.toggle();
    expect(store.name).toBe("daylight");
    vi.restoreAllMocks();
  });
});

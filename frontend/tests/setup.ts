import { config, enableAutoUnmount } from "@vue/test-utils";
import { afterEach, beforeEach, vi } from "vitest";
import "vuetify/styles";

// Vuetify measures elements with these, which jsdom doesn't have.
class ResizeObserverStub {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
globalThis.ResizeObserver = ResizeObserverStub;

// Vuetify places dialogs and tooltips against the visual viewport, which jsdom lacks.
Object.defineProperty(window, "visualViewport", {
  configurable: true,
  value: {
    width: 1280,
    height: 800,
    offsetLeft: 0,
    offsetTop: 0,
    scale: 1,
    addEventListener() {},
    removeEventListener() {},
  },
});

// Whatever a test mounts is taken down after it, so one test never sees another's dialogs.
enableAutoUnmount(afterEach);

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  config.global.plugins = [];
});

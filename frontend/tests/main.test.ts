import { describe, expect, it, vi } from "vitest";

describe("main", () => {
  it("mounts the app on #app", async () => {
    vi.resetModules();
    document.body.innerHTML = '<div id="app"></div>';
    await import("../src/main");
    await vi.waitFor(() => {
      expect(document.querySelector("#app")?.textContent).toContain("Blindspot");
    });
  });
});

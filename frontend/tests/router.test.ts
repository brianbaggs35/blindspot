import { createMemoryHistory } from "vue-router";
import { describe, expect, it } from "vitest";
import { createBlindspotRouter, routes } from "../src/router";

describe("router", () => {
  it("has a home route that loads its view", async () => {
    const router = createBlindspotRouter(createMemoryHistory());
    await router.push("/");
    expect(router.currentRoute.value.name).toBe("home");
    const home = routes[0];
    expect(home).toBeDefined();
    expect(await home?.component()).toHaveProperty("default");
  });

  it("uses browser history by default", () => {
    expect(createBlindspotRouter().options.history).toBeDefined();
  });
});

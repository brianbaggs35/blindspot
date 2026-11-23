import { createMemoryHistory } from "vue-router";
import { beforeEach, describe, expect, it } from "vitest";
import { createBlindspotRouter, routes } from "../src/router";

async function load(path: string) {
  const route = routes.find((candidate) => candidate.path === path);
  const component = route?.component as (() => Promise<unknown>) | undefined;
  expect(component).toBeDefined();
  return component?.();
}

describe("router", () => {
  beforeEach(() => {
    document.title = "";
  });

  it("has a home route that loads its view", async () => {
    const router = createBlindspotRouter(createMemoryHistory());
    await router.push("/");
    expect(router.currentRoute.value.name).toBe("home");
    expect(await load("/")).toHaveProperty("default");
  });

  it("shows the not-found page for an address nobody knows", async () => {
    const router = createBlindspotRouter(createMemoryHistory());
    await router.push("/nothing/here");
    expect(router.currentRoute.value.name).toBe("not-found");
    expect(await load("/:pathMatch(.*)*")).toHaveProperty("default");
  });

  it("puts the page's name in the tab title", async () => {
    const router = createBlindspotRouter(createMemoryHistory());
    await router.push("/");
    expect(document.title).toBe("Blindspot");
    await router.push("/missing");
    expect(document.title).toBe("Page not found · Blindspot");
  });

  it("uses browser history by default", () => {
    expect(createBlindspotRouter().options.history).toBeDefined();
  });
});

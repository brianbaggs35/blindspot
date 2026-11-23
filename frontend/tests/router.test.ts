import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory } from "vue-router";
import { beforeEach, describe, expect, it } from "vitest";
import { api, setSessionEndedHandler } from "../src/api/client";
import { createBlindspotRouter, routes } from "../src/router";
import { useAuthStore } from "../src/stores/auth";
import { admin } from "./helpers";

async function load(path: string) {
  const route = routes.find((candidate) => candidate.path === path);
  const component = route?.component as (() => Promise<unknown>) | undefined;
  expect(component).toBeDefined();
  return component?.();
}

function signedInRouter() {
  setActivePinia(createPinia());
  useAuthStore().$patch({ loaded: true, user: admin });
  return createBlindspotRouter(createMemoryHistory());
}

describe("router", () => {
  beforeEach(() => {
    document.title = "";
    setSessionEndedHandler(undefined);
  });

  it("has a page for every route and loads its view", async () => {
    const paths = routes.map((route) => route.path);
    expect(paths).toEqual([
      "/",
      "/setup",
      "/sign-in",
      "/users",
      "/audit",
      "/account",
      "/forbidden",
      "/:pathMatch(.*)*",
    ]);
    for (const path of paths) expect(await load(path)).toHaveProperty("default");
  });

  it("shows the not-found page for an address nobody knows", async () => {
    const router = signedInRouter();
    await router.push("/nothing/here");
    expect(router.currentRoute.value.name).toBe("not-found");
  });

  it("puts the page's name in the tab title", async () => {
    const router = signedInRouter();
    await router.push("/");
    expect(document.title).toBe("Blindspot");
    await router.push("/missing");
    expect(document.title).toBe("Page not found · Blindspot");
  });

  it("sends someone whose session ended to sign in, and back to the page afterwards", async () => {
    const router = signedInRouter();
    await router.push("/account");
    // The handler the router installed is the one the API client calls on a 401.
    globalThis.fetch = () =>
      Promise.resolve(
        new Response(JSON.stringify({ code: "not_signed_in", title: "Sign in to continue" }), {
          status: 401,
        }),
      );
    await expect(api("GET", "/api/auth/me")).rejects.toThrow("Sign in to continue");
    await router.isReady();
    await new Promise((resolve) => setTimeout(resolve));
    expect(useAuthStore().user).toBeNull();
    expect(router.currentRoute.value.name).toBe("sign-in");
    expect(router.currentRoute.value.query["next"]).toBe("/account");
  });

  it("does nothing when nobody was signed in to begin with", async () => {
    setActivePinia(createPinia());
    useAuthStore().$patch({ loaded: true, user: null });
    const router = createBlindspotRouter(createMemoryHistory());
    await router.push("/sign-in");
    globalThis.fetch = () =>
      Promise.resolve(new Response(JSON.stringify({ code: "not_signed_in" }), { status: 401 }));
    await expect(api("GET", "/api/auth/me")).rejects.toThrow();
    expect(router.currentRoute.value.name).toBe("sign-in");
    expect(router.currentRoute.value.query["next"]).toBeUndefined();
  });

  it("uses browser history by default", () => {
    setActivePinia(createPinia());
    expect(createBlindspotRouter().options.history).toBeDefined();
  });
});

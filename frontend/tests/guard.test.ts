import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory } from "vue-router";
import { beforeEach, describe, expect, it } from "vitest";
import { safeNext } from "../src/router/guard";
import { createBlindspotRouter } from "../src/router";
import { useAuthStore } from "../src/stores/auth";
import { admin, mockApi, viewer } from "./helpers";
import type { User } from "../src/api/types";

function router(state: { user: User | null; setupRequired?: boolean }) {
  setActivePinia(createPinia());
  useAuthStore().$patch({ loaded: true, setupRequired: false, ...state });
  const made = createBlindspotRouter(createMemoryHistory());
  made.addRoute({
    path: "/users",
    name: "users",
    component: { render: () => null },
    meta: { access: "admin" },
  });
  return made;
}

describe("safeNext", () => {
  it.each([
    ["/account", "/account"],
    ["/findings?tab=open", "/findings?tab=open"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["https://evil.example", "/"],
    ["account", "/"],
    [undefined, "/"],
    [["/a", "/b"], "/"],
  ])("%s -> %s", (raw, expected) => {
    expect(safeNext(raw)).toBe(expected);
  });
});

describe("the guard", () => {
  beforeEach(() => {
    mockApi({});
  });

  it("sends a visitor to sign in, remembering where they were going", async () => {
    const r = router({ user: null });
    await r.push("/account?tab=passkeys");
    expect(r.currentRoute.value.name).toBe("sign-in");
    expect(r.currentRoute.value.query["next"]).toBe("/account?tab=passkeys");
  });

  it("lets a visitor open the public pages", async () => {
    const r = router({ user: null });
    await r.push("/sign-in");
    expect(r.currentRoute.value.name).toBe("sign-in");
  });

  it("sends everyone to setup while there is no administrator, and nowhere else", async () => {
    const r = router({ user: null, setupRequired: true });
    await r.push("/account");
    expect(r.currentRoute.value.name).toBe("setup");
    await r.push("/sign-in");
    expect(r.currentRoute.value.name).toBe("setup");
    await r.push("/setup");
    expect(r.currentRoute.value.name).toBe("setup");
  });

  it("closes the setup page once there is an administrator", async () => {
    const r = router({ user: null });
    await r.push("/setup");
    expect(r.currentRoute.value.name).toBe("sign-in");
    const signedIn = router({ user: admin });
    await signedIn.push("/setup");
    expect(signedIn.currentRoute.value.name).toBe("home");
  });

  it("takes someone who is already signed in away from the sign-in page", async () => {
    const r = router({ user: admin });
    await r.push("/sign-in?next=/account");
    expect(r.currentRoute.value.path).toBe("/account");
    await r.push("/sign-in?next=//evil.example");
    expect(r.currentRoute.value.path).toBe("/");
  });

  it("holds everyone back at the terms until they are accepted, then lets them through", async () => {
    const unaccepted = { ...admin, terms_accepted: false };
    const r = router({ user: unaccepted });
    await r.push("/account?tab=passkeys");
    expect(r.currentRoute.value.name).toBe("terms");
    expect(r.currentRoute.value.query["next"]).toBe("/account?tab=passkeys");
    await r.push("/pentests");
    expect(r.currentRoute.value.name).toBe("terms");
    await r.push("/terms");
    expect(r.currentRoute.value.name).toBe("terms");
    useAuthStore().$patch({ user: admin });
    await r.push("/terms?next=/account");
    expect(r.currentRoute.value.path).toBe("/account");
    await r.push("/terms");
    expect(r.currentRoute.value.path).toBe("/");
  });

  it("keeps a viewer out of administrator pages and lets an administrator in", async () => {
    const forViewer = router({ user: viewer });
    await forViewer.push("/users");
    expect(forViewer.currentRoute.value.name).toBe("forbidden");
    const forAdmin = router({ user: admin });
    await forAdmin.push("/users");
    expect(forAdmin.currentRoute.value.name).toBe("users");
  });
});

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../src/stores/auth";
import { admin, mockApi, viewer } from "./helpers";

describe("auth store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("asks the API who is signed in, once", async () => {
    const { fetchMock } = mockApi({
      "GET /api/auth/status": { json: { setup_required: false, user: admin } },
    });
    const auth = useAuthStore();
    await auth.load();
    await auth.load();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(auth.user).toEqual(admin);
    expect(auth.isSignedIn).toBe(true);
    expect(auth.isAdmin).toBe(true);
    await auth.load(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("knows when setup is needed", async () => {
    mockApi({ "GET /api/auth/status": { json: { setup_required: true, user: null } } });
    const auth = useAuthStore();
    await auth.load();
    expect(auth.setupRequired).toBe(true);
    expect(auth.isSignedIn).toBe(false);
    expect(auth.isAdmin).toBe(false);
  });

  it("treats a viewer as signed in but not an administrator", async () => {
    mockApi({ "GET /api/auth/status": { json: { setup_required: false, user: viewer } } });
    const auth = useAuthStore();
    await auth.load();
    expect(auth.isSignedIn).toBe(true);
    expect(auth.isAdmin).toBe(false);
  });

  it("treats an API that does not answer as signed out", async () => {
    mockApi({ "GET /api/auth/status": { status: 502 } });
    const auth = useAuthStore();
    auth.$patch({ user: admin, setupRequired: true });
    await auth.load();
    expect(auth.loaded).toBe(true);
    expect(auth.user).toBeNull();
    expect(auth.setupRequired).toBe(false);
  });

  it("sets up, signs in and signs out", async () => {
    const { calls } = mockApi({
      "POST /api/auth/setup": { json: admin },
      "POST /api/auth/login": { json: viewer },
      "POST /api/auth/logout": { status: 204 },
    });
    const auth = useAuthStore();
    auth.$patch({ setupRequired: true });
    await auth.setup({ setup_code: "c", username: "ada", display_name: "", password: "p" });
    expect(auth.user).toEqual(admin);
    expect(auth.setupRequired).toBe(false);
    await auth.signIn("vic", "pw");
    expect(auth.user).toEqual(viewer);
    expect(calls[1]?.body).toEqual({ username: "vic", password: "pw" });
    await auth.signOut();
    expect(auth.user).toBeNull();
  });

  it("is signed out even when the sign-out request fails", async () => {
    mockApi({ "POST /api/auth/logout": { status: 500, json: {} } });
    const auth = useAuthStore();
    auth.$patch({ user: admin });
    await auth.signOut();
    expect(auth.user).toBeNull();
  });

  it("records that the terms were accepted, for the person signed in", async () => {
    const { calls } = mockApi({ "POST /api/terms/accept": { json: {} } });
    const auth = useAuthStore();
    auth.$patch({ user: { ...admin, terms_accepted: false } });
    expect(auth.termsAccepted).toBe(false);
    await auth.acceptTerms("v1");
    expect(calls[0]?.body).toEqual({ version: "v1" });
    expect(auth.termsAccepted).toBe(true);
    auth.$patch({ user: null });
    await auth.acceptTerms("v1");
    expect(auth.user).toBeNull();
    expect(auth.termsAccepted).toBe(false);
  });

  it("forgets the person when the session ends", () => {
    const auth = useAuthStore();
    auth.$patch({ user: admin });
    auth.sessionEnded();
    expect(auth.user).toBeNull();
  });

  it("signs in with a passkey", async () => {
    vi.resetModules();
    vi.doMock("../src/passkeys", () => ({ signInWithPasskey: () => Promise.resolve(viewer) }));
    const { useAuthStore: fresh } = await import("../src/stores/auth");
    setActivePinia(createPinia());
    const auth = fresh();
    await auth.signInWithPasskey();
    expect(auth.user).toEqual(viewer);
    vi.doUnmock("../src/passkeys");
  });
});

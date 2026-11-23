import { afterEach, describe, expect, it, vi } from "vitest";
import {
  addPasskey,
  PasskeyCancelled,
  passkeysSupported,
  signInWithPasskey,
} from "../src/passkeys";
import { admin, mockApi } from "./helpers";

const ceremony = { challenge_id: "c-1", options: { challenge: "abc" } };
const credential = { toJSON: () => ({ id: "cred-1" }) };

const spies = { get: vi.fn(), create: vi.fn() };

function browserSupport(get: () => Promise<unknown>, create = get) {
  spies.get = vi.fn(get);
  spies.create = vi.fn(create);
  vi.stubGlobal("PublicKeyCredential", {
    parseRequestOptionsFromJSON: (options: unknown) => ({ parsed: options }),
    parseCreationOptionsFromJSON: (options: unknown) => ({ parsed: options }),
  });
  Object.defineProperty(navigator, "credentials", {
    configurable: true,
    value: spies,
  });
}

afterEach(() => {
  Reflect.deleteProperty(navigator, "credentials");
});

describe("passkeys", () => {
  it("knows whether the browser can use them", () => {
    expect(passkeysSupported()).toBe(false);
    vi.stubGlobal("PublicKeyCredential", {});
    expect(passkeysSupported()).toBe(false);
    vi.stubGlobal("PublicKeyCredential", { parseCreationOptionsFromJSON: () => 1 });
    expect(passkeysSupported()).toBe(false);
    browserSupport(() => Promise.resolve(credential));
    expect(passkeysSupported()).toBe(true);
  });

  it("signs in: asks for a challenge, the browser answers it, and the API checks it", async () => {
    browserSupport(() => Promise.resolve(credential));
    const { calls } = mockApi({
      "POST /api/auth/passkeys/login/options": { json: ceremony },
      "POST /api/auth/passkeys/login": { json: admin },
    });
    expect(await signInWithPasskey()).toEqual(admin);
    expect(spies.get).toHaveBeenCalledWith({
      publicKey: { parsed: ceremony.options },
    });
    expect(calls[1]?.body).toEqual({ challenge_id: "c-1", credential: { id: "cred-1" } });
  });

  it("adds a passkey with the password, a name and the browser's credential", async () => {
    browserSupport(() => Promise.resolve(credential));
    const { calls } = mockApi({
      "POST /api/auth/passkeys/register/options": { json: ceremony },
      "POST /api/auth/passkeys/register": { status: 201, json: { id: "p-1", name: "Laptop" } },
    });
    expect(await addPasskey("Laptop", "pw")).toMatchObject({ id: "p-1" });
    expect(calls[0]?.body).toEqual({ password: "pw" });
    expect(calls[1]?.body).toEqual({
      challenge_id: "c-1",
      name: "Laptop",
      credential: { id: "cred-1" },
    });
  });

  it.each(["NotAllowedError", "AbortError"])(
    "treats %s as the prompt being closed",
    async (name) => {
      browserSupport(() => Promise.reject(new DOMException("no", name)));
      mockApi({ "POST /api/auth/passkeys/login/options": { json: ceremony } });
      await expect(signInWithPasskey()).rejects.toBeInstanceOf(PasskeyCancelled);
    },
  );

  it("treats no credential as the prompt being closed", async () => {
    browserSupport(() => Promise.resolve(null));
    mockApi({ "POST /api/auth/passkeys/register/options": { json: ceremony } });
    await expect(addPasskey("x", "pw")).rejects.toBeInstanceOf(PasskeyCancelled);
  });

  it("lets other errors through", async () => {
    browserSupport(() => Promise.reject(new DOMException("bad", "SecurityError")));
    mockApi({ "POST /api/auth/passkeys/login/options": { json: ceremony } });
    await expect(signInWithPasskey()).rejects.toMatchObject({ name: "SecurityError" });
    browserSupport(() => Promise.reject(new Error("plain")));
    await expect(signInWithPasskey()).rejects.toThrow("plain");
  });

  it("says what a cancelled prompt means", () => {
    expect(new PasskeyCancelled().message).toContain("closed");
  });
});

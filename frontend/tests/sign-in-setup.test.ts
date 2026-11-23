import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PasskeyCancelled } from "../src/passkeys";
import SetupView from "../src/views/SetupView.vue";
import SignInView from "../src/views/SignInView.vue";
import ForbiddenView from "../src/views/ForbiddenView.vue";
import { admin, mockApi, mountWithApp } from "./helpers";

const GOOD = "violet harbour lantern 2026";

afterEach(() => {
  vi.doUnmock("../src/passkeys");
});

async function signIn(path = "/sign-in") {
  return mountWithApp(SignInView, path, {}, { user: null });
}

async function fill(
  wrapper: Awaited<ReturnType<typeof signIn>>["wrapper"],
  values: Record<string, string>,
) {
  for (const [selector, value] of Object.entries(values)) {
    await wrapper.get(selector).setValue(value);
  }
}

describe("SignInView", () => {
  it("signs in and goes where the person was heading", async () => {
    const { calls } = mockApi({ "POST /api/auth/login": { json: admin } });
    const { wrapper, router } = await signIn("/sign-in?next=/account");
    await fill(wrapper, {
      "input[autocomplete=username]": "ada",
      "input[autocomplete=current-password]": "pw",
    });
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(calls[0]?.body).toEqual({ username: "ada", password: "pw" });
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe("/account");
    });
  });

  it("shows the refusal in plain words and lets the person try again", async () => {
    mockApi({
      "POST /api/auth/login": {
        status: 401,
        json: { code: "invalid_credentials", title: "That username and password do not match" },
      },
    });
    const { wrapper, router } = await signIn();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain("do not match");
    expect(router.currentRoute.value.name).toBe("sign-in");
  });

  it("says how long to wait when the address is throttled", async () => {
    mockApi({
      "POST /api/auth/login": {
        status: 429,
        json: { code: "too_many_attempts", title: "Too many" },
        headers: { "Retry-After": "300" },
      },
    });
    const { wrapper } = await signIn();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain("5 minutes");
  });

  it("offers a passkey only where the browser can use one", async () => {
    const without = await signIn();
    expect(without.wrapper.text()).not.toContain("passkey");
    vi.resetModules();
    vi.doMock("../src/passkeys", () => ({
      passkeysSupported: () => true,
      signInWithPasskey: () => Promise.resolve(admin),
      PasskeyCancelled,
    }));
    const { default: Fresh } = await import("../src/views/SignInView.vue");
    const { mountWithApp: mountAgain } = await import("./helpers");
    const { wrapper, router } = await mountAgain(Fresh, "/sign-in", {}, { user: null });
    const button = wrapper.findAll("button").find((b) => b.text().includes("passkey"));
    await button?.trigger("click");
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe("/");
    });
  });

  it("explains a closed passkey prompt and other failures", async () => {
    let failure: Error = new PasskeyCancelled();
    vi.resetModules();
    vi.doMock("../src/passkeys", () => ({
      passkeysSupported: () => true,
      signInWithPasskey: () => Promise.reject(failure),
      PasskeyCancelled,
    }));
    const { default: Fresh } = await import("../src/views/SignInView.vue");
    const { mountWithApp: mountAgain } = await import("./helpers");
    const { wrapper } = await mountAgain(Fresh, "/sign-in", {}, { user: null });
    const click = async () => {
      await wrapper
        .findAll("button")
        .find((b) => b.text().includes("passkey"))
        ?.trigger("click");
      await flushPromises();
    };
    await click();
    expect(wrapper.get("[role=alert]").text()).toContain("closed");
    failure = new Error("boom");
    await click();
    expect(wrapper.get("[role=alert]").text()).toBe("Something went wrong. Try again.");
  });
});

describe("SetupView", () => {
  async function setup() {
    return mountWithApp(SetupView, "/setup", {}, { user: null, setupRequired: true });
  }

  const fields = {
    "input[autocomplete=off]": "BLND-AAAA-BBBB-CCCC",
    "input[autocomplete=username]": "ada",
    "input[autocomplete=name]": "Ada",
  };

  it("makes the administrator and goes to the overview", async () => {
    const { calls } = mockApi({ "POST /api/auth/setup": { json: admin } });
    const { wrapper, router, auth } = await setup();
    await fill(wrapper, fields);
    const passwords = wrapper.findAll("input[autocomplete=new-password]");
    await passwords[0]?.setValue(GOOD);
    await passwords[1]?.setValue(GOOD);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(calls[0]?.body).toEqual({
      setup_code: "BLND-AAAA-BBBB-CCCC",
      username: "ada",
      display_name: "Ada",
      password: GOOD,
    });
    expect(auth.user).toEqual(admin);
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe("/");
    });
  });

  it("checks the rules and the repeat before asking the API", async () => {
    const { fetchMock } = mockApi({});
    const { wrapper } = await setup();
    await fill(wrapper, fields);
    const passwords = wrapper.findAll("input[autocomplete=new-password]");
    await passwords[0]?.setValue("short");
    await passwords[1]?.setValue("short");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("password rules");
    await passwords[0]?.setValue(GOOD);
    await passwords[1]?.setValue("different");
    expect(wrapper.text()).toContain("The two passwords are different.");
    await wrapper.get("form").trigger("submit");
    expect(fetchMock).not.toHaveBeenCalled();
    await passwords[1]?.setValue("");
    expect(wrapper.text()).not.toContain("The two passwords are different.");
  });

  it("shows what the API refused", async () => {
    mockApi({
      "POST /api/auth/setup": {
        status: 403,
        json: { code: "setup_code_invalid", title: "That setup code is not right" },
      },
    });
    const { wrapper, router } = await setup();
    await fill(wrapper, fields);
    const passwords = wrapper.findAll("input[autocomplete=new-password]");
    await passwords[0]?.setValue(GOOD);
    await passwords[1]?.setValue(GOOD);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain("setup code is not right");
    expect(router.currentRoute.value.name).toBe("setup");
  });
});

describe("ForbiddenView", () => {
  it("says why and offers the way back", async () => {
    const { wrapper, router } = await mountWithApp(ForbiddenView, "/forbidden");
    expect(wrapper.get("h1").text()).toBe("No access");
    await wrapper.get("button").trigger("click");
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe("/");
    });
  });
});

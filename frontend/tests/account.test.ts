import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PasskeyCancelled } from "../src/passkeys";
import AccountView from "../src/views/AccountView.vue";
import ChangePasswordCard from "../src/views/account/ChangePasswordCard.vue";
import SessionsCard from "../src/views/account/SessionsCard.vue";
import { dialogButton, fillDialog, mockApi, mountWithApp, submitDialog, viewer } from "./helpers";

const GOOD = "violet harbour lantern 2026";
const passkey = {
  id: "p-1",
  name: "Laptop",
  created_at: "2026-11-01T10:00:00Z",
  last_used_at: null,
  backup_eligible: true,
  backed_up: false,
  transports: [],
};
const sessionRow = (id: string, current: boolean, agent: string | null = "Chrome/130 Linux") => ({
  id,
  created_at: "2026-11-20T10:00:00Z",
  last_seen_at: "2026-11-21T10:00:00Z",
  expires_at: "2026-11-22T10:00:00Z",
  ip_address: current ? "203.0.113.5" : null,
  user_agent: agent,
  current,
});

afterEach(() => {
  vi.doUnmock("../src/passkeys");
});

describe("AccountView", () => {
  it("shows who you are and the three cards", async () => {
    mockApi({
      "GET /api/auth/passkeys": { json: [] },
      "GET /api/auth/sessions": { json: [sessionRow("s-1", true)] },
    });
    const { wrapper } = await mountWithApp(AccountView, "/account");
    await flushPromises();
    expect(wrapper.get("h1").text()).toBe("Account");
    expect(wrapper.text()).toContain("Ada Admin");
    expect(wrapper.text()).toContain("admin");
    expect(wrapper.text()).not.toContain("can look, not change");
    expect(wrapper.text()).toContain("Change your password");
    expect(wrapper.text()).toContain("Where you are signed in");
  });

  it("tells a viewer what that means", async () => {
    mockApi({
      "GET /api/auth/passkeys": { json: [] },
      "GET /api/auth/sessions": { json: [] },
    });
    const { wrapper } = await mountWithApp(AccountView, "/account", {}, { user: viewer });
    await flushPromises();
    expect(wrapper.text()).toContain("can look, not change");
  });

  it("shows nothing when nobody is signed in", async () => {
    const { wrapper } = await mountWithApp(AccountView, "/sign-in", {}, { user: null });
    expect(wrapper.find(".v-row").exists()).toBe(false);
  });
});

describe("ChangePasswordCard", () => {
  async function card() {
    return mountWithApp(ChangePasswordCard);
  }
  async function fill(wrapper: Awaited<ReturnType<typeof card>>["wrapper"], again = GOOD) {
    await wrapper.get("input[autocomplete=current-password]").setValue("old password here");
    const fresh = wrapper.findAll("input[autocomplete=new-password]");
    await fresh[0]?.setValue(GOOD);
    await fresh[1]?.setValue(again);
  }

  it("changes the password and clears the form", async () => {
    const { calls } = mockApi({ "POST /api/auth/password": { status: 204 } });
    const { wrapper } = await card();
    await fill(wrapper);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(calls[0]?.body).toEqual({ current_password: "old password here", new_password: GOOD });
    expect(wrapper.get("[role=status]").text()).toContain("Password changed");
    expect(
      wrapper.get<HTMLInputElement>("input[autocomplete=current-password]").element.value,
    ).toBe("");
  });

  it("checks the rules and the repeat first", async () => {
    const { fetchMock } = mockApi({});
    const { wrapper } = await card();
    await fill(wrapper, "different");
    expect(wrapper.text()).toContain("The two passwords are different.");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.get("[role=alert]").text()).toContain("password rules");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a wrong current password", async () => {
    mockApi({
      "POST /api/auth/password": {
        status: 403,
        json: { code: "current_password_wrong", title: "The current password is wrong" },
      },
    });
    const { wrapper } = await card();
    await fill(wrapper);
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain("current password is wrong");
    expect(wrapper.find("[role=status]").exists()).toBe(false);
  });

  it("works without a signed-in user's name", async () => {
    const { wrapper } = await mountWithApp(ChangePasswordCard, "/sign-in", {}, { user: null });
    expect(wrapper.text()).toContain("At least 12 characters");
  });
});

describe("SessionsCard", () => {
  it("lists the browsers, marking this one, and ends another", async () => {
    mockApi({
      "GET /api/auth/sessions": {
        json: [sessionRow("s-1", true), sessionRow("s-2", false), sessionRow("s-3", false, null)],
      },
      "DELETE /api/auth/sessions/s-2": { status: 204 },
    });
    const { wrapper } = await mountWithApp(SessionsCard);
    await flushPromises();
    expect(wrapper.text()).toContain("This browser");
    expect(wrapper.text()).toContain("203.0.113.5");
    expect(wrapper.text()).toContain("Unknown address");
    expect(wrapper.text()).toContain("An unknown browser");
    await wrapper.get("button[aria-label='Sign out Chrome on Linux']").trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(2);
  });

  it("says when the list cannot be loaded and tries again", async () => {
    let fail = true;
    mockApi({
      "GET /api/auth/sessions": () =>
        fail ? { status: 500, json: { title: "Broke" } } : { json: [sessionRow("s-1", true)] },
    });
    const { wrapper } = await mountWithApp(SessionsCard);
    await flushPromises();
    expect(wrapper.text()).toContain("Could not load your sessions");
    expect(wrapper.text()).toContain("Broke");
    fail = false;
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("This browser");
  });

  it("shows why a session could not be ended", async () => {
    mockApi({
      "GET /api/auth/sessions": { json: [sessionRow("s-2", false)] },
      "DELETE /api/auth/sessions/s-2": { status: 404, json: { title: "There is no such session" } },
    });
    const { wrapper } = await mountWithApp(SessionsCard);
    await flushPromises();
    await wrapper.get("button[aria-label^='Sign out']").trigger("click");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toContain("no such session");
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
  });
});

describe("PasskeysCard", () => {
  async function card(
    supported = true,
    addPasskey: () => Promise<unknown> = () => Promise.resolve({}),
  ) {
    vi.resetModules();
    vi.doMock("../src/passkeys", () => ({
      passkeysSupported: () => supported,
      addPasskey,
      PasskeyCancelled,
    }));
    const { default: Fresh } = await import("../src/views/account/PasskeysCard.vue");
    const { mountWithApp: mountAgain } = await import("./helpers");
    const mounted = await mountAgain(Fresh);
    await flushPromises();
    return mounted;
  }

  it("lists the passkeys, and says so when there are none", async () => {
    mockApi({ "GET /api/auth/passkeys": { json: [passkey] } });
    const { wrapper } = await card();
    expect(wrapper.text()).toContain("Laptop");
    mockApi({ "GET /api/auth/passkeys": { json: [] } });
    const empty = await card();
    expect(empty.wrapper.text()).toContain("No passkeys yet");
  });

  it("explains a browser that cannot make passkeys, and hides the add button", async () => {
    mockApi({ "GET /api/auth/passkeys": { json: [passkey] } });
    const { wrapper } = await card(false);
    expect(wrapper.text()).toContain("cannot make passkeys");
    expect(wrapper.text()).not.toContain("Add a passkey");
  });

  it("says when the list cannot be loaded, and tries again", async () => {
    let fail = true;
    mockApi({
      "GET /api/auth/passkeys": () =>
        fail ? { status: 500, json: { title: "Broke" } } : { json: [] },
    });
    const { wrapper } = await card();
    expect(wrapper.text()).toContain("Could not load your passkeys");
    fail = false;
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Try again")
      ?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("No passkeys yet");
  });

  it("adds a passkey with a name and the password", async () => {
    const added = vi.fn(() => Promise.resolve(passkey));
    const { calls } = mockApi({ "GET /api/auth/passkeys": { json: [] } });
    const { wrapper } = await card(true, added);
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await flushPromises();
    await fillDialog({
      "input[maxlength='64']": "Phone",
      "input[autocomplete=current-password]": "pw",
    });
    await submitDialog();
    expect(added).toHaveBeenCalledWith("Phone", "pw");
    expect(calls.filter((c) => c.key === "GET /api/auth/passkeys")).toHaveLength(2);
  });

  it("shows a closed prompt and a refusal in the dialog", async () => {
    let failure: Error = new PasskeyCancelled();
    mockApi({ "GET /api/auth/passkeys": { json: [] } });
    const { wrapper } = await card(true, () => Promise.reject(failure));
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await flushPromises();
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain("closed");
    const { ApiError } = await import("../src/api/client");
    failure = new ApiError(403, "current_password_wrong", "The password is wrong");
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain(
      "The password is wrong",
    );
  });

  it("closes the dialog from Cancel without doing anything", async () => {
    const { fetchMock } = mockApi({ "GET /api/auth/passkeys": { json: [passkey] } });
    const { wrapper } = await card();
    await wrapper.get("button[aria-label='Remove Laptop']").trigger("click");
    await flushPromises();
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(dialogButton("Remove")?.closest(".v-overlay--active")).toBeNull();
  });

  it("renames a passkey", async () => {
    const { calls } = mockApi({
      "GET /api/auth/passkeys": { json: [passkey] },
      "PATCH /api/auth/passkeys/p-1": { json: { ...passkey, name: "Work" } },
    });
    const { wrapper } = await card();
    await wrapper.get("button[aria-label='Rename Laptop']").trigger("click");
    await flushPromises();
    expect(dialogButton("Rename")).toBeDefined();
    expect(document.body.querySelector(".v-dialog input[type=password]")).toBeNull();
    await fillDialog({ "input[maxlength='64']": "Work" });
    await submitDialog();
    expect(calls.find((c) => c.key.startsWith("PATCH"))?.body).toEqual({ name: "Work" });
  });

  it("removes a passkey after asking for the password", async () => {
    const { calls } = mockApi({
      "GET /api/auth/passkeys": { json: [passkey] },
      "DELETE /api/auth/passkeys/p-1": { status: 204 },
    });
    const { wrapper } = await card();
    await wrapper.get("button[aria-label='Remove Laptop']").trigger("click");
    await flushPromises();
    expect(document.body.querySelector(".v-dialog")?.textContent).toContain("Remove “Laptop”?");
    await fillDialog({ "input[autocomplete=current-password]": "pw" });
    await submitDialog();
    expect(calls.find((c) => c.key.startsWith("DELETE"))?.body).toEqual({ password: "pw" });
  });
});

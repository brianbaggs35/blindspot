import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { VSnackbar } from "vuetify/components";
import FormDialog from "../src/components/FormDialog.vue";
import StateView from "../src/components/StateView.vue";
import UsersView from "../src/views/UsersView.vue";
import {
  dialogButton,
  fillDialog,
  mockApi,
  mountWithApp,
  submitDialog,
  admin,
  viewer,
} from "./helpers";

const GOOD = "violet harbour lantern 2026";
const disabled = {
  ...viewer,
  id: "u-3",
  username: "dee",
  display_name: "",
  is_active: false,
  last_sign_in_at: null,
};

async function page(users = [admin, viewer, disabled], extra: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({ "GET /api/users": { json: users }, ...extra });
  const mounted = await mountWithApp(UsersView, "/users");
  await flushPromises();
  return { ...api, ...mounted };
}

function menuItem(label: string) {
  return Array.from(
    document.body.querySelectorAll<HTMLElement>(".v-overlay--active .v-list-item"),
  ).find((item) => item.textContent.trim() === label);
}

async function pick(
  wrapper: Awaited<ReturnType<typeof page>>["wrapper"],
  who: string,
  label: string,
) {
  await wrapper.get(`button[aria-label='Actions for ${who}']`).trigger("click");
  await flushPromises();
  menuItem(label)?.click();
  await flushPromises();
}

describe("UsersView", () => {
  it("lists everyone with their role and whether they can sign in", async () => {
    const { wrapper } = await page();
    expect(wrapper.get("h1").text()).toBe("Users");
    const rows = wrapper.findAll(".v-list-item");
    expect(rows).toHaveLength(3);
    expect(rows[0]?.text()).toContain("Ada Admin");
    expect(rows[0]?.text()).toContain("you");
    expect(rows[1]?.text()).toContain("viewer");
    expect(rows[2]?.text()).toContain("dee");
    expect(rows[2]?.text()).toContain("disabled");
    expect(rows[2]?.text()).toContain("—");
  });

  it("explains an empty list, and a failure with a retry", async () => {
    const empty = await page([]);
    expect(empty.wrapper.text()).toContain("Add the first user");
    const failing = mockApi({ "GET /api/users": { status: 500, json: { title: "Down" } } });
    const { wrapper } = await mountWithApp(UsersView, "/users");
    await flushPromises();
    expect(wrapper.text()).toContain("Could not load the users");
    expect(wrapper.text()).toContain("Down");
    failing.fetchMock.mockClear();
  });

  it("drops a list that arrives after a newer one", async () => {
    const answers: ((value: Response) => void)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => answers.push(resolve))),
    );
    const { wrapper } = await mountWithApp(UsersView, "/users");
    const retry = wrapper.getComponent(StateView);
    retry.vm.$emit("action");
    await flushPromises();
    const reply = (rows: object[]) =>
      new Response(JSON.stringify(rows), { headers: { "Content-Type": "application/json" } });
    answers[1]?.(reply([admin]));
    await flushPromises();
    answers[0]?.(reply([admin, viewer]));
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
  });

  it("ignores a failure that arrives after a newer list", async () => {
    const pending: { resolve: (value: Response) => void; reject: (error: Error) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve, reject) => pending.push({ resolve, reject }))),
    );
    const { wrapper } = await mountWithApp(UsersView, "/users");
    wrapper.getComponent(StateView).vm.$emit("action");
    await flushPromises();
    pending[1]?.resolve(
      new Response(JSON.stringify([admin]), { headers: { "Content-Type": "application/json" } }),
    );
    await flushPromises();
    pending[0]?.reject(new Error("late failure"));
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("late failure");
  });

  it("adds a user", async () => {
    const { wrapper, calls } = await page([admin], {
      "POST /api/users": { status: 201, json: viewer },
    });
    const add = wrapper.findAll("button").find((button) => button.text() === "Add a user");
    await add?.trigger("click");
    await flushPromises();
    await fillDialog({
      "input[autocomplete=off]": "vic",
      "input[type=password]": GOOD,
    });
    await submitDialog();
    expect(calls.find((call) => call.key === "POST /api/users")?.body).toEqual({
      username: "vic",
      display_name: "",
      role: "viewer",
      password: GOOD,
    });
    expect(document.body.textContent).toContain("Added vic.");
    wrapper.getComponent(VSnackbar).vm.$emit("update:modelValue", false);
    await flushPromises();
    expect(calls.filter((call) => call.key === "GET /api/users")).toHaveLength(2);
  });

  it("will not submit a new user whose password breaks the rules, and shows the API's refusal", async () => {
    const { wrapper, calls } = await page([admin], {
      "POST /api/users": { status: 409, json: { title: "That username is already used" } },
    });
    const add = wrapper.findAll("button").find((button) => button.text() === "Add a user");
    await add?.trigger("click");
    await flushPromises();
    await fillDialog({ "input[autocomplete=off]": "vic", "input[type=password]": "short" });
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain(
      "Check the password rules",
    );
    expect(calls.some((call) => call.key === "POST /api/users")).toBe(false);
    await fillDialog({ "input[type=password]": GOOD });
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain(
      "already used",
    );
  });

  it("edits someone else's role and status", async () => {
    const { wrapper, calls } = await page([admin, viewer], {
      [`PATCH /api/users/${viewer.id}`]: { json: { ...viewer, role: "admin" } },
    });
    await pick(wrapper, "vic", "Edit");
    await fillDialog({ "input[autocomplete=off]": "Victor" });
    const form = wrapper.findComponent({ name: "UserFormDialog" });
    await form.findComponent({ name: "VSelect" }).setValue("admin");
    await form.findComponent({ name: "VSwitch" }).setValue(false);
    await submitDialog();
    expect(calls.find((call) => call.key.startsWith("PATCH"))?.body).toEqual({
      display_name: "Victor",
      role: "admin",
      is_active: false,
    });
    expect(document.body.textContent).toContain("Saved vic.");
  });

  it("only lets you change your own name", async () => {
    const { wrapper, calls } = await page([admin, viewer], {
      [`PATCH /api/users/${admin.id}`]: { json: admin },
    });
    await pick(wrapper, "ada", "Edit");
    expect(document.body.textContent).toContain("You cannot change your own role.");
    expect(document.body.textContent).toContain("You cannot disable your own account.");
    await submitDialog();
    expect(calls.find((call) => call.key.startsWith("PATCH"))?.body).toEqual({
      display_name: "Ada Admin",
    });
  });

  it("shows a refusal from the API when saving", async () => {
    const { wrapper } = await page([admin, viewer], {
      [`PATCH /api/users/${viewer.id}`]: { status: 409, json: { title: "Not allowed" } },
    });
    await pick(wrapper, "vic", "Edit");
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain(
      "Not allowed",
    );
  });

  it("resets a password, checking the rules first", async () => {
    const { wrapper, calls } = await page([admin, viewer], {
      [`POST /api/users/${viewer.id}/password`]: { status: 204 },
    });
    await pick(wrapper, "vic", "Reset password");
    await fillDialog({ "input[type=password]": "short" });
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain(
      "Check the password rules",
    );
    await fillDialog({ "input[type=password]": GOOD });
    await submitDialog();
    expect(calls.find((call) => call.key.endsWith("/password"))?.body).toEqual({ password: GOOD });
    expect(document.body.textContent).toContain("vic was signed out everywhere");
  });

  it("shows a refusal when a reset fails", async () => {
    const { wrapper } = await page([admin, viewer], {
      [`POST /api/users/${viewer.id}/password`]: { status: 422, json: { title: "Too common" } },
    });
    await pick(wrapper, "vic", "Reset password");
    await fillDialog({ "input[type=password]": GOOD });
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain(
      "Too common",
    );
  });

  it("signs someone out everywhere after asking", async () => {
    const { wrapper, calls } = await page([admin, viewer], {
      [`POST /api/users/${viewer.id}/sign-out`]: { status: 204 },
    });
    await pick(wrapper, "vic", "Sign out everywhere");
    expect(document.body.textContent).toContain("Sign vic out everywhere?");
    await submitDialog();
    expect(calls.some((call) => call.key.endsWith("/sign-out"))).toBe(true);
    expect(document.body.textContent).toContain("vic was signed out everywhere.");
    expect(calls.filter((call) => call.key === "GET /api/users")).toHaveLength(1);
  });

  it("deletes after asking", async () => {
    const { wrapper, calls } = await page([admin, viewer], {
      [`DELETE /api/users/${viewer.id}`]: { status: 204 },
    });
    await pick(wrapper, "vic", "Delete");
    expect(document.body.textContent).toContain("Delete vic?");
    await submitDialog();
    expect(calls.some((call) => call.key === `DELETE /api/users/${viewer.id}`)).toBe(true);
    expect(document.body.textContent).toContain("Deleted vic.");
    expect(calls.filter((call) => call.key === "GET /api/users")).toHaveLength(2);
  });

  it("closes the form and the reset dialog from Cancel without sending anything", async () => {
    const { wrapper, calls } = await page([admin, viewer]);
    await pick(wrapper, "vic", "Edit");
    dialogButton("Cancel")?.click();
    await flushPromises();
    await pick(wrapper, "vic", "Reset password");
    dialogButton("Cancel")?.click();
    await flushPromises();
    for (const name of ["UserFormDialog", "ResetPasswordDialog"]) {
      wrapper.getComponent({ name }).getComponent(FormDialog).vm.$emit("update:modelValue", false);
    }
    await flushPromises();
    expect(calls.map((call) => call.key)).toEqual(["GET /api/users"]);
  });

  it("does nothing when a dialog is submitted with nothing chosen", async () => {
    const { wrapper, calls } = await page([admin, viewer]);
    for (const name of ["UserFormDialog", "ResetPasswordDialog"]) {
      expect(wrapper.findComponent({ name }).exists()).toBe(true);
    }
    wrapper.findAllComponents(FormDialog).at(-1)?.vm.$emit("submit");
    await flushPromises();
    wrapper.findAllComponents(FormDialog).at(-2)?.vm.$emit("submit");
    await flushPromises();
    expect(calls.map((call) => call.key)).toEqual(["GET /api/users"]);
  });

  it("does not offer to delete your own account", async () => {
    const { wrapper } = await page([admin, viewer]);
    await wrapper.get("button[aria-label='Actions for ada']").trigger("click");
    await flushPromises();
    expect(menuItem("Delete")?.classList.contains("v-list-item--disabled")).toBe(true);
  });

  it("shows the API's refusal in the confirmation and can be cancelled", async () => {
    const { wrapper, calls } = await page([admin, viewer], {
      [`DELETE /api/users/${viewer.id}`]: { status: 409, json: { title: "Cannot delete" } },
    });
    await pick(wrapper, "vic", "Delete");
    await submitDialog();
    expect(document.body.querySelector(".v-dialog [role=alert]")?.textContent).toContain(
      "Cannot delete",
    );
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(calls.filter((call) => call.key.startsWith("DELETE"))).toHaveLength(1);
  });
});

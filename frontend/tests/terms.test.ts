import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { Terms } from "../src/api/types";
import TermsView from "../src/views/TermsView.vue";
import { admin, mockApi, mountWithApp } from "./helpers";
import { emitFrom } from "./pentest-fixtures";

const waiting = { ...admin, terms_accepted: false };

const terms: Terms = {
  title: "Terms of use",
  version: "abc123",
  accepted: false,
  accepted_at: null,
  sections: [
    { id: "permission", title: "Test only what you may", paragraphs: ["First.", "Second."] },
    { id: "liability", title: "No liability", paragraphs: ["Third."] },
  ],
};

type Handlers = Parameters<typeof mockApi>[0];

async function page(handlers: Handlers = {}, path = "/terms?next=/pentests") {
  const api = mockApi({ "GET /api/terms": { json: terms }, ...handlers });
  const mounted = await mountWithApp(TermsView, path, {}, { user: waiting });
  await flushPromises();
  return { ...api, ...mounted };
}

describe("TermsView", () => {
  it("shows the words, the version and a warning, and waits for the person to agree", async () => {
    const { wrapper } = await page();
    const text = wrapper.text();
    expect(text).toContain("Test only what you may");
    expect(text).toContain("Second.");
    expect(text).toContain("No liability");
    expect(text).toContain("Version abc123");
    expect(text).toContain("written permission");
    expect(wrapper.get("[role=status]").text()).toContain("real attacks");
    const accept = wrapper.findAll("button").find((one) => one.text() === "Accept and continue");
    expect(accept?.attributes("disabled")).toBeDefined();
  });

  it("accepts the version that was read and goes on to where the person was heading", async () => {
    const { wrapper, calls, router, auth } = await page({
      "POST /api/terms/accept": { json: { ...terms, accepted: true } },
    });
    emitFrom(wrapper.getComponent({ name: "VCheckbox" }), "update:modelValue", true);
    await flushPromises();
    const accept = wrapper.findAll("button").find((one) => one.text() === "Accept and continue");
    await accept?.trigger("click");
    await flushPromises();
    expect(calls.find((call) => call.key === "POST /api/terms/accept")?.body).toEqual({
      version: "abc123",
    });
    expect(auth.termsAccepted).toBe(true);
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe("/pentests");
    });
  });

  it("shows the new words when they changed while the person was reading", async () => {
    let current: Terms = terms;
    const { wrapper } = await page({
      "GET /api/terms": () => ({ json: current }),
      "POST /api/terms/accept": {
        status: 409,
        json: { code: "terms_changed", title: "The terms changed while you were reading them" },
      },
    });
    current = { ...terms, version: "def456" };
    emitFrom(wrapper.getComponent({ name: "VCheckbox" }), "update:modelValue", true);
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((one) => one.text() === "Accept and continue")
      ?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("The terms changed");
    expect(wrapper.text()).toContain("Version def456");
    const again = wrapper.findAll("button").find((one) => one.text() === "Accept and continue");
    expect(again?.attributes("disabled")).toBeDefined();
  });

  it("says when the terms cannot be loaded, and tries again", async () => {
    let failing = true;
    const { wrapper } = await page({
      "GET /api/terms": () =>
        failing ? { status: 500, json: { code: "boom", title: "Away" } } : { json: terms },
    });
    expect(wrapper.text()).toContain("Could not load the terms");
    expect(wrapper.text()).toContain("Away");
    failing = false;
    await wrapper.get(".bs-state button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Test only what you may");
  });

  it("offers nothing to accept before the words arrived", async () => {
    const { wrapper } = await page({
      "GET /api/terms": { status: 500, json: { code: "boom", title: "Away" } },
    });
    expect(wrapper.findAll("button").some((one) => one.text() === "Accept and continue")).toBe(
      false,
    );
  });

  it("lets the person sign out instead", async () => {
    const { wrapper, router, auth } = await page({ "POST /api/auth/logout": { status: 204 } });
    await wrapper
      .findAll("button")
      .find((one) => one.text() === "Sign out")
      ?.trigger("click");
    await flushPromises();
    expect(auth.user).toBeNull();
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe("sign-in");
    });
  });
});

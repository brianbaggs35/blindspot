import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VSnackbar } from "vuetify/components";
import {
  CHECK_CHOICES,
  CHECK_COLORS,
  CHECK_HINTS,
  CHECK_LABELS,
  STATUS_ORDER,
  categoryFinished,
  finished,
  isFiltering,
  matching,
  percent,
} from "../src/checklist";
import PentestChecklistView from "../src/views/PentestChecklistView.vue";
import CheckDialog from "../src/views/checklist/CheckDialog.vue";
import CustomTestDialog from "../src/views/checklist/CustomTestDialog.vue";
import FeaturesCard from "../src/views/checklist/FeaturesCard.vue";
import ChecklistCard from "../src/views/pentests/ChecklistCard.vue";
import {
  alertText,
  checklistOf,
  emitFrom,
  fieldNamed,
  finding,
  item,
  own,
  pentest,
  saml,
} from "./pentest-fixtures";
import { dialogButton, mockApi, mountWithApp, submitDialog, viewer } from "./helpers";

type Handlers = Parameters<typeof mockApi>[0];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("checklist helpers", () => {
  it("has one set of words for each state, in order", () => {
    expect(STATUS_ORDER).toEqual([
      "todo",
      "in_progress",
      "passed",
      "finding",
      "blocked",
      "not_applicable",
    ]);
    expect(CHECK_LABELS.in_progress).toBe("In progress");
    expect(CHECK_HINTS.finding).toBe("Done, and a weakness was found");
    expect(CHECK_COLORS.passed).toBe("success");
    expect(CHECK_CHOICES.map((one) => one.value)).toEqual([...STATUS_ORDER]);
    expect(CHECK_CHOICES[0]).toEqual({
      value: "todo",
      title: "To do",
      subtitle: "Nobody has started",
    });
  });

  it("counts what is finished and says it in whole percent", () => {
    const counts = {
      todo: 5,
      in_progress: 1,
      passed: 2,
      finding: 1,
      blocked: 1,
      not_applicable: 3,
    };
    expect(finished(counts)).toBe(6);
    expect(percent(6, 13)).toBe(46);
    expect(percent(0, 0)).toBe(100);
    expect(percent(13, 13)).toBe(100);
    expect(categoryFinished({ id: "X", name: "X", tests: [item(), finding, saml, own] })).toBe(2);
  });

  it("filters by words, state and whether the test applies", () => {
    const tests = [item(), finding, saml, own];
    const none = { text: "", status: null, appliesOnly: false } as const;
    expect(matching(tests, none)).toHaveLength(4);
    expect(matching(tests, { ...none, text: "  " })).toHaveLength(4);
    expect(matching(tests, { ...none, text: "INFO-02" }).map((one) => one.test_id)).toEqual([
      "WSTG-INFO-02",
    ]);
    expect(matching(tests, { ...none, text: "banner modules" })).toEqual([finding]);
    expect(matching(tests, { ...none, text: "cache" })).toEqual([own]);
    expect(matching(tests, { ...none, status: "finding" })).toEqual([finding]);
    expect(matching(tests, { ...none, appliesOnly: true })).toEqual([item(), finding, own]);
    expect(matching(tests, { ...none, text: "banner", status: "todo" })).toEqual([]);
  });

  it("knows when anything is filtering", () => {
    expect(isFiltering({ text: "", status: null, appliesOnly: false })).toBe(false);
    expect(isFiltering({ text: " ", status: null, appliesOnly: false })).toBe(false);
    expect(isFiltering({ text: "a", status: null, appliesOnly: false })).toBe(true);
    expect(isFiltering({ text: "", status: "todo", appliesOnly: false })).toBe(true);
    expect(isFiltering({ text: "", status: null, appliesOnly: true })).toBe(true);
  });
});

describe("ChecklistCard", () => {
  async function card(handlers: Handlers = {}) {
    const api = mockApi({
      "GET /api/pentests/p-1/checklist": { json: checklistOf() },
      ...handlers,
    });
    const mounted = await mountWithApp(ChecklistCard, "/pentests/p-1", { pentestId: "p-1" });
    await flushPromises();
    return { ...api, ...mounted };
  }

  it("shows how far the work has got and the way in", async () => {
    const { wrapper } = await card();
    const text = wrapper.text();
    expect(text).toContain("2 of 4 tests finished");
    expect(text).toContain("To do: 1");
    expect(text).toContain("In progress: 1");
    expect(text).toContain("Finding: 1");
    expect(text).toContain("Not applicable: 1");
    expect(wrapper.get("a[href='/pentests/p-1/checklist']").text()).toContain("Open the checklist");
    expect(wrapper.get("[aria-label='Tests finished']").attributes("aria-valuenow")).toBe("50");
  });

  it("says why the progress is missing and still offers the checklist", async () => {
    const { wrapper } = await card({
      "GET /api/pentests/p-1/checklist": { status: 500, json: { code: "boom", title: "Away" } },
    });
    expect(wrapper.text()).toContain("Could not load the progress: Away");
    expect(wrapper.find("a[href='/pentests/p-1/checklist']").exists()).toBe(true);
  });

  it("reads again for another pentest and forgets an earlier failure", async () => {
    let failing = true;
    const { wrapper, calls } = await card({
      "GET /api/pentests/p-1/checklist": () =>
        failing ? { status: 500, json: { code: "boom", title: "Away" } } : { json: checklistOf() },
      "GET /api/pentests/p-2/checklist": () => ({ json: checklistOf() }),
    });
    expect(wrapper.text()).toContain("Away");
    failing = false;
    await wrapper.setProps({ pentestId: "p-2" });
    await flushPromises();
    expect(calls.some((call) => call.key === "GET /api/pentests/p-2/checklist")).toBe(true);
    expect(wrapper.text()).not.toContain("Away");
    expect(wrapper.text()).toContain("2 of 4 tests finished");
  });

  async function late(first: () => Promise<Response>) {
    mockApi({ "GET /api/pentests/p-2/checklist": { json: checklistOf({ total: 9 }) } });
    const original = globalThis.fetch;
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal("fetch", (input: string, init?: RequestInit) =>
      input.includes("/p-1/") ? slow.then(first) : original(input, init),
    );
    const { wrapper } = await mountWithApp(ChecklistCard, "/", { pentestId: "p-1" });
    await wrapper.setProps({ pentestId: "p-2" });
    await flushPromises();
    release();
    await flushPromises();
    return wrapper;
  }

  it("ignores a late answer for a pentest that was left", async () => {
    const wrapper = await late(() =>
      Promise.resolve(new Response(JSON.stringify(checklistOf({ total: 1 })))),
    );
    expect(wrapper.text()).toContain("of 9 tests finished");
  });

  it("ignores a late failure for a pentest that was left", async () => {
    const wrapper = await late(() => Promise.reject(new Error("late")));
    expect(wrapper.text()).toContain("of 9 tests finished");
    expect(wrapper.text()).not.toContain("Could not load");
  });
});

async function page(
  handlers: Handlers = {},
  { made = pentest(), user = undefined as typeof viewer | undefined } = {},
) {
  const api = mockApi({
    "GET /api/pentests/p-1/checklist": { json: checklistOf() },
    "GET /api/pentests/p-1": { json: made },
    ...handlers,
  });
  const mounted = await mountWithApp(
    PentestChecklistView,
    "/pentests/p-1/checklist",
    {},
    user ? { user } : {},
  );
  await flushPromises();
  return { ...api, ...mounted };
}

async function openPanels(wrapper: Awaited<ReturnType<typeof page>>["wrapper"]) {
  for (const title of wrapper.findAll(".v-expansion-panel-title")) {
    if (title.attributes("aria-expanded") !== "true") await title.trigger("click");
  }
  await flushPromises();
}

function press(wrapper: Awaited<ReturnType<typeof page>>["wrapper"], label: string) {
  const found = wrapper.findAll("button").find((one) => one.text() === label);
  if (found === undefined) throw new Error(`no ${label} button`);
  return found.trigger("click");
}

describe("PentestChecklistView", () => {
  it("shows the progress, the states and each category", async () => {
    const { wrapper } = await page();
    expect(wrapper.get("h1").text()).toBe("Checklist: Acme storefront");
    const text = wrapper.text();
    expect(text).toContain("OWASP Web Security Testing Guide · snapshot 1");
    expect(text).toContain("2 of 4 tests finished (50%)");
    expect(text).toContain("Finding: 1");
    expect(text).toContain("Showing 4 of 4 tests.");
    expect(text).toContain("Information Gathering");
    expect(text).toContain("1 of 2 finished");
    expect(text).toContain("Authentication");
    expect(text).toContain("Custom");
    expect(wrapper.get("a[href='/pentests/p-1']").text()).toContain("Back to the pentest");
  });

  it("lists the tests of a category with their risk and state", async () => {
    const { wrapper } = await page();
    await openPanels(wrapper);
    const text = wrapper.text();
    expect(text).toContain("Search engine discovery");
    expect(text).toContain("Safe");
    expect(text).toContain("Active");
    expect(text).toContain("Intrusive");
    expect(text).toContain("Your own test");
    expect(text).toContain("WSTG-INFO-01");
    expect(wrapper.get("[aria-label='WSTG-INFO-02 Fingerprint the web server']").text()).toContain(
      "Finding",
    );
  });

  it("narrows by search, opening the categories that have a match", async () => {
    const { wrapper } = await page();
    await fieldNamed(wrapper, "VTextField", "Search tests, ids and notes").setValue("banner");
    await flushPromises();
    expect(wrapper.text()).toContain("Showing 1 of 4 tests.");
    expect(wrapper.text()).not.toContain("Authentication");
    expect(wrapper.text()).toContain("Clear the search and filters to see every test.");
    expect(wrapper.get(".v-expansion-panel-title").attributes("aria-expanded")).toBe("true");
    await fieldNamed(wrapper, "VTextField", "Search tests, ids and notes").setValue("");
    await flushPromises();
    expect(wrapper.text()).toContain("Showing 4 of 4 tests.");
    expect(wrapper.get(".v-expansion-panel-title").attributes("aria-expanded")).toBe("false");
    await fieldNamed(wrapper, "VTextField", "Search tests, ids and notes").setValue("zzz");
    await flushPromises();
    expect(wrapper.text()).toContain("No test matches that.");
    expect(wrapper.text()).not.toContain("Clear the search and filters");
  });

  it("narrows by state with the chips, from the mouse and the keyboard", async () => {
    const { wrapper } = await page();
    const chips = () => wrapper.findAll("[role=group][aria-label='Filter by state'] .v-chip");
    expect(chips()).toHaveLength(6);
    await chips()[3]?.trigger("click");
    expect(wrapper.text()).toContain("Showing 1 of 4 tests.");
    expect(chips()[3]?.attributes("aria-pressed")).toBe("true");
    await chips()[3]?.trigger("click");
    expect(wrapper.text()).toContain("Showing 4 of 4 tests.");
    await chips()[0]?.trigger("keydown", { key: "Enter" });
    expect(wrapper.text()).toContain("Showing 1 of 4 tests.");
    await chips()[0]?.trigger("keydown", { key: " " });
    expect(wrapper.text()).toContain("Showing 4 of 4 tests.");
  });

  it("can show only the tests that apply", async () => {
    const { wrapper } = await page();
    emitFrom(wrapper.getComponent({ name: "VSwitch" }), "update:modelValue", true);
    await flushPromises();
    expect(wrapper.text()).toContain("Showing 3 of 4 tests.");
    expect(wrapper.text()).not.toContain("Authentication");
  });

  it("opens a test, saves it and reads the list again", async () => {
    const { wrapper, calls } = await page({
      "PUT /api/pentests/p-1/checklist/WSTG-INFO-01": { json: item({ status: "passed" }) },
    });
    await openPanels(wrapper);
    await wrapper.get("[aria-label='WSTG-INFO-01 Search engine discovery']").trigger("click");
    await flushPromises();
    expect(document.body.textContent).toContain("Search engine discovery");
    emitFrom(fieldNamed(wrapper, "VSelect", "Where it stands"), "update:modelValue", "passed");
    await submitDialog();
    const put = calls.find((call) => call.key === "PUT /api/pentests/p-1/checklist/WSTG-INFO-01");
    expect(put?.body).toMatchObject({ status: "passed" });
    expect(document.body.textContent).toContain("Saved.");
    expect(calls.filter((call) => call.key === "GET /api/pentests/p-1/checklist")).toHaveLength(2);
  });

  it("saves the features the target shows", async () => {
    const { wrapper, calls } = await page({
      "PATCH /api/pentests/p-1": { json: pentest({ features: ["saml"] }) },
    });
    const form = wrapper.findAll("form").find((one) => one.text().includes("Save features"));
    emitFrom(fieldNamed(wrapper, "VCombobox", "Features"), "update:modelValue", ["SAML"]);
    await flushPromises();
    await form?.trigger("submit");
    await flushPromises();
    expect(calls.find((call) => call.key === "PATCH /api/pentests/p-1")?.body).toEqual({
      features: ["saml"],
    });
    expect(document.body.textContent).toContain("Features saved.");
  });

  it("offers the features its tests ask for", async () => {
    const { wrapper } = await page();
    expect(fieldNamed(wrapper, "VCombobox", "Features").props("items")).toEqual(["saml"]);
  });

  it("adds a test of your own", async () => {
    const { wrapper, calls } = await page({
      "POST /api/pentests/p-1/checklist/custom": { status: 201, json: own },
    });
    await press(wrapper, "Add a test");
    await flushPromises();
    await fieldNamed(wrapper, "VTextField", "Name").setValue("Check the CDN");
    await submitDialog();
    expect(
      calls.find((call) => call.key === "POST /api/pentests/p-1/checklist/custom")?.body,
    ).toEqual({ name: "Check the CDN", category: "Custom", notes: "" });
    expect(document.body.textContent).toContain("Test added.");
  });

  it("shows a viewer everything and lets them change nothing", async () => {
    const { wrapper } = await page({}, { user: viewer });
    expect(wrapper.findAll("button").map((one) => one.text())).not.toContain("Add a test");
    expect(wrapper.text()).toContain("None named.");
    expect(wrapper.text()).not.toContain("Save features");
    await openPanels(wrapper);
    await wrapper.get("[aria-label='WSTG-INFO-02 Fingerprint the web server']").trigger("click");
    await flushPromises();
    expect(document.body.textContent).toContain("The banner names the version");
    expect(dialogButton("Save")).toBeUndefined();
  });

  it("reads a pentest that is archived or in the trash but changes nothing", async () => {
    for (const [changes, words] of [
      [{ archived_at: "2026-11-23T12:00:00Z" }, "archived"],
      [{ deleted_at: "2026-11-23T12:00:00Z" }, "in the trash"],
    ] as const) {
      const { wrapper } = await page({}, { made: pentest(changes) });
      expect(wrapper.text()).toContain(`This pentest is ${words}`);
      expect(wrapper.findAll("button").map((one) => one.text())).not.toContain("Add a test");
      wrapper.unmount();
    }
  });

  it("says when it cannot be loaded, and tries again", async () => {
    let failing = true;
    const { wrapper } = await page({
      "GET /api/pentests/p-1/checklist": () =>
        failing
          ? { status: 500, json: { code: "boom", title: "The database is away" } }
          : { json: checklistOf() },
    });
    expect(wrapper.text()).toContain("Could not load the checklist");
    expect(wrapper.text()).toContain("The database is away");
    failing = false;
    await wrapper.get(".bs-state button").trigger("click");
    await flushPromises();
    expect(wrapper.get("h1").text()).toBe("Checklist: Acme storefront");
  });

  async function late(first: () => Promise<Response>) {
    mockApi({
      "GET /api/pentests/p-2": { json: pentest({ id: "p-2", name: "Second" }) },
      "GET /api/pentests/p-2/checklist": { json: checklistOf() },
    });
    const original = globalThis.fetch;
    let release: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal("fetch", (input: string, init?: RequestInit) =>
      input.includes("/p-1") ? slow.then(first) : original(input, init),
    );
    const { wrapper, router } = await mountWithApp(PentestChecklistView, "/pentests/p-1/checklist");
    await router.push("/pentests/p-2/checklist");
    await flushPromises();
    release();
    await flushPromises();
    return wrapper;
  }

  it("ignores a late answer for a pentest that was left", async () => {
    const wrapper = await late(() => Promise.resolve(new Response(JSON.stringify(pentest()))));
    expect(wrapper.get("h1").text()).toBe("Checklist: Second");
  });

  it("ignores a late failure for a pentest that was left", async () => {
    const wrapper = await late(() => Promise.reject(new Error("late")));
    expect(wrapper.get("h1").text()).toBe("Checklist: Second");
  });

  it("closes its notice", async () => {
    const { wrapper } = await page({
      "PATCH /api/pentests/p-1": { json: pentest() },
    });
    const form = wrapper.findAll("form").find((one) => one.text().includes("Save features"));
    await form?.trigger("submit");
    await flushPromises();
    const bar = wrapper.getComponent(VSnackbar);
    expect(bar.props("modelValue")).toBe(true);
    emitFrom(bar, "update:modelValue", false);
    await flushPromises();
    expect(bar.props("modelValue")).toBe(false);
  });
});

async function dialog(props: object, handlers: Handlers = {}) {
  const api = mockApi(handlers);
  const mounted = await mountWithApp(CheckDialog, "/pentests/p-1/checklist", {
    modelValue: true,
    pentestId: "p-1",
    editable: true,
    ...props,
  });
  await flushPromises();
  return { ...api, ...mounted };
}

describe("CheckDialog", () => {
  const PATH = "PUT /api/pentests/p-1/checklist/WSTG-INFO-02";

  it("starts from the test and sends what was changed, without the empty links", async () => {
    const { wrapper, calls } = await dialog({ item: finding }, { [PATH]: { json: finding } });
    expect(document.body.textContent).toContain("Fingerprint the web server");
    expect(fieldNamed(wrapper, "VTextarea", "Notes").props("modelValue")).toContain("banner");
    expect(fieldNamed(wrapper, "VTextField", "Link 1 label").props("modelValue")).toBe("Response");
    await fieldNamed(wrapper, "VTextarea", "Notes").setValue("Changed");
    await press(wrapper, "Add a link");
    await flushPromises();
    await fieldNamed(wrapper, "VTextField", "Link 2 label").setValue("  Screenshot ");
    await fieldNamed(wrapper, "VTextField", "Link 2 address").setValue(" https://x.example.com/a ");
    await press(wrapper, "Add a link");
    await flushPromises();
    expect(fieldNamed(wrapper, "VTextField", "Link 3 label").props("modelValue")).toBe("");
    await submitDialog();
    expect(calls.find((call) => call.key === PATH)?.body).toEqual({
      status: "finding",
      notes: "Changed",
      evidence: [
        { label: "Response", url: "https://evidence.example.com/info-02" },
        { label: "Screenshot", url: "https://x.example.com/a" },
      ],
    });
    expect(wrapper.emitted("saved")?.[0]).toEqual(["Saved."]);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("removes a link", async () => {
    const { calls } = await dialog({ item: finding }, { [PATH]: { json: finding } });
    document.body.querySelector<HTMLButtonElement>("button[aria-label='Remove link 1']")?.click();
    await flushPromises();
    await submitDialog();
    expect(calls.find((call) => call.key === PATH)?.body).toMatchObject({ evidence: [] });
  });

  it("says what is wrong and keeps what was typed", async () => {
    const { wrapper } = await dialog(
      { item: finding },
      {
        [PATH]: { status: 422, json: { code: "bad", title: "That address is not a web address" } },
      },
    );
    await submitDialog();
    expect(alertText()).toContain("That address is not a web address");
    expect(wrapper.emitted("saved")).toBeUndefined();
  });

  it("names the feature a test needs when the target lacks it, and links the guide", async () => {
    await dialog({ item: saml });
    expect(document.body.textContent).toContain("needs a feature the target does not show: saml");
    expect(document.body.querySelector(".v-dialog a")).toBeNull();
    wrapperCleanup();
  });

  it("links the guide when there is one", async () => {
    await dialog({ item: item() });
    expect(document.body.querySelector(".v-dialog a")?.getAttribute("href")).toBe(
      "https://owasp.org/wstg/info-01",
    );
  });

  it("changes a custom test's name and category", async () => {
    const { wrapper, calls } = await dialog(
      { item: own },
      { "PUT /api/pentests/p-1/checklist/CUSTOM-AB12CD34": { json: own } },
    );
    await fieldNamed(wrapper, "VTextField", "Name").setValue("  Check the CDN again ");
    await fieldNamed(wrapper, "VTextField", "Move to another category").setValue(" Edge ");
    await submitDialog();
    expect(
      calls.find((call) => call.key === "PUT /api/pentests/p-1/checklist/CUSTOM-AB12CD34")?.body,
    ).toMatchObject({ name: "Check the CDN again", category: "Edge" });
  });

  it("keeps a custom test where it is when no category is typed", async () => {
    const { calls } = await dialog(
      { item: own },
      { "PUT /api/pentests/p-1/checklist/CUSTOM-AB12CD34": { json: own } },
    );
    await submitDialog();
    const body = calls.find(
      (call) => call.key === "PUT /api/pentests/p-1/checklist/CUSTOM-AB12CD34",
    )?.body as Record<string, unknown>;
    expect(body["name"]).toBe("Check the CDN");
    expect(body).not.toHaveProperty("category");
  });

  it("puts a methodology test back as untouched after asking", async () => {
    const { wrapper, calls } = await dialog(
      { item: finding },
      { "DELETE /api/pentests/p-1/checklist/WSTG-INFO-02": { status: 204 } },
    );
    await press(wrapper, "Put back as untouched");
    expect(document.body.textContent).toContain("Its state, notes and evidence links are cleared.");
    dialogButton("Put back")?.click();
    await flushPromises();
    expect(
      calls.some((call) => call.key === "DELETE /api/pentests/p-1/checklist/WSTG-INFO-02"),
    ).toBe(true);
    expect(wrapper.emitted("saved")?.[0]).toEqual(["Put back as untouched."]);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("removes a custom test after asking", async () => {
    const { wrapper } = await dialog(
      { item: own },
      { "DELETE /api/pentests/p-1/checklist/CUSTOM-AB12CD34": { status: 204 } },
    );
    await press(wrapper, "Remove this test");
    expect(document.body.textContent).toContain(
      "The test, its notes and its evidence links are deleted.",
    );
    dialogButton("Remove")?.click();
    await flushPromises();
    expect(wrapper.emitted("saved")?.[0]).toEqual(["Test removed."]);
  });

  it("offers no reset for a test nobody has touched", async () => {
    const { wrapper } = await dialog({ item: item() });
    expect(wrapper.findAll("button").map((one) => one.text())).not.toContain(
      "Put back as untouched",
    );
    expect(document.body.textContent).not.toContain("Put back as untouched");
  });

  it("shows a viewer the same things as text", async () => {
    const { wrapper } = await dialog({ item: finding, editable: false });
    const text = document.body.textContent;
    expect(text).toContain("Finding");
    expect(text).toContain("The banner names the version");
    expect(
      document.body.querySelector(".v-dialog a[href='https://evidence.example.com/info-02']"),
    ).not.toBeNull();
    expect(dialogButton("Save")).toBeUndefined();
    expect(dialogButton("Put back as untouched")).toBeUndefined();
    dialogButton("Close")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("shows a viewer a test with no notes or evidence", async () => {
    await dialog({ item: item(), editable: false });
    expect(document.body.querySelector(".v-dialog .bs-notes")).toBeNull();
    expect(document.body.querySelector(".v-dialog ul")).toBeNull();
  });

  it("closes on cancel and starts over when opened again", async () => {
    const { wrapper } = await dialog({ item: finding });
    await fieldNamed(wrapper, "VTextarea", "Notes").setValue("Half typed");
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    expect(fieldNamed(wrapper, "VTextarea", "Notes").props("modelValue")).toContain("banner");
  });

  it("closes when the dialog asks to", async () => {
    const { wrapper } = await dialog({ item: finding });
    emitFrom(wrapper.getComponent({ name: "VDialog" }), "update:modelValue", false);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  function press(wrapper: Awaited<ReturnType<typeof dialog>>["wrapper"], label: string) {
    const found = Array.from(
      document.body.querySelectorAll<HTMLButtonElement>(".v-dialog button"),
    ).findLast((one) => one.textContent.trim() === label);
    if (found === undefined) throw new Error(`no ${label} button`);
    found.click();
    return flushPromises();
  }

  function wrapperCleanup() {
    document.body.innerHTML = "";
  }
});

describe("CustomTestDialog", () => {
  async function adding(handlers: Handlers = {}) {
    const api = mockApi(handlers);
    const mounted = await mountWithApp(CustomTestDialog, "/", {
      modelValue: true,
      pentestId: "p-1",
      categories: ["Information Gathering", "Custom"],
    });
    await flushPromises();
    return { ...api, ...mounted };
  }

  it("adds the test with the name, category and notes typed", async () => {
    const { wrapper, calls } = await adding({
      "POST /api/pentests/p-1/checklist/custom": { status: 201, json: own },
    });
    await fieldNamed(wrapper, "VTextField", "Name").setValue("Check the CDN");
    emitFrom(fieldNamed(wrapper, "VCombobox", "Category"), "update:modelValue", "Edge");
    await fieldNamed(wrapper, "VTextarea", "Notes (optional)").setValue("Cache headers");
    await submitDialog();
    expect(
      calls.find((call) => call.key === "POST /api/pentests/p-1/checklist/custom")?.body,
    ).toEqual({ name: "Check the CDN", category: "Edge", notes: "Cache headers" });
    expect(wrapper.emitted("added")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("falls back to the Custom category when it is cleared", async () => {
    const { wrapper, calls } = await adding({
      "POST /api/pentests/p-1/checklist/custom": { status: 201, json: own },
    });
    emitFrom(fieldNamed(wrapper, "VCombobox", "Category"), "update:modelValue", null);
    await submitDialog();
    expect(
      calls.find((call) => call.key === "POST /api/pentests/p-1/checklist/custom")?.body,
    ).toMatchObject({ category: "Custom" });
  });

  it("says why it was refused and starts over when reopened", async () => {
    const { wrapper } = await adding({
      "POST /api/pentests/p-1/checklist/custom": {
        status: 409,
        json: { code: "too_many_custom", title: "A pentest has at most 100 custom tests" },
      },
    });
    await fieldNamed(wrapper, "VTextField", "Name").setValue("One more");
    await submitDialog();
    expect(alertText()).toContain("at most 100 custom tests");
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    expect(alertText()).toBe("");
    expect(fieldNamed(wrapper, "VTextField", "Name").props("modelValue")).toBe("");
  });

  it("closes on cancel", async () => {
    const { wrapper } = await adding();
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });
});

describe("FeaturesCard", () => {
  function mountCard(props: object, handlers: Handlers = {}) {
    const api = mockApi(handlers);
    return mountWithApp(FeaturesCard, "/", {
      pentestId: "p-1",
      features: ["jwt"],
      suggestions: ["saml", "jwt"],
      editable: true,
      ...props,
    }).then(async (mounted) => {
      await flushPromises();
      return { ...api, ...mounted };
    });
  }

  it("saves the features in one form", async () => {
    const { wrapper, calls } = await mountCard(
      {},
      { "PATCH /api/pentests/p-1": { json: pentest() } },
    );
    emitFrom(fieldNamed(wrapper, "VCombobox", "Features"), "update:modelValue", [
      " Web Socket ",
      "SAML",
    ]);
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(calls.find((call) => call.key === "PATCH /api/pentests/p-1")?.body).toEqual({
      features: ["web-socket", "saml"],
    });
    expect(wrapper.emitted("saved")).toHaveLength(1);
  });

  it("starts from what is named, and follows a change to it", async () => {
    const { wrapper } = await mountCard({});
    expect(fieldNamed(wrapper, "VCombobox", "Features").props("modelValue")).toEqual(["jwt"]);
    await wrapper.setProps({ features: ["saml"] });
    expect(fieldNamed(wrapper, "VCombobox", "Features").props("modelValue")).toEqual(["saml"]);
  });

  it("says why it was refused", async () => {
    const { wrapper } = await mountCard(
      {},
      {
        "PATCH /api/pentests/p-1": {
          status: 409,
          json: { code: "archived", title: "This pentest is archived" },
        },
      },
    );
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("This pentest is archived");
    expect(wrapper.emitted("saved")).toBeUndefined();
  });

  it("shows a viewer the features as words", async () => {
    const { wrapper } = await mountCard({ editable: false });
    expect(wrapper.findAll(".v-chip").map((one) => one.text())).toEqual(["jwt"]);
    expect(wrapper.find("form").exists()).toBe(false);
    await wrapper.setProps({ features: [] });
    expect(wrapper.text()).toContain("None named.");
  });
});

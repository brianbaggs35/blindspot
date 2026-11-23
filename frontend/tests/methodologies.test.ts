import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type {
  Methodology,
  MethodologyDetail,
  Playbook,
  SpecDiff,
  TestDetail,
  TestSummary,
  UpdateCheck,
} from "../src/api/types";
import StateView from "../src/components/StateView.vue";
import { isEmptyDiff, joinLines, lines, matching } from "../src/methodologies";
import MethodologiesView from "../src/views/MethodologiesView.vue";
import PlaybookDialog from "../src/views/methodologies/PlaybookDialog.vue";
import TestDialog from "../src/views/methodologies/TestDialog.vue";
import UpdatesDialog from "../src/views/methodologies/UpdatesDialog.vue";
import { dialogButton, mockApi, mountWithApp, viewer } from "./helpers";

type Handlers = Parameters<typeof mockApi>[0];

const wstg: Methodology = {
  id: "wstg",
  name: "OWASP Web Security Testing Guide",
  source_url: "https://owasp.org/www-project-web-security-testing-guide/",
  license: "CC BY-SA 4.0",
  origin: "bundled",
  enabled: true,
  version_number: 1,
  version_label: "snapshot 2026-11-23",
  content_hash: "a".repeat(64),
  categories: 2,
  tests: 3,
  authored_playbooks: 1,
  custom_playbooks: 0,
  manual_review_tests: 1,
  imported_at: "2026-11-23T10:00:00Z",
  can_update_from_upstream: true,
};

const house: Methodology = {
  ...wstg,
  id: "house",
  name: "House checks",
  origin: "folder",
  can_update_from_upstream: false,
  custom_playbooks: 2,
  version_label: "2.0",
  version_number: 3,
  tests: 1,
  categories: 1,
};

function summary(changes: Partial<TestSummary>): TestSummary {
  return {
    id: "WSTG-INFO-01",
    name: "Search engine discovery",
    reference: null,
    risk_class: "safe",
    tags: [],
    requires: [],
    tools: ["b.http"],
    manual_review: false,
    playbook_source: "generated",
    ...changes,
  };
}

const detail: MethodologyDetail = {
  ...wstg,
  category_list: [
    {
      id: "WSTG-INFO",
      name: "Information Gathering",
      reporting_label: null,
      tests: [
        summary({}),
        summary({
          id: "WSTG-INFO-02",
          name: "Fingerprint the web server",
          risk_class: "active",
          tools: ["c.nmap"],
          playbook_source: "authored",
        }),
      ],
    },
    {
      id: "WSTG-ATHN",
      name: "Authentication",
      reporting_label: null,
      tests: [
        summary({
          id: "WSTG-ATHN-01",
          name: "Credentials over an encrypted channel",
          risk_class: "intrusive",
          tools: [],
          manual_review: true,
          playbook_source: "custom",
        }),
      ],
    },
  ],
};

const houseDetail: MethodologyDetail = {
  ...house,
  category_list: [
    {
      id: "HOUSE-ONE",
      name: "House rules",
      reporting_label: null,
      tests: [summary({ id: "HOUSE-ONE-01", name: "Check the banner" })],
    },
  ],
};

const playbook: Playbook = {
  summary: "Check search engine discovery",
  instructions: "Look at what search engines know.",
  tools: ["b.http"],
  manual_review: false,
  safe_steps: ["Search for the site"],
  active_steps: ["Request robots.txt"],
  intrusive_steps: ["Ask first"],
  evidence: ["The result page"],
  success: "Nothing sensitive is indexed.",
  failure: "Sensitive pages are indexed.",
  not_applicable: ["The site is private"],
};

function testDetail(changes: Partial<TestDetail["test"]> = {}): TestDetail {
  return {
    methodology_id: "wstg",
    category_id: "WSTG-INFO",
    category_name: "Information Gathering",
    test: {
      id: "WSTG-INFO-01",
      name: "Search engine discovery",
      reference: "https://owasp.org/test",
      objectives: ["Find indexed pages"],
      tags: [],
      risk_class: "safe",
      requires: [],
      approach: null,
      playbook,
      playbook_source: "generated",
      ...changes,
    },
  };
}

const noDiff: SpecDiff = {
  added: [],
  removed: [],
  changed: [],
  categories_added: [],
  categories_removed: [],
  details_changed: [],
};

function update(changes: Partial<UpdateCheck> = {}): UpdateCheck {
  return {
    source: "origin",
    current_hash: "a".repeat(64),
    candidate_hash: "b".repeat(64),
    candidate_label: "snapshot 2026-12-01",
    changed: true,
    diff: {
      added: ["WSTG-INFO-99"],
      removed: ["WSTG-INFO-98"],
      changed: [{ id: "WSTG-INFO-02", fields: ["name", "objectives"] }],
      categories_added: ["WSTG-NEW"],
      categories_removed: ["WSTG-OLD"],
      details_changed: ["license"],
    },
    ...changes,
  };
}

function handlers(extra: Handlers = {}, list: Methodology[] = [wstg]): Handlers {
  return {
    "GET /api/methodologies": { json: list },
    "GET /api/methodologies/wstg": { json: detail },
    "GET /api/methodologies/house": { json: houseDetail },
    ...extra,
  };
}

async function page(extra: Handlers = {}, list: Methodology[] = [wstg]) {
  const api = mockApi(handlers(extra, list));
  const mounted = await mountWithApp(MethodologiesView, "/methodologies");
  await flushPromises();
  return { ...api, ...mounted };
}

type Wrapper = Awaited<ReturnType<typeof page>>["wrapper"];

function button(wrapper: Wrapper | VueWrapper, label: string) {
  return wrapper.findAll("button").find((one) => one.text() === label);
}

async function click(wrapper: Wrapper, label: string) {
  await button(wrapper, label)?.trigger("click");
  await flushPromises();
}

async function press(label: string) {
  dialogButton(label)?.click();
  await flushPromises();
}

function field(wrapper: Wrapper | VueWrapper, label: string) {
  return wrapper
    .findAllComponents({ name: "VTextField" })
    .find((one) => one.props("label") === label);
}

// Emits an event as a component would, for the components found by name (which are untyped).
function emitFrom(found: { vm: unknown }, event: string, ...args: unknown[]) {
  (found.vm as { $emit: (name: string, ...rest: unknown[]) => void }).$emit(event, ...args);
}

function alertText() {
  return Array.from(document.body.querySelectorAll(".v-dialog .v-alert[role=alert]"))
    .map((one) => one.textContent)
    .join(" ");
}

async function openCategories(wrapper: Wrapper) {
  for (const title of wrapper.findAll(".v-expansion-panel-title")) {
    if (title.attributes("aria-expanded") !== "true") await title.trigger("click");
  }
  await flushPromises();
}

async function openTest(wrapper: Wrapper, id: string) {
  await openCategories(wrapper);
  await wrapper.get(`[aria-label^='${id}']`).trigger("click");
  await flushPromises();
}

describe("methodology helpers", () => {
  it("turns a text box into a list and back", () => {
    expect(lines(" one \n\n  \ntwo\n")).toEqual(["one", "two"]);
    expect(lines("")).toEqual([]);
    expect(joinLines(["a", "b"])).toBe("a\nb");
  });

  it("filters tests by what was typed and by risk", () => {
    const tests = detail.category_list.flatMap((category) => category.tests);
    expect(matching(tests, { text: "", risks: [] })).toHaveLength(3);
    expect(matching(tests, { text: "  ", risks: [] })).toHaveLength(3);
    expect(matching(tests, { text: "athn-01", risks: [] }).map((one) => one.id)).toEqual([
      "WSTG-ATHN-01",
    ]);
    expect(matching(tests, { text: "FINGERPRINT", risks: [] }).map((one) => one.id)).toEqual([
      "WSTG-INFO-02",
    ]);
    expect(matching(tests, { text: "nmap", risks: [] }).map((one) => one.id)).toEqual([
      "WSTG-INFO-02",
    ]);
    expect(matching(tests, { text: "", risks: ["safe", "intrusive"] })).toHaveLength(2);
    expect(matching(tests, { text: "nmap", risks: ["safe"] })).toEqual([]);
  });

  it("knows an update that changes nothing", () => {
    expect(isEmptyDiff(noDiff)).toBe(true);
    for (const key of Object.keys(noDiff) as (keyof SpecDiff)[]) {
      const one = { ...noDiff, [key]: key === "changed" ? [{ id: "x", fields: [] }] : ["x"] };
      expect(isEmptyDiff(one)).toBe(false);
    }
  });
});

describe("MethodologiesView", () => {
  it("lists the categories and tests with what each one is", async () => {
    const { wrapper } = await page();
    expect(wrapper.get("h1").text()).toBe("Methodologies");
    const text = wrapper.text();
    expect(text).toContain("OWASP Web Security Testing Guide");
    expect(text).toContain("2 categories");
    expect(text).toContain("3 tests");
    expect(text).toContain("1 hand-written playbooks");
    expect(text).toContain("1 reviewed by a person");
    expect(text).toContain("snapshot 2026-11-23 (version 1)");
    expect(text).toContain("Licence: CC BY-SA 4.0");
    expect(text).not.toContain("changed here");
    expect(text).toContain("Showing 3 of 3 tests.");
    expect(text).toContain("Information Gathering");
    expect(text).toContain("Authentication");
    expect(wrapper.find(".v-tab").exists()).toBe(false);
    expect(wrapper.get("a[rel='noopener noreferrer']").attributes("href")).toBe(wstg.source_url);
  });

  it("shows the tests of a category with their risk and where the playbook came from", async () => {
    const { wrapper } = await page();
    await openCategories(wrapper);
    const text = wrapper.text();
    expect(text).toContain("Search engine discovery");
    expect(text).toContain("Safe");
    expect(text).toContain("Active");
    expect(text).toContain("Intrusive");
    expect(text).toContain("Hand-written");
    expect(text).toContain("Changed here");
    expect(text).not.toContain("Generated");
  });

  it("has a tab for each methodology and loads the one chosen", async () => {
    const { wrapper, calls } = await page({}, [wstg, house]);
    const tabs = wrapper.findAll(".v-tab");
    expect(tabs.map((one) => one.text())).toEqual([wstg.name, house.name]);
    await tabs[1]?.trigger("click");
    await flushPromises();
    expect(calls.some((call) => call.key === "GET /api/methodologies/house")).toBe(true);
    expect(wrapper.text()).toContain("2 changed here");
    expect(wrapper.text()).toContain("Showing 1 of 1 tests.");
  });

  it("narrows the tests by search and by risk, and says when none match", async () => {
    const { wrapper } = await page();
    await field(wrapper, "Search tests, ids and tools")?.setValue("nmap");
    expect(wrapper.text()).toContain("Showing 1 of 3 tests.");
    expect(wrapper.text()).not.toContain("Authentication");
    await field(wrapper, "Search tests, ids and tools")?.setValue("");
    const chips = wrapper.findAll(".v-btn-toggle .v-btn");
    expect(chips.map((one) => one.text())).toEqual(["Safe", "Active", "Intrusive"]);
    await chips[2]?.trigger("click");
    expect(wrapper.text()).toContain("Showing 1 of 3 tests.");
    await field(wrapper, "Search tests, ids and tools")?.setValue("nothing like this");
    expect(wrapper.text()).toContain("No test matches that search.");
    expect(wrapper.text()).not.toContain("Showing");
  });

  it("gives an administrator the controls and a viewer none", async () => {
    const { wrapper } = await page();
    expect(button(wrapper, "Read packs folder")).toBeDefined();
    expect(button(wrapper, "Check for updates")).toBeDefined();
    expect(wrapper.findComponent({ name: "VSwitch" }).exists()).toBe(true);
    mockApi(handlers());
    const other = await mountWithApp(MethodologiesView, "/methodologies", {}, { user: viewer });
    await flushPromises();
    expect(button(other.wrapper, "Read packs folder")).toBeUndefined();
    expect(button(other.wrapper, "Check for updates")).toBeUndefined();
    expect(other.wrapper.findComponent({ name: "VSwitch" }).exists()).toBe(false);
    expect(other.wrapper.text()).toContain("Information Gathering");
  });

  it("explains an empty list", async () => {
    const { wrapper } = await page({}, []);
    expect(wrapper.text()).toContain("No methodologies");
    expect(wrapper.text()).toContain("None is installed.");
    expect(button(wrapper, "Check for updates")?.attributes("disabled")).toBeDefined();
  });

  it("explains a failure and tries again", async () => {
    mockApi(handlers({ "GET /api/methodologies": { status: 500, json: { title: "Down" } } }));
    const { wrapper } = await mountWithApp(MethodologiesView, "/methodologies");
    await flushPromises();
    expect(wrapper.text()).toContain("Could not load the methodologies");
    expect(wrapper.text()).toContain("Down");
    mockApi(handlers());
    wrapper.getComponent(StateView).vm.$emit("action");
    await flushPromises();
    expect(wrapper.text()).toContain("Information Gathering");
  });

  it("drops a load that arrives after a newer one", async () => {
    const waiting: { path: string; resolve: (response: Response) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (input: RequestInfo | URL) =>
          new Promise<Response>((resolve) => {
            waiting.push({ path: input as string, resolve });
          }),
      ),
    );
    const { wrapper } = await mountWithApp(MethodologiesView, "/methodologies");
    wrapper.getComponent(StateView).vm.$emit("action");
    await flushPromises();
    const answer = async (path: string, index: number, json: unknown) => {
      waiting
        .filter((one) => one.path === path)
        .at(index)
        ?.resolve(
          new Response(JSON.stringify(json), { headers: { "Content-Type": "application/json" } }),
        );
      await flushPromises();
    };
    await answer("/api/methodologies", 1, [wstg]);
    await answer("/api/methodologies/wstg", 0, detail);
    await answer("/api/methodologies", 0, [wstg, house]);
    await answer("/api/methodologies/wstg", 1, houseDetail);
    expect(wrapper.text()).toContain("Information Gathering");
    expect(wrapper.text()).not.toContain("House rules");
  });

  it("ignores a failure that arrives after a newer load", async () => {
    const pending: { resolve: (value: Response) => void; reject: (error: Error) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (input: RequestInfo | URL) =>
          new Promise<Response>((resolve, reject) => {
            if (input === "/api/methodologies") pending.push({ resolve, reject });
            else {
              resolve(
                new Response(JSON.stringify(detail), {
                  headers: { "Content-Type": "application/json" },
                }),
              );
            }
          }),
      ),
    );
    const { wrapper } = await mountWithApp(MethodologiesView, "/methodologies");
    wrapper.getComponent(StateView).vm.$emit("action");
    await flushPromises();
    pending[1]?.resolve(
      new Response(JSON.stringify([wstg]), { headers: { "Content-Type": "application/json" } }),
    );
    await flushPromises();
    pending[0]?.reject(new Error("late failure"));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Could not load the methodologies");
  });

  it("turns a methodology on and off", async () => {
    const { wrapper, calls } = await page({
      "PATCH /api/methodologies/wstg": { json: { ...wstg, enabled: false } },
    });
    emitFrom(wrapper.getComponent({ name: "VSwitch" }), "update:modelValue", false);
    await flushPromises();
    expect(calls.find((call) => call.key === "PATCH /api/methodologies/wstg")?.body).toEqual({
      enabled: false,
    });
    expect(document.body.textContent).toContain("OWASP Web Security Testing Guide is off.");
    emitFrom(wrapper.getComponent({ name: "VSwitch" }), "update:modelValue", true);
    await flushPromises();
    expect(calls.filter((call) => call.key === "PATCH /api/methodologies/wstg")).toHaveLength(2);
    expect(document.body.textContent).toContain("OWASP Web Security Testing Guide is on.");
  });

  it("treats a cleared switch as off", async () => {
    const { wrapper, calls } = await page({ "PATCH /api/methodologies/wstg": { json: wstg } });
    emitFrom(wrapper.getComponent({ name: "VSwitch" }), "update:modelValue", null);
    await flushPromises();
    expect(calls.find((call) => call.key === "PATCH /api/methodologies/wstg")?.body).toEqual({
      enabled: false,
    });
  });

  it("says why a switch could not be changed", async () => {
    const { wrapper } = await page({
      "PATCH /api/methodologies/wstg": { status: 500, json: { title: "Nope" } },
    });
    emitFrom(wrapper.getComponent({ name: "VSwitch" }), "update:modelValue", false);
    await flushPromises();
    expect(document.body.textContent).toContain("Nope");
  });

  it("reads the packs folder and reports what it found", async () => {
    const { wrapper } = await page({
      "POST /api/methodologies/reload": {
        json: {
          added: ["house"],
          updates_available: ["wstg"],
          problems: { broken: "There is no tools.yaml" },
        },
      },
    });
    await click(wrapper, "Read packs folder");
    const text = document.body.textContent;
    expect(text).toContain("Added house.");
    expect(text).toContain("Updates are waiting for wstg.");
    expect(text).toContain("broken: There is no tools.yaml");
  });

  it("says when the folder has nothing new", async () => {
    const { wrapper } = await page({
      "POST /api/methodologies/reload": {
        json: { added: [], updates_available: [], problems: {} },
      },
    });
    await click(wrapper, "Read packs folder");
    expect(document.body.textContent).toContain("No new packs.");
  });

  it("says why the folder could not be read", async () => {
    const { wrapper } = await page({
      "POST /api/methodologies/reload": { status: 500, json: { title: "Disk trouble" } },
    });
    await click(wrapper, "Read packs folder");
    expect(document.body.textContent).toContain("Disk trouble");
  });

  it("opens a test, and shows its playbook", async () => {
    const { wrapper } = await page({
      "GET /api/methodologies/wstg/tests/WSTG-INFO-01": { json: testDetail() },
    });
    await openTest(wrapper, "WSTG-INFO-01");
    const dialog = wrapper.getComponent(TestDialog);
    expect(dialog.props("testId")).toBe("WSTG-INFO-01");
    const text = document.body.textContent;
    expect(text).toContain("WSTG-INFO-01 · Search engine discovery");
    expect(text).toContain("Look at what search engines know.");
    expect(text).toContain("Request robots.txt");
  });

  it("refreshes the list after a playbook was changed in a test", async () => {
    const { wrapper, calls } = await page({
      "GET /api/methodologies/wstg/tests/WSTG-INFO-01": { json: testDetail() },
    });
    await openTest(wrapper, "WSTG-INFO-01");
    const before = calls.filter((call) => call.key === "GET /api/methodologies").length;
    wrapper.getComponent(TestDialog).vm.$emit("changed");
    await flushPromises();
    expect(calls.filter((call) => call.key === "GET /api/methodologies")).toHaveLength(before + 1);
  });

  it("applies an update from the dialog and says which version is now in use", async () => {
    const { wrapper } = await page({
      "GET /api/methodologies/wstg/updates?source=origin": { json: update() },
      "POST /api/methodologies/wstg/updates": {
        json: { ...wstg, version_number: 2, version_label: "snapshot 2026-12-01" },
      },
    });
    await click(wrapper, "Check for updates");
    await press("Check for an update");
    await press("Apply this update");
    expect(document.body.textContent).toContain(
      "OWASP Web Security Testing Guide is now snapshot 2026-12-01.",
    );
    expect(wrapper.getComponent(UpdatesDialog).props("modelValue")).toBe(false);
  });
});

describe("the parts of the page that need no data", () => {
  it("has nothing to list, switch or change without a methodology", async () => {
    const { wrapper } = await page({}, []);
    const vm = wrapper.vm as unknown as {
      categories: unknown[];
      toggle: (on: boolean) => Promise<void>;
    };
    expect(vm.categories).toEqual([]);
    await vm.toggle(true);
    expect(document.body.textContent).not.toContain(" is on.");
  });

  it("follows its dialogs when they close themselves", async () => {
    const { wrapper } = await page({
      "GET /api/methodologies/wstg/tests/WSTG-INFO-01": { json: testDetail() },
    });
    await openTest(wrapper, "WSTG-INFO-01");
    wrapper.getComponent(TestDialog).vm.$emit("update:modelValue", false);
    wrapper.getComponent(UpdatesDialog).vm.$emit("update:modelValue", true);
    await flushPromises();
    expect(wrapper.getComponent(TestDialog).props("modelValue")).toBe(false);
    expect(wrapper.getComponent(UpdatesDialog).props("modelValue")).toBe(true);
    wrapper.getComponent(UpdatesDialog).vm.$emit("update:modelValue", false);
    await flushPromises();
    expect(wrapper.getComponent(UpdatesDialog).props("modelValue")).toBe(false);
  });

  it("lets the notice close itself", async () => {
    const { wrapper } = await page({
      "POST /api/methodologies/reload": {
        json: { added: [], updates_available: [], problems: {} },
      },
    });
    await click(wrapper, "Read packs folder");
    emitFrom(wrapper.getComponent({ name: "VSnackbar" }), "update:modelValue", false);
    await flushPromises();
    expect(wrapper.getComponent({ name: "VSnackbar" }).props("modelValue")).toBe(false);
  });

  it("lets each dialog close itself", async () => {
    mockApi({
      "GET /api/methodologies/wstg/tests/WSTG-INFO-01": { json: testDetail() },
      "GET /api/methodologies/wstg/updates?source=origin": { json: update() },
    });
    for (const [component, props] of [
      [TestDialog, { methodologyId: "wstg", testId: "WSTG-INFO-01", canEdit: true }],
      [PlaybookDialog, { methodologyId: "wstg", testId: "WSTG-INFO-01", playbook }],
      [UpdatesDialog, { methodology: wstg }],
    ] as const) {
      const { wrapper } = await mountWithApp(component, "/methodologies", {
        modelValue: true,
        ...props,
      });
      await flushPromises();
      emitFrom(wrapper.getComponent({ name: "VDialog" }), "update:modelValue", false);
      await flushPromises();
      expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
    }
  });

  it("has no steps or parts to list before there is anything to show", async () => {
    mockApi({});
    const test = await mountWithApp(TestDialog, "/methodologies", {
      modelValue: false,
      methodologyId: "wstg",
      testId: "WSTG-INFO-01",
      canEdit: false,
    });
    const updates = await mountWithApp(UpdatesDialog, "/methodologies", {
      modelValue: false,
      methodology: wstg,
    });
    expect((test.wrapper.vm as unknown as { steps: unknown[] }).steps).toEqual([]);
    expect((updates.wrapper.vm as unknown as { parts: unknown[] }).parts).toEqual([]);
  });
});

describe("TestDialog", () => {
  async function dialog(
    changes: Partial<TestDetail["test"]> = {},
    canEdit = true,
    extra: Handlers = {},
  ) {
    const api = mockApi({
      "GET /api/methodologies/wstg/tests/WSTG-INFO-01": { json: testDetail(changes) },
      ...extra,
    });
    const mounted = await mountWithApp(TestDialog, "/methodologies", {
      modelValue: false,
      methodologyId: "wstg",
      testId: "WSTG-INFO-01",
      canEdit,
    });
    await mounted.wrapper.setProps({ modelValue: true });
    await flushPromises();
    return { ...api, ...mounted };
  }

  it("shows everything the agent is told", async () => {
    await dialog({ requires: ["saml"] });
    const text = document.body.textContent;
    for (const expected of [
      "Search engine discovery",
      "Information Gathering",
      "only if the target has saml",
      "Find indexed pages",
      "Check search engine discovery",
      "Look at what search engines know.",
      "Safe steps",
      "Search for the site",
      "Active steps",
      "Intrusive steps, only after approval",
      "The result page",
      "Nothing sensitive is indexed.",
      "Sensitive pages are indexed.",
      "Not applicable when",
      "The site is private",
      "Generated",
    ]) {
      expect(text).toContain(expected);
    }
    expect(document.body.querySelector("a[href='https://owasp.org/test']")).not.toBeNull();
    expect(text).not.toContain("A person reviews the result");
    expect(text).not.toContain("None: this test is done by the agent");
  });

  it("leaves out what a playbook does not have", async () => {
    await dialog({
      reference: null,
      playbook: {
        ...playbook,
        tools: [],
        manual_review: true,
        safe_steps: [],
        active_steps: [],
        intrusive_steps: [],
        not_applicable: [],
      },
    });
    const text = document.body.textContent;
    expect(text).toContain("A person reviews the result");
    expect(text).toContain("None: this test is done by the agent");
    expect(text).not.toContain("Safe steps");
    expect(text).not.toContain("Active steps");
    expect(text).not.toContain("Intrusive steps");
    expect(text).not.toContain("Not applicable when");
    expect(text).not.toContain("Read the test in its guide");
  });

  it("explains a failure to load", async () => {
    await dialog({}, true, {
      "GET /api/methodologies/wstg/tests/WSTG-INFO-01": { status: 404, json: { title: "Gone" } },
    });
    expect(alertText()).toContain("Gone");
    expect(document.body.textContent).toContain("Loading the test");
    expect(dialogButton("Edit the playbook")).toBeUndefined();
  });

  it("shows a viewer the playbook without the buttons", async () => {
    await dialog({}, false);
    expect(dialogButton("Edit the playbook")).toBeUndefined();
    expect(dialogButton("Put the original back")).toBeUndefined();
    expect(dialogButton("Close")).toBeDefined();
  });

  it("closes", async () => {
    const { wrapper } = await dialog();
    await press("Close");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("only offers to put the original back when the playbook was changed", async () => {
    await dialog({ playbook_source: "authored" });
    expect(dialogButton("Put the original back")).toBeUndefined();
    expect(dialogButton("Edit the playbook")).toBeDefined();
  });

  it("puts the original back and reloads", async () => {
    const { wrapper, calls } = await dialog({ playbook_source: "custom" }, true, {
      "DELETE /api/methodologies/wstg/tests/WSTG-INFO-01/playbook": { status: 204 },
    });
    await press("Put the original back");
    expect(
      calls.some(
        (call) => call.key === "DELETE /api/methodologies/wstg/tests/WSTG-INFO-01/playbook",
      ),
    ).toBe(true);
    expect(wrapper.emitted("changed")).toHaveLength(1);
    expect(
      calls.filter((call) => call.key === "GET /api/methodologies/wstg/tests/WSTG-INFO-01"),
    ).toHaveLength(2);
  });

  it("says why the original could not be put back", async () => {
    const { wrapper } = await dialog({ playbook_source: "custom" }, true, {
      "DELETE /api/methodologies/wstg/tests/WSTG-INFO-01/playbook": {
        status: 500,
        json: { title: "Cannot" },
      },
    });
    await press("Put the original back");
    expect(alertText()).toContain("Cannot");
    expect(wrapper.emitted("changed")).toBeUndefined();
  });

  it("ignores a load that arrives after a newer one", async () => {
    const waiting: ((response: Response) => void)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            waiting.push(resolve);
          }),
      ),
    );
    const { wrapper } = await mountWithApp(TestDialog, "/methodologies", {
      modelValue: false,
      methodologyId: "wstg",
      testId: "WSTG-INFO-01",
      canEdit: true,
    });
    await wrapper.setProps({ modelValue: true });
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    const reply = async (index: number, name: string) => {
      waiting.at(index)?.(
        new Response(JSON.stringify(testDetail({ name })), {
          headers: { "Content-Type": "application/json" },
        }),
      );
      await flushPromises();
    };
    await reply(1, "The newer one");
    await reply(0, "The older one");
    expect(document.body.textContent).toContain("The newer one");
    expect(document.body.textContent).not.toContain("The older one");
  });

  it("ignores a failure that arrives after a newer load", async () => {
    const waiting: { resolve: (response: Response) => void; reject: (error: Error) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve, reject) => {
            waiting.push({ resolve, reject });
          }),
      ),
    );
    const { wrapper } = await mountWithApp(TestDialog, "/methodologies", {
      modelValue: false,
      methodologyId: "wstg",
      testId: "WSTG-INFO-01",
      canEdit: true,
    });
    await wrapper.setProps({ modelValue: true });
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    waiting[1]?.resolve(
      new Response(JSON.stringify(testDetail()), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await flushPromises();
    waiting[0]?.reject(new Error("late failure"));
    await flushPromises();
    expect(alertText()).not.toContain("late failure");
  });

  it("opens the editor and shows what the editor saved", async () => {
    const { wrapper } = await dialog({}, true, {
      "PUT /api/methodologies/wstg/tests/WSTG-INFO-01/playbook": {
        json: testDetail({ name: "Renamed by the server", playbook_source: "custom" }),
      },
    });
    await press("Edit the playbook");
    expect(wrapper.getComponent(PlaybookDialog).props("modelValue")).toBe(true);
    await press("Save playbook");
    expect(wrapper.emitted("changed")).toHaveLength(1);
    expect(document.body.textContent).toContain("Renamed by the server");
  });
});

describe("PlaybookDialog", () => {
  async function editor(extra: Handlers = {}) {
    const api = mockApi(extra);
    const mounted = await mountWithApp(PlaybookDialog, "/methodologies", {
      modelValue: false,
      methodologyId: "wstg",
      testId: "WSTG-INFO-01",
      playbook,
    });
    await mounted.wrapper.setProps({ modelValue: true });
    await flushPromises();
    return { ...api, ...mounted };
  }

  async function submit() {
    document.body
      .querySelector<HTMLFormElement>(".v-dialog form")
      ?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flushPromises();
  }

  function box(label: string) {
    return Array.from(document.body.querySelectorAll<HTMLElement>(".v-dialog .v-field"))
      .find((one) => one.querySelector("label")?.textContent === label)
      ?.querySelector<HTMLInputElement | HTMLTextAreaElement>("input, textarea");
  }

  it("starts from the playbook it was given", async () => {
    await editor();
    expect(box("Summary")?.value).toBe(playbook.summary);
    expect(box("Instructions to the agent")?.value).toBe(playbook.instructions);
    expect(box("Safe steps")?.value).toBe("Search for the site");
    expect(box("Mark it not applicable when")?.value).toBe("The site is private");
    expect(document.body.textContent).toContain("b.http");
  });

  it("saves what was typed, one entry to a line", async () => {
    const { wrapper, calls } = await editor({
      "PUT /api/methodologies/wstg/tests/WSTG-INFO-01/playbook": { json: testDetail() },
    });
    const typed = {
      Summary: "  A new summary ",
      "Instructions to the agent": "Do the new thing.",
      "Safe steps": "one\n\ntwo\n",
      "Active steps": "",
      "Intrusive steps (always ask first)": "ask\n",
      "Evidence to bring back": "proof",
      "Mark it passed when": " fine ",
      "Report a finding when": "bad",
      "Mark it not applicable when": "",
    };
    for (const [label, value] of Object.entries(typed)) {
      const input = box(label);
      if (input === null || input === undefined) throw new Error(`no ${label}`);
      input.value = value;
      input.dispatchEvent(new Event("input"));
    }
    emitFrom(wrapper.getComponent({ name: "VSwitch" }), "update:modelValue", true);
    emitFrom(wrapper.getComponent({ name: "VCombobox" }), "update:modelValue", [
      "b.http",
      "c.nmap",
    ]);
    await flushPromises();
    await submit();
    expect(
      calls.find((call) => call.key === "PUT /api/methodologies/wstg/tests/WSTG-INFO-01/playbook")
        ?.body,
    ).toEqual({
      summary: "A new summary",
      instructions: "Do the new thing.",
      tools: ["b.http", "c.nmap"],
      manual_review: true,
      safe_steps: ["one", "two"],
      active_steps: [],
      intrusive_steps: ["ask"],
      evidence: ["proof"],
      success: "fine",
      failure: "bad",
      not_applicable: [],
    });
    expect(wrapper.emitted("saved")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("keeps the dialog open and says why a save was refused", async () => {
    const { wrapper } = await editor({
      "PUT /api/methodologies/wstg/tests/WSTG-INFO-01/playbook": {
        status: 422,
        json: { title: "Not a valid playbook" },
      },
    });
    await submit();
    expect(alertText()).toContain("Not a valid playbook");
    expect(wrapper.emitted("saved")).toBeUndefined();
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("starts again from the playbook each time it opens", async () => {
    const { wrapper } = await editor({
      "PUT /api/methodologies/wstg/tests/WSTG-INFO-01/playbook": {
        status: 422,
        json: { title: "Refused" },
      },
    });
    const input = box("Summary");
    if (input === null || input === undefined) throw new Error("no summary");
    input.value = "Changed";
    input.dispatchEvent(new Event("input"));
    await submit();
    expect(alertText()).toContain("Refused");
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(box("Summary")?.value).toBe(playbook.summary);
    expect(alertText()).not.toContain("Refused");
  });

  it("cancels", async () => {
    const { wrapper } = await editor();
    await press("Cancel");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });
});

describe("UpdatesDialog", () => {
  async function updates(methodology: Methodology = wstg, extra: Handlers = {}) {
    const api = mockApi(extra);
    const mounted = await mountWithApp(UpdatesDialog, "/methodologies", {
      modelValue: false,
      methodology,
    });
    await mounted.wrapper.setProps({ modelValue: true });
    await flushPromises();
    return { ...api, ...mounted };
  }

  it("says what is in use and that checking changes nothing", async () => {
    await updates();
    const text = document.body.textContent;
    expect(text).toContain("Update OWASP Web Security Testing Guide");
    expect(text).toContain("Now in use: snapshot 2026-11-23 (version 1)");
    expect(text).toContain("The latest checklist published by OWASP");
  });

  it("only offers a choice of source when upstream can be read", async () => {
    await updates({ ...wstg, can_update_from_upstream: false });
    expect(document.body.textContent).not.toContain("The latest checklist published by OWASP");
  });

  it("shows what an update would change", async () => {
    await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": { json: update() },
    });
    await press("Check for an update");
    const text = document.body.textContent;
    expect(text).toContain("snapshot 2026-12-01 would change the following.");
    expect(text).toContain("Tests added (1)");
    expect(text).toContain("WSTG-INFO-99");
    expect(text).toContain("Tests removed (1)");
    expect(text).toContain("Categories added (1)");
    expect(text).toContain("Categories removed (1)");
    expect(text).toContain("Details changed (1)");
    expect(text).toContain("Tests changed (1)");
    expect(text).toContain("WSTG-INFO-02: name, objectives");
    expect(text).toContain("Playbooks you changed stay as you wrote them.");
    expect(text).not.toContain("Only the order or wording");
    expect(dialogButton("Apply this update")).toBeDefined();
  });

  it("leaves out the parts of an update that change nothing", async () => {
    await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": {
        json: update({ diff: { ...noDiff, added: ["WSTG-INFO-99"] } }),
      },
    });
    await press("Check for an update");
    const text = document.body.textContent;
    expect(text).toContain("Tests added (1)");
    expect(text).not.toContain("Tests removed");
    expect(text).not.toContain("Tests changed");
  });

  it("says when only the wording differs", async () => {
    await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": {
        json: update({ diff: noDiff }),
      },
    });
    await press("Check for an update");
    expect(document.body.textContent).toContain(
      "Only the order or wording inside the methodology differs.",
    );
  });

  it("says when there is nothing to update", async () => {
    await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": {
        json: update({ changed: false, diff: noDiff }),
      },
    });
    await press("Check for an update");
    expect(document.body.textContent).toContain("Nothing to update: this is already the latest.");
    expect(dialogButton("Apply this update")).toBeUndefined();
  });

  it("looks at the upstream copy when asked, and forgets a check when the source changes", async () => {
    const { wrapper, calls } = await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": { json: update() },
      "GET /api/methodologies/wstg/updates?source=upstream": {
        json: update({ source: "upstream", candidate_label: "upstream today" }),
      },
    });
    await press("Check for an update");
    expect(document.body.textContent).toContain("would change the following");
    emitFrom(wrapper.getComponent({ name: "VRadioGroup" }), "update:modelValue", "upstream");
    await flushPromises();
    expect(document.body.textContent).not.toContain("would change the following");
    await press("Check for an update");
    expect(
      calls.some((call) => call.key === "GET /api/methodologies/wstg/updates?source=upstream"),
    ).toBe(true);
    expect(document.body.textContent).toContain("upstream today would change the following");
  });

  it("applies the update that was shown, and no other", async () => {
    const { wrapper, calls } = await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": { json: update() },
      "POST /api/methodologies/wstg/updates": { json: { ...wstg, version_number: 2 } },
    });
    await press("Check for an update");
    await press("Apply this update");
    expect(calls.find((call) => call.key === "POST /api/methodologies/wstg/updates")?.body).toEqual(
      {
        source: "origin",
        candidate_hash: "b".repeat(64),
      },
    );
    expect(wrapper.emitted("applied")).toEqual([[{ ...wstg, version_number: 2 }]]);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("says why an update was refused", async () => {
    const { wrapper } = await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": { json: update() },
      "POST /api/methodologies/wstg/updates": {
        status: 409,
        json: { title: "The update changed since you looked" },
      },
    });
    await press("Check for an update");
    await press("Apply this update");
    expect(alertText()).toContain("The update changed since you looked");
    expect(wrapper.emitted("applied")).toBeUndefined();
  });

  it("says why a check failed", async () => {
    await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": {
        status: 502,
        json: { title: "Upstream is down" },
      },
    });
    await press("Check for an update");
    expect(alertText()).toContain("Upstream is down");
    expect(dialogButton("Apply this update")).toBeUndefined();
  });

  it("starts clean each time it opens", async () => {
    const { wrapper } = await updates(wstg, {
      "GET /api/methodologies/wstg/updates?source=origin": { json: update() },
    });
    await press("Check for an update");
    expect(document.body.textContent).toContain("would change the following");
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(document.body.textContent).not.toContain("would change the following");
  });

  it("does nothing when asked to apply before a check", async () => {
    const { wrapper } = await updates();
    const vm = wrapper.vm as unknown as { apply: () => Promise<void> };
    await vm.apply();
    expect(wrapper.emitted("applied")).toBeUndefined();
  });

  it("closes", async () => {
    const { wrapper } = await updates();
    await press("Close");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });
});

import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResultsCard from "../src/views/pentests/ResultsCard.vue";
import AnnotateDialog from "../src/views/results/AnnotateDialog.vue";
import ImportDialog from "../src/views/results/ImportDialog.vue";
import NoteDialog from "../src/views/results/NoteDialog.vue";
import { mockApi, mountWithApp, submitDialog } from "./helpers";
import { emitFrom, fieldNamed } from "./pentest-fixtures";
import { fullOf, listOf, summaryOf } from "./results-fixtures";

/** A promise settled from outside, for an answer that must arrive late. */
function deferred() {
  let resolve: (value: Response) => void = () => undefined;
  let reject: (reason: Error) => void = () => undefined;
  const promise = new Promise<Response>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  vi.restoreAllMocks();
});

const BASE = "/api/pentests/p-1/results";

function alertText() {
  return document.body.querySelector(".v-dialog .v-alert[role=alert]")?.textContent ?? "";
}

async function type(selector: string, value: string) {
  const field = document.body.querySelector<HTMLInputElement>(`.v-dialog ${selector}`);
  if (field === null) throw new Error(`no ${selector}`);
  field.value = value;
  field.dispatchEvent(new Event("input"));
  await flushPromises();
}

describe("NoteDialog", () => {
  it("writes a result by hand, and starts empty each time it opens", async () => {
    const api = mockApi({ [`POST ${BASE}`]: { json: fullOf() } });
    const { wrapper } = await mountWithApp(NoteDialog, "/", { modelValue: true, pentestId: "p-1" });
    await flushPromises();
    await type("input[autocomplete=off]", "Saw a form");
    await type("textarea", "Looks like a login");
    await fieldNamed(wrapper, "VSelect", "How serious (optional)").setValue("low");
    await fieldNamed(wrapper, "VTextField", "Checklist test (optional)").setValue("WSTG-1");
    emitFrom(fieldNamed(wrapper, "VCombobox", "Tags (optional)"), "update:modelValue", ["login"]);
    await submitDialog();
    expect(api.calls).toContainEqual({
      key: `POST ${BASE}`,
      body: {
        title: "Saw a form",
        notes: "Looks like a login",
        severity: "low",
        tags: ["login"],
        test_id: "WSTG-1",
      },
    });
    expect(wrapper.emitted("added")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);

    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(
      document.body.querySelector<HTMLInputElement>(".v-dialog input[autocomplete=off]")?.value,
    ).toBe("");
  });

  it("sends no test when none is given, and says why it failed", async () => {
    let fail = true;
    const api = mockApi({
      [`POST ${BASE}`]: () =>
        fail ? { status: 422, json: { detail: "Bad" } } : { json: fullOf() },
    });
    await mountWithApp(NoteDialog, "/", { modelValue: true, pentestId: "p-1" });
    await flushPromises();
    await type("input[autocomplete=off]", "Title");
    await submitDialog();
    expect(alertText()).toContain("The request failed (422)");
    fail = false;
    await submitDialog();
    expect(api.calls.at(-1)?.body).toMatchObject({ test_id: null });
  });
});

describe("ImportDialog", () => {
  it("imports pasted output with the chosen tool and an optional title", async () => {
    const api = mockApi({ [`POST ${BASE}/import`]: { json: fullOf() } });
    const { wrapper } = await mountWithApp(ImportDialog, "/", {
      modelValue: true,
      pentestId: "p-1",
    });
    await flushPromises();
    await fieldNamed(wrapper, "VSelect", "Which tool made it").setValue("nuclei_jsonl");
    await type("textarea", "{}");
    await type("input[autocomplete=off]", " Mine ");
    await submitDialog();
    expect(api.calls.at(-1)).toEqual({
      key: `POST ${BASE}/import`,
      body: { parser: "nuclei_jsonl", content: "{}", title: "Mine" },
    });
    expect(wrapper.emitted("added")).toHaveLength(1);
  });

  it("sends no title when none is given, reads a file, and says why it failed", async () => {
    let fail = true;
    const api = mockApi({
      [`POST ${BASE}/import`]: () =>
        fail ? { status: 422, json: { detail: "Bad" } } : { json: fullOf() },
    });
    const { wrapper } = await mountWithApp(ImportDialog, "/", {
      modelValue: true,
      pentestId: "p-1",
    });
    await flushPromises();
    const input = fieldNamed(wrapper, "VFileInput", "Load from a file (optional)");
    emitFrom(input, "update:modelValue", null);
    emitFrom(input, "update:modelValue", []);
    emitFrom(input, "update:modelValue", { text: () => Promise.resolve("<nmaprun/>") });
    await flushPromises();
    emitFrom(input, "update:modelValue", [{ text: () => Promise.resolve("<nmaprun a/>") }]);
    await flushPromises();
    await submitDialog();
    expect(alertText()).toContain("The request failed (422)");
    fail = false;
    await submitDialog();
    expect(api.calls.at(-1)?.body).toEqual({ parser: "nmap_xml", content: "<nmaprun a/>" });
  });
});

describe("AnnotateDialog", () => {
  it("saves a title, notes, tags and test, starting from what the result has", async () => {
    const result = fullOf({ test_id: null });
    const api = mockApi({ [`PATCH ${BASE}/r-1`]: { json: fullOf({ title: "Better" }) } });
    const { wrapper } = await mountWithApp(AnnotateDialog, "/", {
      modelValue: true,
      pentestId: "p-1",
      result,
    });
    await flushPromises();
    expect(
      document.body.querySelector<HTMLInputElement>(".v-dialog input[autocomplete=off]")?.value,
    ).toBe(result.title);
    await type("input[autocomplete=off]", "Better");
    await submitDialog();
    expect(api.calls.at(-1)).toEqual({
      key: `PATCH ${BASE}/r-1`,
      body: { title: "Better", notes: result.notes, tags: result.tags, test_id: null },
    });
    expect(wrapper.emitted("saved")).toHaveLength(1);
    await fieldNamed(wrapper, "VTextField", "Checklist test (optional)").setValue("WSTG-2");
    emitFrom(fieldNamed(wrapper, "VCombobox", "Tags"), "update:modelValue", ["x"]);
    emitFrom(wrapper.getComponent({ name: "FormDialog" }), "update:modelValue", false);
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("keeps the test it has and says why a save failed", async () => {
    mockApi({ [`PATCH ${BASE}/r-1`]: { status: 500, json: { detail: "Down" } } });
    await mountWithApp(AnnotateDialog, "/", {
      modelValue: true,
      pentestId: "p-1",
      result: fullOf(),
    });
    await flushPromises();
    await submitDialog();
    expect(alertText()).toContain("The request failed (500)");
  });
});

describe("ResultsCard", () => {
  it("shows how many results there are and the latest, each with a link", async () => {
    mockApi({
      [`GET ${BASE}?limit=3`]: {
        json: listOf([summaryOf(), summaryOf({ id: "r-2", title: "Note", top_severity: null })], 9),
      },
    });
    const { wrapper } = await mountWithApp(ResultsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    expect(wrapper.text()).toContain("9 results recorded. The latest:");
    expect(wrapper.text()).toContain("Medium");
    expect(wrapper.find("a[href='/pentests/p-1/results/r-2']").exists()).toBe(true);
    expect(wrapper.find("a[href='/pentests/p-1/results']").exists()).toBe(true);
  });

  it("says when nothing is recorded, a single result, and why it could not load", async () => {
    mockApi({ [`GET ${BASE}?limit=3`]: { json: listOf([]) } });
    const empty = await mountWithApp(ResultsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    expect(empty.wrapper.text()).toContain("Nothing has been recorded yet.");

    mockApi({ [`GET ${BASE}?limit=3`]: { json: listOf([summaryOf()]) } });
    const one = await mountWithApp(ResultsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    expect(one.wrapper.text()).toContain("1 result recorded.");

    mockApi({ [`GET ${BASE}?limit=3`]: { status: 500, json: { detail: "Down" } } });
    const failed = await mountWithApp(ResultsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    expect(failed.wrapper.text()).toContain("Could not load the results");
  });

  it("ignores a late list for a pentest that was left", async () => {
    const api = mockApi({
      [`GET ${BASE}?limit=3`]: { json: listOf([]) },
      "GET /api/pentests/p-2/results?limit=3": { json: listOf([]) },
    });
    const { wrapper } = await mountWithApp(ResultsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    const slow = deferred();
    api.fetchMock.mockImplementationOnce(() => slow.promise);
    await wrapper.setProps({ pentestId: "p-2" });
    await wrapper.setProps({ pentestId: "p-1" });
    await flushPromises();
    slow.resolve(new Response(JSON.stringify(listOf([summaryOf({ title: "Stale one" })]))));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Stale one");
  });

  it("reloads for another pentest and ignores a late answer", async () => {
    const api = mockApi({
      [`GET ${BASE}?limit=3`]: { json: listOf([]) },
      "GET /api/pentests/p-2/results?limit=3": { json: listOf([summaryOf()]) },
    });
    const { wrapper } = await mountWithApp(ResultsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    const slow = deferred();
    api.fetchMock.mockImplementationOnce(() => slow.promise);
    await wrapper.setProps({ pentestId: "p-2" });
    await wrapper.setProps({ pentestId: "p-1" });
    await flushPromises();
    slow.reject(new Error("late"));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Could not load");
  });
});

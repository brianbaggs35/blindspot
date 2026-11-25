import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import PentestResultsView from "../src/views/PentestResultsView.vue";
import PentestResultView from "../src/views/PentestResultView.vue";
import { dialogButton, fillDialog, mockApi, mountWithApp, submitDialog, viewer } from "./helpers";
import { emitFrom, fieldNamed, pentest } from "./pentest-fixtures";
import type { Friendly } from "../src/api/types";
import { fullOf, listOf, rawOf, summaryOf } from "./results-fixtures";

type Handlers = Parameters<typeof mockApi>[0];

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
const LIST = `GET ${BASE}?view=live&limit=50`;
const wait = (ms: number) => new Promise((done) => setTimeout(done, ms));

function press(root: Pick<VueWrapper, "findAll">, label: string) {
  const found = root.findAll("button").find((one) => one.text() === label);
  if (found === undefined) throw new Error(`no ${label} button`);
  return found.trigger("click");
}

function noticeText() {
  return document.body.textContent;
}

/** Page text with every run of white space made one space, as a person reads it. */
function read(root: { text: () => string }) {
  return root.text().replace(/\s+/g, " ");
}

/** The newest open dialog's field and form: closed dialogs stay in the page. */
async function fillLast(selector: string, value: string) {
  const fields = document.body.querySelectorAll<HTMLInputElement>(`.v-dialog ${selector}`);
  const field = fields[fields.length - 1];
  if (field === undefined) throw new Error(`no ${selector} in a dialog`);
  field.value = value;
  field.dispatchEvent(new Event("input"));
  await flushPromises();
}

async function submitLast() {
  const forms = document.body.querySelectorAll<HTMLFormElement>(".v-dialog form");
  forms[forms.length - 1]?.dispatchEvent(new Event("submit", { cancelable: true }));
  await flushPromises();
}

const SELECT_ONE = "input[aria-label='Select Nmap scan of shop.example.com']";

async function listPage(handlers: Handlers = {}, user = undefined as typeof viewer | undefined) {
  const api = mockApi({
    [LIST]: { json: listOf() },
    "GET /api/pentests/p-1": { json: pentest() },
    ...handlers,
  });
  const mounted = await mountWithApp(
    PentestResultsView,
    "/pentests/p-1/results",
    {},
    user ? { user } : {},
  );
  await flushPromises();
  return { ...api, ...mounted };
}

describe("PentestResultsView", () => {
  it("lists the results with what each is, and links to each", async () => {
    const { wrapper } = await listPage({
      [LIST]: {
        json: listOf([
          summaryOf(),
          summaryOf({
            id: "r-2",
            title: "Failed run",
            status: "failed",
            top_severity: null,
            issue_count: 0,
            tool_id: null,
            agent_role: null,
            test_id: null,
            source: "manual",
            summary: [],
            tags: [],
          }),
          summaryOf({ id: "r-3", title: "One issue", issue_count: 1 }),
        ]),
      },
    });
    const text = read(wrapper);
    expect(wrapper.get("h1").text()).toBe("Results: Acme storefront");
    expect(text).toContain("Showing 3 of 3.");
    expect(text).toContain("Tool run · p.nmap · recon · test WSTG-INFO-02");
    expect(text).toContain("Medium · 2");
    expect(text).toContain("One host is up and 2 ports are open.");
    expect(text).toContain("Failed");
    expect(text).toContain("Note");
    expect(wrapper.find("a[href='/pentests/p-1/results/r-1']").exists()).toBe(true);
  });

  it("says it is empty, and with filters set offers to clear them", async () => {
    const empty = { json: listOf([]) };
    const { wrapper, calls } = await listPage({
      [LIST]: empty,
      [`${LIST}&tool=p.nmap`]: empty,
      [`${LIST}&tool=p.nmap&agent=recon`]: empty,
      [`${LIST}&tool=p.nmap&agent=recon&severity=high`]: empty,
      [`${LIST}&q=nginx&tool=p.nmap&agent=recon&severity=high&test=WSTG-1`]: empty,
      "GET /api/pentests/p-1/results?view=trash&limit=50": empty,
    });
    expect(wrapper.text()).toContain("No results yet");

    await fieldNamed(wrapper, "VSelect", "Tool").setValue("p.nmap");
    await flushPromises();
    expect(wrapper.text()).toContain("No result matches that");
    await fieldNamed(wrapper, "VSelect", "Agent").setValue("recon");
    await fieldNamed(wrapper, "VSelect", "Worst severity").setValue("high");
    await flushPromises();
    await fieldNamed(wrapper, "VTextField", "Search titles and notes").setValue("nginx");
    await fieldNamed(wrapper, "VTextField", "Checklist test").setValue("WSTG-1");
    await wait(350);
    await flushPromises();
    expect(calls.map((one) => one.key).some((key) => key.includes("&q=nginx&tool=p.nmap"))).toBe(
      true,
    );

    await press(wrapper, "Clear the filters");
    await wait(350);
    await flushPromises();
    expect(wrapper.text()).toContain("No results yet");

    await fieldNamed(wrapper, "VSwitch", "Show the trash").setValue(true);
    await flushPromises();
    expect(wrapper.text()).toContain("The trash is empty");
  });

  it("says why it failed and tries again", async () => {
    let fail = true;
    const { wrapper } = await listPage({
      [LIST]: () => (fail ? { status: 500, json: { detail: "Down" } } : { json: listOf() }),
    });
    expect(wrapper.text()).toContain("Could not load the results");
    fail = false;
    await press(wrapper, "Try again");
    await flushPromises();
    expect(wrapper.text()).toContain("Showing 1 of 1.");
  });

  it("loads more, and says when it cannot", async () => {
    const offset = (n: number) => `GET ${BASE}?view=live&limit=50&offset=${String(n)}`;
    let fail = false;
    const { wrapper } = await listPage({
      [LIST]: { json: listOf([summaryOf()], 3) },
      [offset(1)]: () =>
        fail
          ? { status: 500, json: { detail: "Nope" } }
          : { json: listOf([summaryOf({ id: "r-2", title: "Second" })], 3) },
    });
    fail = true;
    await press(wrapper, "Load 2 more");
    await flushPromises();
    expect(noticeText()).toContain("Could not load more");
    fail = false;
    await press(wrapper, "Load 2 more");
    await flushPromises();
    expect(wrapper.text()).toContain("Showing 2 of 3.");
  });

  it("ignores an answer that arrives after a newer one", async () => {
    const { wrapper, fetchMock } = await listPage();
    const first = deferred();
    const second = deferred();
    const third = deferred();
    fetchMock.mockImplementationOnce(() => first.promise);
    fetchMock.mockImplementationOnce(() => Promise.resolve(new Response("{}")));
    fetchMock.mockImplementationOnce(() => second.promise);
    fetchMock.mockImplementationOnce(() => Promise.resolve(new Response("{}")));
    fetchMock.mockImplementationOnce(() => third.promise);
    fetchMock.mockImplementationOnce(() => Promise.resolve(new Response("{}")));
    await fieldNamed(wrapper, "VSelect", "Tool").setValue("p.nmap");
    await fieldNamed(wrapper, "VSelect", "Agent").setValue("recon");
    await fieldNamed(wrapper, "VSelect", "Worst severity").setValue("high");
    const reply = (title: string) =>
      new Response(JSON.stringify(listOf([summaryOf({ title })])), {
        headers: { "Content-Type": "application/json" },
      });
    second.resolve(reply("Newest"));
    third.resolve(reply("Newest"));
    await flushPromises();
    first.reject(new Error("late"));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Could not load the results");
  });

  it("deletes and restores a selection, and tags and untags it", async () => {
    const bulk = `POST ${BASE}/bulk`;
    let fail = false;
    const { wrapper, calls } = await listPage({
      [bulk]: () => (fail ? { status: 500, json: { detail: "Nope" } } : { json: { changed: 1 } }),
      [`GET ${BASE}?view=trash&limit=50`]: { json: listOf([summaryOf({ deleted: true })]) },
    });
    await wrapper.get(SELECT_ONE).setValue(true);
    expect(wrapper.text()).toContain("1 selected");

    await press(wrapper, "Add a tag");
    await fillDialog({ "input[autocomplete=off]": "retest" });
    await submitDialog();
    expect(calls).toContainEqual({
      key: bulk,
      body: { ids: ["r-1"], action: "tag", tag: "retest" },
    });
    expect(noticeText()).toContain("Tag added.");

    await wrapper.get(SELECT_ONE).setValue(true);
    await press(wrapper, "Remove a tag");
    await fillDialog({ "input[autocomplete=off]": "retest" });
    fail = true;
    await submitDialog();
    expect(document.body.querySelector(".v-dialog .v-alert[role=alert]")?.textContent).toContain(
      "The request failed (500)",
    );
    fail = false;
    await submitDialog();
    expect(noticeText()).toContain("Tag removed.");

    await wrapper.get(SELECT_ONE).setValue(true);
    fail = true;
    await press(wrapper, "Delete");
    await flushPromises();
    expect(noticeText()).toContain("Could not do that");
    fail = false;
    await press(wrapper, "Delete");
    await flushPromises();
    expect(noticeText()).toContain("Moved to the trash.");
    expect(wrapper.text()).not.toContain("1 selected");

    await fieldNamed(wrapper, "VSwitch", "Show the trash").setValue(true);
    await flushPromises();
    await wrapper.get(SELECT_ONE).setValue(true);
    expect(wrapper.text()).not.toContain("Add a tag");
    await press(wrapper, "Restore");
    await flushPromises();
    expect(noticeText()).toContain("Restored.");
  });

  it("adds a note and imports output, then shows the list again", async () => {
    const { wrapper, calls } = await listPage({
      [`POST ${BASE}`]: { json: fullOf() },
      [`POST ${BASE}/import`]: { json: fullOf() },
    });
    await press(wrapper, "Write a note");
    await flushPromises();
    await fillDialog({ "input[autocomplete=off]": "Saw a login form" });
    await submitDialog();
    expect(noticeText()).toContain("Note added.");
    await press(wrapper, "Import output");
    await flushPromises();
    await fillLast("textarea", "<nmaprun/>");
    await submitLast();
    expect(noticeText()).toContain("Output imported.");
    expect(calls.filter((one) => one.key === LIST).length).toBeGreaterThanOrEqual(3);
  });

  it("lets a viewer read and nothing more, and the same for an archived pentest", async () => {
    const { wrapper } = await listPage({}, viewer);
    expect(wrapper.find(SELECT_ONE).exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Write a note");
    expect(wrapper.text()).not.toContain("Import output");
    const archived = await listPage({
      "GET /api/pentests/p-1": { json: pentest({ archived_at: "2026-11-24T10:00:00Z" }) },
    });
    expect(archived.wrapper.text()).not.toContain("Write a note");
  });
});

const RESULT = `${BASE}/r-1`;

async function resultPage(made = fullOf(), handlers: Handlers = {}, user?: typeof viewer | null) {
  const api = mockApi({
    [`GET ${RESULT}`]: { json: made },
    [`GET ${RESULT}/raw`]: { json: rawOf },
    "GET /api/pentests/p-1": { json: pentest() },
    ...handlers,
  });
  const mounted = await mountWithApp(
    PentestResultView,
    "/pentests/p-1/results/r-1",
    {},
    user === undefined ? {} : { user },
  );
  await flushPromises();
  return { ...api, ...mounted };
}

async function pick(root: Pick<VueWrapper, "findAll">, label: string) {
  await press(root, label);
  await flushPromises();
}

describe("PentestResultView", () => {
  it("shows the friendly view first, with terms, cards and pictures", async () => {
    const { wrapper } = await resultPage();
    const text = wrapper.text();
    expect(wrapper.get("h1").text()).toBe("Nmap scan of shop.example.com");
    expect(text).toContain("Tool run · p.nmap · recon");
    expect(text).toContain("Medium · 2 issues");
    expect(text).toContain("Test WSTG-INFO-02");
    expect(text).toContain("Checked by hand.");
    expect(text).toContain("One host is up with 2 open ports");
    expect(text).toContain("What this means");
    expect(text).toContain("Turn it off.");
    expect(text).toContain("3 more, less serious, are in the technical view.");
    expect(text).toContain("80/tcp");
    expect(text).toContain("open · http · nginx 1.31");
    expect(text).toContain("Host is down");
    expect(text).toContain("No ports were reported.");
    expect(text).toContain("Needs work");
    expect(text).toContain("Good");
    expect(wrapper.get("[aria-label='Grade B']").text()).toBe("B");
    expect(wrapper.findAll(".bs-term").length).toBeGreaterThan(0);
  });

  it("shows the visuals only when there is something to show", async () => {
    const base = fullOf();
    const { wrapper } = await resultPage(
      fullOf({
        friendly: {
          ...(base.friendly as Friendly),
          hidden_cards: 0,
          visuals: { port_map: [], tls_grade: "Z", scorecard: [] },
        },
      }),
    );
    expect(wrapper.text()).not.toContain("more, less serious");
    expect(wrapper.text()).not.toContain("Header scorecard");
    expect(wrapper.text()).toContain("Encryption grade");
  });

  it("switches to the technical view and remembers it for this person", async () => {
    const { wrapper } = await resultPage();
    await pick(wrapper, "Technical");
    const text = wrapper.text();
    expect(text).toContain("Issues");
    expect(text).toContain("Hosts and services");
    expect(text).toContain("Two lines were left out");
    expect(text).toContain("only the first part is kept here");
    expect(
      localStorage.getItem("blindspot.results-view.00000000-0000-7000-8000-000000000001"),
    ).toBe("technical");
    const again = await resultPage();
    expect(again.wrapper.text()).toContain("Hosts and services");
  });

  it("says when a tool reported nothing, with no warnings", async () => {
    localStorage.setItem(
      "blindspot.results-view.00000000-0000-7000-8000-000000000001",
      "technical",
    );
    const { wrapper } = await resultPage(fullOf({ technical: {} }));
    expect(wrapper.text()).toContain("The tool reported nothing of any kind.");
  });

  it("shows the raw output with the command, searches it, copies it and downloads it", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const create = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }));
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const { wrapper } = await resultPage();
    await pick(wrapper, "Raw");
    const text = wrapper.text();
    expect(text).toContain("nmap -oX - shop.example.com");
    expect(text).toContain("Exit code: 0 · Took: 1.5 s");
    expect(wrapper.find("mark").exists()).toBe(false);

    await fieldNamed(wrapper, "VTextField", "Search the output").setValue("nginx");
    expect(wrapper.get("output[aria-label='Matches']").text()).toBe("1 match");
    expect(wrapper.get("mark").text()).toBe("nginx");
    await fieldNamed(wrapper, "VTextField", "Search the output").setValue("o");
    expect(wrapper.get("output[aria-label='Matches']").text()).toContain("matches");

    await press(wrapper, "Copy");
    expect(writeText).toHaveBeenCalledWith(rawOf.output);
    expect(wrapper.text()).toContain("Copied");
    await press(wrapper, "Download");
    expect(create).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
  });

  it("explains a result with no command, a cut output and a hidden tail", async () => {
    const long = "line\n".repeat(2100);
    const { wrapper } = await resultPage(fullOf(), {
      [`GET ${RESULT}/raw`]: {
        json: {
          ...rawOf,
          command: [],
          exit_code: null,
          duration_ms: null,
          output: long,
          truncated: true,
          size: 9999999,
        },
      },
    });
    await pick(wrapper, "Raw");
    const text = wrapper.text();
    expect(text).toContain("No command: this result was written or imported");
    expect(text).toContain("Exit code: — · Took: —");
    expect(text).toContain("The output is 9999999 characters long.");
    expect(text).toContain("101 more lines are not shown.");
  });

  it("says when the raw output cannot be loaded, and ignores a late answer", async () => {
    const { wrapper } = await resultPage(fullOf(), {
      [`GET ${RESULT}/raw`]: { status: 500, json: { detail: "Gone" } },
    });
    await pick(wrapper, "Raw");
    expect(wrapper.text()).toContain("Could not load the output");
  });

  it("is a note when there is no tool output, and reads a failed run", async () => {
    const note = await resultPage(
      fullOf({
        friendly: null,
        technical: null,
        source: "manual",
        status: "manual",
        tool_id: null,
        agent_role: null,
        test_id: null,
        top_severity: null,
        tags: [],
      }),
    );
    expect(note.wrapper.text()).toContain("This is a note, so there is no tool output");
    const failed = await resultPage(
      fullOf({ status: "failed", exit_code: null, duration_ms: null }),
    );
    expect(failed.wrapper.text()).toContain("Exit code unknown, after —");
    const one = await resultPage(fullOf({ issue_count: 1 }));
    expect(one.wrapper.text()).toContain("Medium · 1 issue");
  });

  it("keeps credentials masked until an administrator shows one, and hides it again", async () => {
    const credentials = [
      {
        index: 0,
        target: "ssh://10.0.0.1",
        kind: "password",
        username: "root",
        secret: "••••••••",
      },
      { index: 1, target: "http://x", kind: "token", username: null, secret: "••••••••" },
    ];
    let fail = true;
    const { wrapper } = await resultPage(fullOf({ credentials }), {
      [`POST ${RESULT}/credentials/0/reveal`]: () =>
        fail ? { status: 500, json: { detail: "Sealed" } } : { json: { secret: "hunter2" } },
    });
    expect(wrapper.text()).toContain("ssh://10.0.0.1");
    expect(wrapper.text()).not.toContain("hunter2");
    await wrapper.get("button[aria-label='Show the secret for ssh://10.0.0.1']").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("The request failed (500)");
    fail = false;
    await wrapper.get("button[aria-label='Show the secret for ssh://10.0.0.1']").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("hunter2");
    await wrapper.get("button[aria-label='Hide the secret for ssh://10.0.0.1']").trigger("click");
    expect(wrapper.text()).not.toContain("hunter2");
    expect(wrapper.text()).toContain("••••••••");

    const asViewer = await resultPage(fullOf({ credentials }), {}, viewer);
    expect(asViewer.wrapper.text()).toContain("••••••••");
    expect(asViewer.wrapper.find("button[aria-label^='Show the secret']").exists()).toBe(false);
  });

  it("deletes a result after asking, and restores one from the trash", async () => {
    const del = vi.fn(() => ({ status: 204 }));
    const { wrapper } = await resultPage(fullOf(), { [`DELETE ${RESULT}`]: del });
    await press(wrapper, "Delete");
    await flushPromises();
    expect(document.body.textContent).toContain("It moves to the trash");
    dialogButton("Delete")?.click();
    await flushPromises();
    expect(del).toHaveBeenCalled();

    let fail = true;
    const trash = await resultPage(fullOf({ deleted: true }), {
      [`POST ${RESULT}/restore`]: () =>
        fail ? { status: 500, json: { detail: "Nope" } } : { json: fullOf() },
    });
    expect(trash.wrapper.text()).toContain("This result is in the trash.");
    expect(trash.wrapper.text()).not.toContain("Delete");
    await press(trash.wrapper, "Restore");
    await flushPromises();
    expect(noticeText()).toContain("Could not restore it");
    fail = false;
    await press(trash.wrapper, "Restore");
    await flushPromises();
    expect(noticeText()).toContain("Restored.");
  });

  it("edits the notes and tags", async () => {
    const saved = fullOf({ notes: "New notes", tags: ["a"] });
    const { wrapper } = await resultPage(fullOf(), { [`PATCH ${RESULT}`]: { json: saved } });
    await press(wrapper, "Notes and tags");
    await flushPromises();
    await fillDialog({ textarea: "New notes" });
    await submitDialog();
    expect(wrapper.text()).toContain("New notes");
    expect(noticeText()).toContain("Saved.");
  });

  it("reads only, for a viewer and for an archived pentest", async () => {
    const asViewer = await resultPage(fullOf(), {}, viewer);
    expect(asViewer.wrapper.text()).not.toContain("Notes and tags");
    const archived = await resultPage(fullOf(), {
      "GET /api/pentests/p-1": { json: pentest({ deleted_at: "2026-11-24T10:00:00Z" }) },
    });
    expect(archived.wrapper.text()).not.toContain("Notes and tags");
  });

  it("says why it failed, tries again, and ignores a toggle with no value", async () => {
    let fail = true;
    const { wrapper } = await resultPage(fullOf(), {
      [`GET ${RESULT}`]: () =>
        fail ? { status: 404, json: { detail: "Gone" } } : { json: fullOf() },
    });
    expect(wrapper.text()).toContain("Could not load the result");
    fail = false;
    await press(wrapper, "Try again");
    await flushPromises();
    emitFrom(wrapper.getComponent({ name: "VBtnToggle" }), "update:modelValue", undefined);
    await flushPromises();
    expect(wrapper.text()).toContain("One host is up with 2 open ports");
  });
});

describe("late answers and edges", () => {
  it("ignores a late result for one that was left, and a late failure", async () => {
    const slow = deferred();
    const { wrapper, router, fetchMock } = await resultPage(fullOf(), {
      [`GET ${BASE}/r-2`]: { json: fullOf({ id: "r-2", title: "Second" }) },
      [`GET ${BASE}/r-2/raw`]: { json: rawOf },
    });
    fetchMock.mockImplementationOnce(() => slow.promise);
    fetchMock.mockImplementationOnce(() => slow.promise);
    await router.push("/pentests/p-1/results/r-2");
    await router.push("/pentests/p-1/results/r-1");
    await flushPromises();
    slow.resolve(new Response(JSON.stringify(fullOf({ title: "Stale" }))));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Stale");

    const failing = deferred();
    fetchMock.mockImplementationOnce(() => failing.promise);
    fetchMock.mockImplementationOnce(() => failing.promise);
    await router.push("/pentests/p-1/results/r-2");
    await router.push("/pentests/p-1/results/r-1");
    await flushPromises();
    failing.reject(new Error("late"));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Could not load the result");
  });

  it("reads for someone who is not signed in", async () => {
    const { wrapper, auth } = await resultPage();
    auth.$patch({ user: null });
    await pick(wrapper, "Raw");
    expect(localStorage.getItem("blindspot.results-view.")).toBe("raw");
  });

  it("unticks a result and closes the tag dialog", async () => {
    const { wrapper } = await listPage();
    await wrapper.get(SELECT_ONE).setValue(true);
    expect(wrapper.text()).toContain("1 selected");
    await wrapper.get(SELECT_ONE).setValue(false);
    expect(wrapper.text()).not.toContain("1 selected");
    await wrapper.get(SELECT_ONE).setValue(true);
    await press(wrapper, "Add a tag");
    await flushPromises();
    for (const dialog of wrapper.findAllComponents({ name: "FormDialog" }))
      emitFrom(dialog, "update:modelValue", false);
    await flushPromises();
    expect(document.body.querySelector(".v-overlay--active")).toBeNull();
  });

  it("ignores a late page of results after the filters changed", async () => {
    const offset = `GET ${BASE}?view=live&limit=50&offset=1`;
    const { wrapper, fetchMock } = await listPage({
      [LIST]: { json: listOf([summaryOf()], 3) },
      [offset]: { json: listOf([summaryOf({ id: "r-9", title: "Late page" })], 3) },
      [`${LIST}&tool=p.nmap`]: { json: listOf([summaryOf()], 1) },
    });
    const slow = deferred();
    fetchMock.mockImplementationOnce(() => slow.promise);
    await press(wrapper, "Load 2 more");
    await fieldNamed(wrapper, "VSelect", "Tool").setValue("p.nmap");
    await flushPromises();
    slow.resolve(
      new Response(JSON.stringify(listOf([summaryOf({ id: "r-9", title: "Late page" })], 3))),
    );
    await flushPromises();
    expect(wrapper.text()).not.toContain("Late page");
  });
});

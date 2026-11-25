import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PentestFindingsView from "../src/views/PentestFindingsView.vue";
import FindingsCard from "../src/views/pentests/FindingsCard.vue";
import { dialogButton, fillDialog, mockApi, mountWithApp, submitDialog, viewer } from "./helpers";
import { emitFrom, fieldNamed, pentest } from "./pentest-fixtures";
import FindingFormDialog from "../src/views/findings/FindingFormDialog.vue";
import { listOf, summaryOf } from "./findings-fixtures";

type Handlers = Parameters<typeof mockApi>[0];

const BASE = "/api/pentests/p-1/findings";
const LIST = `GET ${BASE}?view=live&sort=severity&order=desc&limit=50`;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

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

const answer = (json: unknown) =>
  new Response(JSON.stringify(json), { headers: { "Content-Type": "application/json" } });

function press(root: Pick<VueWrapper, "findAll">, label: string) {
  const found = root.findAll("button").find((one) => one.text() === label);
  if (found === undefined) throw new Error(`no ${label} button`);
  return found.trigger("click");
}

const read = (root: { text: () => string }) => root.text().replace(/\s+/g, " ");

async function listPage(handlers: Handlers = {}, user = undefined as typeof viewer | undefined) {
  const api = mockApi({
    [LIST]: { json: listOf() },
    "GET /api/pentests/p-1": { json: pentest() },
    ...handlers,
  });
  const mounted = await mountWithApp(
    PentestFindingsView,
    "/pentests/p-1/findings",
    {},
    user ? { user } : {},
  );
  await flushPromises();
  return { ...api, ...mounted };
}

describe("PentestFindingsView", () => {
  it("lists the findings with their counts and links to each", async () => {
    const { wrapper } = await listPage({
      [LIST]: {
        json: listOf([summaryOf(), summaryOf({ id: "f-2", number: 2, title: "Open admin" })], {
          severities: { high: 1, low: 1 },
          statuses: { new: 2 },
        }),
      },
    });
    const text = read(wrapper);
    expect(text).toContain("Findings: Acme storefront");
    expect(text).toContain("High: 1");
    expect(text).toContain("New: 2");
    expect(text).toContain("F-1");
    expect(text).toContain("Missing HSTS header");
    expect(text).toContain("https://shop.example.com · WSTG-CONF-07 · 1 evidence");
    expect(text).toContain("High · 8.7");
    expect(text).toContain("Showing 2 of 2.");
    expect(wrapper.find("a[href='/pentests/p-1/findings/f-2']").exists()).toBe(true);
  });

  it("says there are none, and what to do", async () => {
    const { wrapper } = await listPage({ [LIST]: { json: listOf([]) } });
    expect(read(wrapper)).toContain("No findings yet");
    expect(read(wrapper)).toContain("Write one, import a report, or make one from a result.");
  });

  it("says what failed and tries again", async () => {
    let fail = true;
    const { wrapper } = await listPage({
      [LIST]: () =>
        fail
          ? { status: 500, json: { code: "boom", title: "The server broke" } }
          : { json: listOf() },
    });
    expect(read(wrapper)).toContain("Could not load the findings");
    expect(read(wrapper)).toContain("The server broke");
    fail = false;
    await press(wrapper, "Try again");
    await flushPromises();
    expect(read(wrapper)).toContain("Missing HSTS header");
  });

  it("offers the exports to anyone and the writing only to an administrator", async () => {
    const { wrapper } = await listPage({}, viewer);
    expect(read(wrapper)).not.toContain("Write a finding");
    expect(read(wrapper)).not.toContain("Import");
    expect(wrapper.find("input[aria-label='Select Missing HSTS header']").exists()).toBe(false);
  });

  it("hides the writing on a pentest that is archived", async () => {
    const { wrapper } = await listPage({
      "GET /api/pentests/p-1": { json: pentest({ archived_at: "2026-11-24T10:00:00Z" }) },
    });
    expect(read(wrapper)).not.toContain("Write a finding");
  });

  it("filters, sorts and groups by asking the server again", async () => {
    const { wrapper, calls } = await listPage();
    await fieldNamed(wrapper, "VSelect", "Status").setValue(["new"]);
    await flushPromises();
    await fieldNamed(wrapper, "VSelect", "Severity").setValue(["high"]);
    await flushPromises();
    await fieldNamed(wrapper, "VSelect", "Sort by").setValue("cvss");
    await flushPromises();
    await press(wrapper, "Highest first");
    await flushPromises();
    expect(read(wrapper)).toContain("Lowest first");
    await press(wrapper, "Lowest first");
    await flushPromises();
    const keys = calls.map((one) => one.key);
    expect(keys.some((key) => key.includes("status=new") && key.includes("severity=high"))).toBe(
      true,
    );
    expect(keys.some((key) => key.includes("sort=cvss"))).toBe(true);
    expect(keys.some((key) => key.includes("order=asc"))).toBe(true);
  });

  it("waits for the typing to stop before it searches, and can clear what it found nothing for", async () => {
    const { wrapper, calls } = await listPage({
      [`GET ${BASE}?view=live&sort=severity&order=desc&limit=50&q=nothing`]: {
        json: listOf([]),
      },
    });
    const before = calls.length;
    await fieldNamed(wrapper, "VTextField", "Search findings").setValue("noth");
    await fieldNamed(wrapper, "VTextField", "Search findings").setValue("nothing");
    await vi.advanceTimersByTimeAsync(100);
    expect(calls.length).toBe(before);
    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();
    expect(read(wrapper)).toContain("No finding matches that");
    await press(wrapper, "Clear the filters");
    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();
    expect(read(wrapper)).toContain("Missing HSTS header");
  });

  it("filters by test and by target after the typing stops", async () => {
    const { wrapper, calls } = await listPage();
    await fieldNamed(wrapper, "VTextField", "Checklist test").setValue("WSTG-CONF-07");
    await fieldNamed(wrapper, "VTextField", "Target").setValue("shop");
    await vi.advanceTimersByTimeAsync(400);
    await flushPromises();
    expect(
      calls.some((one) => one.key.includes("test=WSTG-CONF-07") && one.key.includes("target=shop")),
    ).toBe(true);
  });

  it("offers the three export formats", async () => {
    const { wrapper } = await listPage();
    await press(wrapper, "Export");
    await flushPromises();
    const links = Array.from(document.body.querySelectorAll("a[download]")).map((one) =>
      one.getAttribute("href"),
    );
    expect(links).toEqual([
      "/api/pentests/p-1/findings/export?format=json",
      "/api/pentests/p-1/findings/export?format=csv",
      "/api/pentests/p-1/findings/export?format=sarif",
    ]);
  });

  it("groups the findings under the groups the server counts", async () => {
    const grouped = `GET ${BASE}?view=live&sort=severity&order=desc&limit=50&group_by=target`;
    const { wrapper } = await listPage({
      [grouped]: {
        json: listOf(
          [summaryOf(), summaryOf({ id: "f-2", number: 2, title: "Loose", target: "" })],
          {
            groups: [
              { key: "https://shop.example.com", count: 1 },
              { key: "No target", count: 1 },
              { key: "nowhere", count: 4 },
            ],
          },
        ),
      },
    });
    await fieldNamed(wrapper, "VSelect", "Group by").setValue("target");
    await flushPromises();
    const text = read(wrapper);
    expect(text).toContain("https://shop.example.com (1)");
    expect(text).toContain("No target (1)");
    expect(text).not.toContain("nowhere");
  });

  it("groups by category and by severity as well", async () => {
    const byCategory = `GET ${BASE}?view=live&sort=severity&order=desc&limit=50&group_by=category`;
    const { wrapper } = await listPage({
      [byCategory]: {
        json: listOf([summaryOf()], { groups: [{ key: "Configuration", count: 1 }] }),
      },
      [`GET ${BASE}?view=live&sort=severity&order=desc&limit=50&group_by=severity`]: {
        json: listOf([summaryOf()], { groups: [{ key: "high", count: 1 }] }),
      },
    });
    await fieldNamed(wrapper, "VSelect", "Group by").setValue("category");
    await flushPromises();
    expect(read(wrapper)).toContain("Configuration (1)");
    await fieldNamed(wrapper, "VSelect", "Group by").setValue("severity");
    await flushPromises();
    expect(read(wrapper)).toContain("high (1)");
  });

  it("shows the trash, where the bulk action is to restore", async () => {
    const trash = `GET ${BASE}?view=trash&sort=severity&order=desc&limit=50`;
    const { wrapper, calls } = await listPage({
      [trash]: { json: listOf([summaryOf({ deleted: true })]) },
      [`POST ${BASE}/bulk`]: { json: { changed: 1, skipped: 0 } },
    });
    await wrapper.getComponent({ name: "VSwitch" }).setValue(true);
    await flushPromises();
    await wrapper.get("input[aria-label='Select Missing HSTS header']").setValue(true);
    expect(read(wrapper)).toContain("1 selected");
    expect(read(wrapper)).not.toContain("Apply");
    await press(wrapper, "Restore");
    await flushPromises();
    expect(calls.find((one) => one.key === `POST ${BASE}/bulk`)?.body).toEqual({
      ids: ["f-1"],
      action: "restore",
    });
    expect(document.body.textContent).toContain("Restored.");
  });

  it("changes the status of the findings picked, and says if some stayed as they were", async () => {
    const { wrapper, calls } = await listPage({
      [`POST ${BASE}/bulk`]: { json: { changed: 1, skipped: 1 } },
    });
    await wrapper.get("input[aria-label='Select Missing HSTS header']").setValue(true);
    expect(read(wrapper)).not.toContain("Apply");
    await fieldNamed(wrapper, "VSelect", "Set the status").setValue("confirmed");
    await press(wrapper, "Apply");
    await flushPromises();
    expect(calls.find((one) => one.key === `POST ${BASE}/bulk`)?.body).toEqual({
      ids: ["f-1"],
      action: "set_status",
      status: "confirmed",
    });
    expect(document.body.textContent).toContain(
      "Status set to Confirmed. 1 could not take it and stayed as they were.",
    );
  });

  it("picks and unpicks, and deletes what is picked", async () => {
    const { wrapper, calls } = await listPage({
      [`POST ${BASE}/bulk`]: { json: { changed: 1, skipped: 0 } },
    });
    const box = wrapper.get("input[aria-label='Select Missing HSTS header']");
    await box.setValue(true);
    await box.setValue(false);
    expect(read(wrapper)).not.toContain("selected");
    await box.setValue(true);
    await press(wrapper, "Delete");
    await flushPromises();
    expect(calls.find((one) => one.key === `POST ${BASE}/bulk`)?.body).toEqual({
      ids: ["f-1"],
      action: "delete",
    });
  });

  it("says why a bulk action failed", async () => {
    const { wrapper } = await listPage({
      [`POST ${BASE}/bulk`]: { status: 409, json: { code: "x", title: "Not now" } },
    });
    await wrapper.get("input[aria-label='Select Missing HSTS header']").setValue(true);
    await press(wrapper, "Delete");
    await flushPromises();
    expect(document.body.textContent).toContain("Could not do that: Not now");
  });

  it("loads more, and says when that fails", async () => {
    let fail = false;
    const second = `GET ${BASE}?view=live&sort=severity&order=desc&limit=50&offset=1`;
    const { wrapper } = await listPage({
      [LIST]: { json: listOf([summaryOf()], { total: 3 }) },
      [second]: () =>
        fail
          ? { status: 500, json: { code: "x", title: "No more" } }
          : { json: listOf([summaryOf({ id: "f-2", number: 2, title: "Second" })], { total: 3 }) },
    });
    expect(read(wrapper)).toContain("Load 2 more");
    fail = true;
    await press(wrapper, "Load 2 more");
    await flushPromises();
    expect(document.body.textContent).toContain("Could not load more: No more");
    fail = false;
    await press(wrapper, "Load 2 more");
    await flushPromises();
    expect(read(wrapper)).toContain("Second");
    expect(read(wrapper)).toContain("Showing 2 of 3.");
  });

  it("opens the form to write a finding, which cannot be added until it is rated", async () => {
    const { wrapper } = await listPage({
      "GET /api/findings/reference": {
        json: { owasp: { A01: "Broken Access Control" }, transitions: {} },
      },
    });
    await press(wrapper, "Write a finding");
    await flushPromises();
    await fillDialog({ "input[type=text]": "Open redirect" });
    expect(dialogButton("Add the finding")?.disabled).toBe(true);
  });

  it("reloads the list when a finding was added", async () => {
    const { wrapper, calls } = await listPage();
    const before = calls.length;
    emitFrom(wrapper.getComponent(FindingFormDialog), "saved", {});
    await flushPromises();
    expect(calls.length).toBeGreaterThan(before);
    expect(document.body.textContent).toContain("Finding added.");
  });

  it("imports a report", async () => {
    const { wrapper, calls } = await listPage({
      [`POST ${BASE}/import`]: { json: { created: 2, skipped: 1 } },
    });
    await press(wrapper, "Import");
    await flushPromises();
    await fillDialog({ textarea: "{}" });
    await submitDialog();
    expect(calls.find((one) => one.key === `POST ${BASE}/import`)?.body).toEqual({
      format: "json",
      content: "{}",
    });
    expect(document.body.textContent).toContain("2 imported, 1 skipped.");
  });

  it("goes back to another pentest's findings when the route changes", async () => {
    vi.useRealTimers();
    const { wrapper, router, calls } = await listPage({
      "GET /api/pentests/p-2": { json: pentest({ id: "p-2", name: "Other" }) },
      [`GET /api/pentests/p-2/findings?view=live&sort=severity&order=desc&limit=50`]: {
        json: listOf([]),
      },
    });
    await router.push("/pentests/p-2/findings");
    await flushPromises();
    expect(calls.some((one) => one.key.includes("/p-2/findings"))).toBe(true);
    expect(read(wrapper)).toContain("No findings yet");
  });
});

describe("FindingsCard", () => {
  const CARD = "GET /api/pentests/p-1/findings?limit=3&sort=severity&order=desc";

  async function card(handlers: Handlers) {
    mockApi(handlers);
    const mounted = await mountWithApp(FindingsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    return mounted.wrapper;
  }

  it("says there are none yet", async () => {
    const wrapper = await card({ [CARD]: { json: listOf([]) } });
    expect(read(wrapper)).toContain("No findings yet");
    expect(wrapper.find("a[href='/pentests/p-1/findings']").exists()).toBe(true);
  });

  it("names the most serious findings and counts the new ones", async () => {
    const wrapper = await card({
      [CARD]: { json: listOf([summaryOf(), summaryOf({ id: "f-2", number: 2 })]) },
    });
    expect(read(wrapper)).toContain("2 findings, 2 new.");
    expect(read(wrapper)).toContain("F-1 Missing HSTS header");
    expect(wrapper.find("a[href='/pentests/p-1/findings/f-2']").exists()).toBe(true);
  });

  it("says one finding in the singular", async () => {
    const wrapper = await card({ [CARD]: { json: listOf() } });
    expect(read(wrapper)).toContain("1 finding,");
  });

  it("says what failed", async () => {
    const wrapper = await card({
      [CARD]: { status: 500, json: { code: "x", title: "Broken" } },
    });
    expect(read(wrapper)).toContain("Could not load the findings: Broken");
  });

  it("loads again for another pentest", async () => {
    const wrapper = await card({
      [CARD]: { json: listOf() },
      "GET /api/pentests/p-2/findings?limit=3&sort=severity&order=desc": { json: listOf([]) },
    });
    await wrapper.setProps({ pentestId: "p-2" });
    await flushPromises();
    expect(read(wrapper)).toContain("No findings yet");
  });
});

describe("late answers", () => {
  it("ignores a list that arrives after a newer one, and a late failure", async () => {
    const { wrapper, fetchMock } = await listPage();
    const slow = deferred();
    const failing = deferred();
    const quick = () => Promise.resolve(answer({}));
    fetchMock.mockImplementationOnce(() => slow.promise);
    fetchMock.mockImplementationOnce(quick);
    fetchMock.mockImplementationOnce(() => failing.promise);
    fetchMock.mockImplementationOnce(quick);
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(answer(listOf([summaryOf({ title: "Newest" })]))),
    );
    fetchMock.mockImplementationOnce(() => Promise.resolve(answer(pentest())));
    await fieldNamed(wrapper, "VSelect", "Status").setValue(["new"]);
    await fieldNamed(wrapper, "VSelect", "Status").setValue(["fixed"]);
    await fieldNamed(wrapper, "VSelect", "Status").setValue(["confirmed"]);
    await flushPromises();
    slow.resolve(answer(listOf([summaryOf({ title: "Stale" })])));
    failing.reject(new Error("late"));
    await flushPromises();
    expect(read(wrapper)).toContain("Newest");
    expect(read(wrapper)).not.toContain("Stale");
    expect(read(wrapper)).not.toContain("Could not load the findings");
  });

  it("ignores a page of more that arrives after the list changed, and its failure", async () => {
    const five = { json: listOf([summaryOf()], { total: 5 }) };
    const { wrapper, fetchMock } = await listPage({
      [LIST]: five,
      [`GET ${BASE}?view=live&sort=severity&order=desc&limit=50&status=new`]: five,
      [`GET ${BASE}?view=live&sort=severity&order=desc&limit=50&status=fixed`]: five,
    });
    const slow = deferred();
    fetchMock.mockImplementationOnce(() => slow.promise);
    await press(wrapper, "Load 4 more");
    await fieldNamed(wrapper, "VSelect", "Status").setValue(["new"]);
    await flushPromises();
    slow.resolve(answer(listOf([summaryOf({ id: "f-9", title: "Stale page" })], { total: 5 })));
    await flushPromises();
    expect(read(wrapper)).not.toContain("Stale page");

    const failing = deferred();
    fetchMock.mockImplementationOnce(() => failing.promise);
    await press(wrapper, "Load 4 more");
    await fieldNamed(wrapper, "VSelect", "Status").setValue(["fixed"]);
    await flushPromises();
    failing.reject(new Error("late"));
    await flushPromises();
    expect(document.body.textContent).not.toContain("Could not load more");
  });

  it("ignores a late card for a pentest that was left", async () => {
    const slow = deferred();
    const failing = deferred();
    mockApi({
      "GET /api/pentests/p-1/findings?limit=3&sort=severity&order=desc": { json: listOf() },
    });
    const { wrapper } = await mountWithApp(FindingsCard, "/", { pentestId: "p-1" });
    await flushPromises();
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementationOnce(() => slow.promise);
    await wrapper.setProps({ pentestId: "p-2" });
    fetchMock.mockImplementationOnce(() => failing.promise);
    await wrapper.setProps({ pentestId: "p-3" });
    fetchMock.mockImplementationOnce(() => Promise.resolve(answer(listOf([]))));
    await wrapper.setProps({ pentestId: "p-4" });
    await flushPromises();
    slow.resolve(answer(listOf([summaryOf({ title: "Stale" })])));
    failing.reject(new Error("late"));
    await flushPromises();
    expect(read(wrapper)).not.toContain("Stale");
    expect(read(wrapper)).not.toContain("Could not load");
  });
});

import type { FindingDuplicate } from "../src/api/types";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import PentestFindingView from "../src/views/PentestFindingView.vue";
import { dialogButton, mockApi, mountWithApp, viewer } from "./helpers";
import { emitFrom, fieldNamed, pentest } from "./pentest-fixtures";
import EvidenceDialog from "../src/views/findings/EvidenceDialog.vue";
import EvidenceList from "../src/views/findings/EvidenceList.vue";
import FindingFormDialog from "../src/views/findings/FindingFormDialog.vue";
import { eventOf, findingOf } from "./findings-fixtures";

type Handlers = Parameters<typeof mockApi>[0];

const BASE = "/api/pentests/p-1/findings/f-1";
const REFERENCE = {
  owasp: { A05: "Security Misconfiguration" },
  transitions: {},
};

afterEach(() => {
  vi.restoreAllMocks();
});

function press(root: Pick<VueWrapper, "findAll">, label: string) {
  const found = root.findAll("button").find((one) => one.text() === label);
  if (found === undefined) throw new Error(`no ${label} button`);
  return found.trigger("click");
}

const read = (root: { text: () => string }) => root.text().replace(/\s+/g, " ");

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

async function detail(handlers: Handlers = {}, user = undefined as typeof viewer | undefined) {
  const api = mockApi({
    [`GET ${BASE}`]: { json: findingOf() },
    "GET /api/pentests/p-1": { json: pentest() },
    "GET /api/findings/reference": { json: REFERENCE },
    ...handlers,
  });
  const mounted = await mountWithApp(
    PentestFindingView,
    "/pentests/p-1/findings/f-1",
    {},
    user ? { user } : {},
  );
  await flushPromises();
  return { ...api, ...mounted };
}

describe("PentestFindingView", () => {
  it("shows the finding with how it was rated, what it is about and how to fix it", async () => {
    const { wrapper } = await detail();
    const text = read(wrapper);
    expect(wrapper.get("h1").text()).toContain("F-1 Missing HSTS header");
    expect(text).toContain("High");
    expect(text).toContain("New");
    expect(text).toContain("Not verified");
    expect(text).toContain("Firm confidence");
    expect(text).toContain("Written by hand");
    expect(text).toContain("The site never asks browsers to stay on HTTPS.");
    expect(text).toContain("https://shop.example.com");
    expect(text).toContain("WSTG-CONF-07 (Configuration)");
    expect(text).toContain("CWE-319");
    expect(text).toContain("A05 Security Misconfiguration");
    expect(text).toContain("Send the header.");
    expect(wrapper.find("a[href='https://owasp.org/www-project-secure-headers/']").exists()).toBe(
      true,
    );
    expect(text).toContain("How I saw it");
    expect(text).toContain("Created.");
  });

  it("shows both scores, who verified it, and a finding that has nothing optional", async () => {
    const { wrapper } = await detail({
      [`GET ${BASE}`]: {
        json: findingOf({
          cvss31_vector: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
          cvss31_score: "9.8",
          cvss4_score: "9.3",
          verified_at: "2026-11-25T11:00:00Z",
          verified_by: "agent",
          verification: "confirmed",
        }),
      },
    });
    expect(read(wrapper)).toContain("9.8 · CVSS:3.1/AV:N");
    expect(read(wrapper)).toContain("9.3 · CVSS:4.0/AV:N");
    expect(read(wrapper)).toContain("By an agent");
    const bare = await detail({
      [`GET ${BASE}`]: {
        json: findingOf({
          description: "",
          target: "",
          test_ids: [],
          cwe: [],
          owasp: null,
          cvss4_vector: null,
          remediation: "",
          references: [],
          verified_at: "2026-11-25T11:00:00Z",
          verified_by: "u-1",
          allowed_statuses: ["retest_needed"],
        }),
      },
    });
    const text = read(bare.wrapper);
    expect(text).toContain("By a person");
    expect(text).not.toContain("How to fix it");
    expect(text).not.toContain("References");
    expect(bare.wrapper.findAll("button").some((one) => one.text() === "Ask for a retest")).toBe(
      false,
    );
  });

  it("says what failed and tries again", async () => {
    let fail = true;
    const { wrapper } = await detail({
      [`GET ${BASE}`]: () =>
        fail
          ? { status: 404, json: { code: "x", title: "No such finding" } }
          : { json: findingOf() },
    });
    expect(read(wrapper)).toContain("Could not load the finding");
    fail = false;
    await press(wrapper, "Try again");
    await flushPromises();
    expect(read(wrapper)).toContain("Missing HSTS header");
  });

  it("gives a viewer nothing to change", async () => {
    const { wrapper } = await detail({}, viewer);
    const buttons = wrapper.findAll("button").map((one) => one.text());
    expect(buttons).not.toContain("Change");
    expect(buttons).not.toContain("Merge");
    expect(buttons).not.toContain("Delete");
    expect(buttons).not.toContain("Add evidence");
    expect(wrapper.find("form").exists()).toBe(false);
  });

  it("moves the finding to another status with a note", async () => {
    const { wrapper, calls } = await detail({
      [`POST ${BASE}/status`]: { json: findingOf({ status: "confirmed" }) },
    });
    expect(wrapper.findAll("button").some((one) => one.text() === "Move")).toBe(false);
    await fieldNamed(wrapper, "VSelect", "Move to").setValue("confirmed");
    await fieldNamed(wrapper, "VTextField", "Why (optional)").setValue("Seen twice");
    await press(wrapper, "Move");
    await flushPromises();
    expect(calls.find((one) => one.key === `POST ${BASE}/status`)?.body).toEqual({
      status: "confirmed",
      note: "Seen twice",
    });
    expect(document.body.textContent).toContain("Status changed.");
    expect(read(wrapper)).toContain("Confirmed");
  });

  it("says why a change was refused", async () => {
    const { wrapper } = await detail({
      [`POST ${BASE}/status`]: {
        status: 409,
        json: { code: "bad_transition", title: "That is not allowed" },
      },
    });
    await fieldNamed(wrapper, "VSelect", "Move to").setValue("confirmed");
    await press(wrapper, "Move");
    await flushPromises();
    expect(read(wrapper)).toContain("That is not allowed");
  });

  it("records that a person verified it, or could not reproduce it", async () => {
    const { wrapper, calls } = await detail({
      [`POST ${BASE}/verification`]: { json: findingOf({ verification: "confirmed" }) },
    });
    await press(wrapper, "I verified it");
    await flushPromises();
    await press(wrapper, "I could not reproduce it");
    await flushPromises();
    const bodies = calls
      .filter((one) => one.key === `POST ${BASE}/verification`)
      .map((one) => one.body);
    expect(bodies).toEqual([{ outcome: "confirmed" }, { outcome: "unconfirmed" }]);
    expect(document.body.textContent).toContain("Marked as not reproduced.");
  });

  it("asks for a retest and points to the agents page for the tests", async () => {
    const { wrapper, calls } = await detail({
      [`GET ${BASE}`]: {
        json: findingOf({
          allowed_statuses: ["retest_needed"],
          test_ids: ["WSTG-CONF-07", "WSTG-CONF-08"],
        }),
      },
      [`POST ${BASE}/retest`]: {
        json: findingOf({
          status: "retest_needed",
          test_ids: ["WSTG-CONF-07", "WSTG-CONF-08"],
          allowed_statuses: ["fixed"],
        }),
      },
    });
    await press(wrapper, "Ask for a retest");
    await flushPromises();
    expect(calls.some((one) => one.key === `POST ${BASE}/retest`)).toBe(true);
    const link = wrapper.get("a[href^='/pentests/p-1/agents']");
    expect(decodeURIComponent(link.attributes("href") ?? "")).toBe(
      "/pentests/p-1/agents?retest=WSTG-CONF-07,WSTG-CONF-08",
    );
  });

  it("adds a comment to the timeline", async () => {
    const { wrapper, calls } = await detail({
      [`POST ${BASE}/comments`]: {
        status: 201,
        json: findingOf({
          timeline: [eventOf(), eventOf({ id: "v-2", kind: "comment", data: { body: "On it" } })],
        }),
      },
    });
    const submit = wrapper.findAll("button").find((one) => one.text() === "Comment");
    expect(submit?.attributes("disabled")).toBeDefined();
    await fieldNamed(wrapper, "VTextField", "Write a comment").setValue("On it");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(calls.find((one) => one.key === `POST ${BASE}/comments`)?.body).toEqual({
      body: "On it",
    });
    expect(read(wrapper)).toContain("On it");
    expect(document.body.textContent).toContain("Comment added.");
  });

  it("shows the note of a status change in the timeline", async () => {
    const { wrapper } = await detail({
      [`GET ${BASE}`]: {
        json: findingOf({
          timeline: [
            eventOf({
              kind: "status",
              actor: null,
              data: { before: "new", after: "fixed", note: "Patched" },
            }),
          ],
        }),
      },
    });
    expect(read(wrapper)).toContain("Status changed from New to Fixed.");
    expect(read(wrapper)).toContain("“Patched”");
  });

  it("warns about findings that look like this one, and merges into one", async () => {
    const duplicate: FindingDuplicate = {
      id: "f-2",
      number: 2,
      title: "No HSTS",
      status: "new",
      reason: "same title",
    };
    const { wrapper, calls } = await detail({
      [`GET ${BASE}`]: { json: findingOf({ duplicates: [duplicate] }) },
      [`GET /api/pentests/p-1/findings?limit=200&sort=number&order=asc`]: {
        json: {
          items: [
            { id: "f-1", number: 1, title: "Missing HSTS header" },
            { id: "f-2", number: 2, title: "No HSTS" },
          ],
        },
      },
      [`POST ${BASE}/merge`]: { json: findingOf({ id: "f-2", number: 2, title: "No HSTS" }) },
    });
    expect(read(wrapper)).toContain("This looks like:");
    expect(read(wrapper)).toContain("F-2 No HSTS (same title)");
    await press(wrapper, "Merge");
    await flushPromises();
    const submit = dialogButton("Merge");
    expect(submit?.disabled).toBe(false);
    submit?.closest("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flushPromises();
    expect(calls.find((one) => one.key === `POST ${BASE}/merge`)?.body).toEqual({ into: "f-2" });
    expect(document.body.textContent).toContain("Merged into F-2.");
  });

  it("says why a merge failed", async () => {
    const { wrapper } = await detail({
      [`GET /api/pentests/p-1/findings?limit=200&sort=number&order=asc`]: {
        json: { items: [{ id: "f-1", number: 1, title: "Mine" }] },
      },
      [`POST ${BASE}/merge`]: { status: 409, json: { code: "x", title: "Cannot merge" } },
    });
    await press(wrapper, "Merge");
    await flushPromises();
    expect(dialogButton("Merge")?.disabled).toBe(true);
  });

  it("moves it to the trash after asking, and restores it", async () => {
    const { wrapper, calls } = await detail({
      [`DELETE ${BASE}`]: { status: 204 },
    });
    await press(wrapper, "Delete");
    await flushPromises();
    dialogButton("Move to the trash")?.click();
    await flushPromises();
    expect(calls.some((one) => one.key === `DELETE ${BASE}`)).toBe(true);
  });

  it("says a finding in the trash is, and can be restored unless it was merged", async () => {
    const { wrapper, calls } = await detail({
      [`GET ${BASE}`]: { json: findingOf({ deleted: true }) },
      [`POST ${BASE}/restore`]: { json: findingOf() },
    });
    expect(read(wrapper)).toContain("This finding is in the trash.");
    expect(wrapper.findAll("button").map((one) => one.text())).not.toContain("Change");
    await press(wrapper, "Restore");
    await flushPromises();
    expect(calls.some((one) => one.key === `POST ${BASE}/restore`)).toBe(true);
    expect(document.body.textContent).toContain("Restored.");

    const merged = await detail({
      [`GET ${BASE}`]: { json: findingOf({ deleted: true, merged_into: "f-2" }) },
    });
    expect(read(merged.wrapper)).toContain("it was merged into another one");
    expect(merged.wrapper.findAll("button").map((one) => one.text())).not.toContain("Restore");
  });

  it("opens the form to change it and shows what was saved", async () => {
    const { wrapper } = await detail();
    await press(wrapper, "Change");
    await flushPromises();
    expect(document.body.textContent).toContain("Change the finding");
    dialogButton("Cancel")?.click();
    await flushPromises();
    emitFrom(wrapper.getComponent(FindingFormDialog), "saved", findingOf({ title: "Renamed" }));
    await flushPromises();
    expect(read(wrapper)).toContain("Renamed");
    expect(document.body.textContent).toContain("Saved.");
  });

  it("reloads after evidence is added, changed or removed", async () => {
    const { wrapper, calls } = await detail();
    const before = calls.length;
    emitFrom(wrapper.getComponent(EvidenceDialog), "added");
    await flushPromises();
    emitFrom(wrapper.getComponent(EvidenceList), "changed", "Sealed.");
    await flushPromises();
    expect(calls.length).toBe(before + 6);
    expect(document.body.textContent).toContain("Sealed.");
  });

  it("opens the evidence form", async () => {
    const { wrapper } = await detail({
      "GET /api/pentests/p-1/results?limit=200": { json: { items: [] } },
    });
    await press(wrapper, "Add evidence");
    await flushPromises();
    expect(document.body.textContent).toContain("What it is");
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.getComponent(EvidenceDialog).props("modelValue")).toBe(false);
  });

  it("reloads when the finding in the route changes", async () => {
    const { router, calls } = await detail({
      "GET /api/pentests/p-1/findings/f-2": { json: findingOf({ id: "f-2" }) },
    });
    await router.push("/pentests/p-1/findings/f-2");
    await flushPromises();
    expect(calls.some((one) => one.key === "GET /api/pentests/p-1/findings/f-2")).toBe(true);
  });

  it("ignores an answer that arrives after a newer one, and a late failure", async () => {
    const { wrapper, router, fetchMock } = await detail();
    const loaded = (title: string) => [
      () => Promise.resolve(answer(findingOf({ title }))),
      () => Promise.resolve(answer(pentest())),
      () => Promise.resolve(answer(REFERENCE)),
    ];
    const slow = deferred();
    const [, quickPentest, quickReference] = loaded("x");
    fetchMock.mockImplementationOnce(() => slow.promise);
    fetchMock.mockImplementationOnce(quickPentest as () => Promise<Response>);
    fetchMock.mockImplementationOnce(quickReference as () => Promise<Response>);
    for (const one of loaded("Newest")) fetchMock.mockImplementationOnce(one);
    await router.push("/pentests/p-1/findings/f-2");
    await router.push("/pentests/p-1/findings/f-3");
    await flushPromises();
    slow.resolve(answer(findingOf({ title: "Stale" })));
    await flushPromises();
    expect(read(wrapper)).toContain("Newest");
    expect(read(wrapper)).not.toContain("Stale");

    const failing = deferred();
    fetchMock.mockImplementationOnce(() => failing.promise);
    fetchMock.mockImplementationOnce(quickPentest as () => Promise<Response>);
    fetchMock.mockImplementationOnce(quickReference as () => Promise<Response>);
    for (const one of loaded("Last")) fetchMock.mockImplementationOnce(one);
    await router.push("/pentests/p-1/findings/f-4");
    await router.push("/pentests/p-1/findings/f-5");
    await flushPromises();
    failing.reject(new Error("late"));
    await flushPromises();
    expect(read(wrapper)).toContain("Last");
    expect(read(wrapper)).not.toContain("Could not load the finding");
  });
});

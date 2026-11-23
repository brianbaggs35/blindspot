import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { actionLabel, auditQuery, detailText, NO_FILTERS } from "../src/audit";
import AuditView from "../src/views/AuditView.vue";
import { mockApi, mountWithApp } from "./helpers";

const event = (id: string, extra: object = {}) => ({
  id,
  created_at: "2026-11-21T10:00:00Z",
  actor_id: "a-1",
  actor_name: "ada",
  action: "auth.login",
  outcome: "success",
  target_type: null,
  target_id: null,
  ip_address: "203.0.113.5",
  user_agent: "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0",
  detail: null,
  ...extra,
});

describe("audit helpers", () => {
  it("names the actions it knows and shows others as they are", () => {
    expect(actionLabel("user.delete")).toBe("Deleted an account");
    expect(actionLabel("something.new")).toBe("something.new");
  });

  it("asks only for the filters that are set", () => {
    expect(auditQuery(NO_FILTERS, null)).toBe("limit=50");
    const query = new URLSearchParams(
      auditQuery(
        { action: "user.create", outcome: "failure", actor: " ada ", since: "2026-11-01" },
        "id-9",
        25,
      ),
    );
    expect(query.get("action")).toBe("user.create");
    expect(query.get("outcome")).toBe("failure");
    expect(query.get("actor")).toBe("ada");
    expect(query.get("before")).toBe("id-9");
    expect(query.get("limit")).toBe("25");
    expect(query.get("since")).toBe(new Date("2026-11-01T00:00:00").toISOString());
  });

  it("writes an event's detail on one line", () => {
    expect(detailText(null)).toBe("");
    expect(detailText({ role: "admin", changes: { a: 1 } })).toBe('role: admin, changes: {"a":1}');
  });
});

describe("AuditView", () => {
  it("lists events, newest first, with who, when and from where", async () => {
    mockApi({
      "GET /api/audit?limit=50": {
        json: {
          items: [
            event("e-2", { action: "user.create", detail: { username: "vic" } }),
            event("e-1", {
              actor_name: null,
              ip_address: null,
              user_agent: null,
              outcome: "failure",
            }),
          ],
          next_before: null,
        },
      },
    });
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await flushPromises();
    expect(wrapper.get("h1").text()).toBe("Audit log");
    const rows = wrapper.findAll(".v-list-item");
    expect(rows).toHaveLength(2);
    expect(rows[0]?.text()).toContain("Added an account");
    expect(rows[0]?.text()).toContain("ada");
    expect(rows[0]?.text()).toContain("Chrome on Linux");
    expect(rows[0]?.text()).toContain("username: vic");
    expect(rows[0]?.text()).toContain("succeeded");
    expect(rows[1]?.text()).toContain("Nobody signed in");
    expect(rows[1]?.text()).toContain("failed");
    expect(wrapper.text()).not.toContain("Show older events");
  });

  it("filters, and clears the filters", async () => {
    const { calls } = mockApi({
      "GET /api/audit?limit=50": { json: { items: [event("e-1")], next_before: null } },
      "GET /api/audit?limit=50&outcome=failure&actor=ada": {
        json: { items: [], next_before: null },
      },
    });
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await flushPromises();
    expect(wrapper.text()).not.toContain("Clear");
    await wrapper.get("input[autocomplete=off]").setValue("ada");
    await wrapper.get("input[type=date]").setValue("");
    // The outcome select is set through the component, as a click-through of its menu adds nothing.
    await wrapper.getComponent({ name: "VAutocomplete" }).setValue("");
    await wrapper.getComponent({ name: "VSelect" }).setValue("failure");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(calls.at(-1)?.key).toBe("GET /api/audit?limit=50&outcome=failure&actor=ada");
    expect(wrapper.text()).toContain("Nothing matches");
    expect(wrapper.text()).toContain("No events match these filters");
    const clear = wrapper.findAll("button").find((button) => button.text() === "Clear");
    await clear?.trigger("click");
    await flushPromises();
    expect(calls.at(-1)?.key).toBe("GET /api/audit?limit=50");
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
  });

  it("sends the day to search from", async () => {
    const { calls } = mockApi({
      "GET /api/audit?limit=50": { json: { items: [event("e-1")], next_before: null } },
      [`GET /api/audit?limit=50&since=${encodeURIComponent(new Date("2026-11-01T00:00:00").toISOString())}`]:
        {
          json: { items: [], next_before: null },
        },
    });
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await flushPromises();
    await wrapper.get("input[type=date]").setValue("2026-11-01");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(calls.at(-1)?.key).toContain("&since=2026-11-01T");
    // Nothing matched, so the empty state offers to clear the filters; its button does.
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await flushPromises();
    expect(calls.at(-1)?.key).toBe("GET /api/audit?limit=50");
  });

  it("shows an empty log in words", async () => {
    mockApi({ "GET /api/audit?limit=50": { json: { items: [], next_before: null } } });
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await flushPromises();
    expect(wrapper.text()).toContain("Nothing has been recorded yet");
  });

  it("pages with next_before and keeps what is already shown", async () => {
    const { calls } = mockApi({
      "GET /api/audit?limit=50": { json: { items: [event("e-2")], next_before: "e-2" } },
      "GET /api/audit?limit=50&before=e-2": { json: { items: [event("e-1")], next_before: null } },
    });
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await flushPromises();
    expect(calls.at(-1)?.key).toBe("GET /api/audit?limit=50&before=e-2");
    expect(wrapper.findAll(".v-list-item")).toHaveLength(2);
    expect(wrapper.text()).not.toContain("Show older events");
  });

  it("keeps the page and says so when the next page fails", async () => {
    mockApi({
      "GET /api/audit?limit=50": { json: { items: [event("e-2")], next_before: "e-2" } },
      "GET /api/audit?limit=50&before=e-2": { status: 500, json: { title: "Database is down" } },
    });
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await flushPromises();
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
    expect(wrapper.get(".v-alert[role=alert]").text()).toContain("Database is down");
  });

  it("offers a retry when the log cannot be loaded", async () => {
    let calls = 0;
    mockApi({
      "GET /api/audit?limit=50": () => {
        calls += 1;
        return calls === 1
          ? { status: 500, json: { title: "Database is down" } }
          : { json: { items: [event("e-1")], next_before: null } };
      },
    });
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await flushPromises();
    expect(wrapper.text()).toContain("Could not load the audit log");
    expect(wrapper.text()).toContain("Database is down");
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("Database is down");
  });

  it("drops an answer that arrives after a newer search", async () => {
    const resolvers: ((value: Response) => void)[] = [];
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => resolvers.push(resolve)));
    vi.stubGlobal("fetch", fetchMock);
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await wrapper.get("form").trigger("submit");
    const answer = (items: object[]) =>
      new Response(JSON.stringify({ items, next_before: null }), {
        headers: { "Content-Type": "application/json" },
      });
    resolvers[1]?.(answer([event("e-new")]));
    await flushPromises();
    resolvers[0]?.(answer([event("e-old"), event("e-old-2")]));
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
  });

  it("ignores a failure of the next page that arrives after a new search", async () => {
    const pending: { resolve: (value: Response) => void; reject: (error: Error) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve, reject) => pending.push({ resolve, reject }))),
    );
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    pending[0]?.resolve(
      new Response(JSON.stringify({ items: [event("e-1")], next_before: "e-1" }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await flushPromises();
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await wrapper.get("form").trigger("submit");
    pending[1]?.reject(new Error("late failure"));
    await flushPromises();
    pending[2]?.resolve(
      new Response(JSON.stringify({ items: [event("e-2")], next_before: null }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await flushPromises();
    expect(wrapper.text()).not.toContain("late failure");
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
  });

  it("drops a late failure, and a late next page", async () => {
    const pending: { resolve: (value: Response) => void; reject: (error: Error) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve, reject) => pending.push({ resolve, reject }))),
    );
    const { wrapper } = await mountWithApp(AuditView, "/audit");
    await wrapper.get("form").trigger("submit");
    pending[1]?.resolve(
      new Response(JSON.stringify({ items: [event("e-1")], next_before: "e-1" }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await flushPromises();
    // Start the next page, then search again before it answers.
    await wrapper.get("button.v-btn--variant-tonal").trigger("click");
    await wrapper.get("form").trigger("submit");
    pending[0]?.reject(new Error("late failure"));
    await flushPromises();
    pending[2]?.resolve(
      new Response(JSON.stringify({ items: [event("late")], next_before: null }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    pending[3]?.resolve(
      new Response(JSON.stringify({ items: [event("e-2")], next_before: null }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await flushPromises();
    expect(wrapper.findAll(".v-list-item")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("late failure");
  });
});

import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentsView from "../src/views/AgentsView.vue";
import { dialogButton, mockApi, mountWithApp, viewer } from "./helpers";
import { fieldNamed } from "./pentest-fixtures";
import { budget, overview, prompt, settings, tree } from "./agents-fixtures";

type Handlers = Parameters<typeof mockApi>[0];

afterEach(() => {
  vi.restoreAllMocks();
});

export function press(root: Pick<VueWrapper, "findAll">, label: string) {
  const found = root.findAll("button").find((one) => one.text() === label);
  if (found === undefined) throw new Error(`no ${label} button`);
  return found.trigger("click");
}

export function read(root: { text: () => string }) {
  return root.text().replace(/\s+/g, " ");
}

async function agentsPage(handlers: Handlers = {}, user = undefined as typeof viewer | undefined) {
  const api = mockApi({
    "GET /api/agents/overview": { json: overview() },
    "GET /api/agents/settings": { json: settings() },
    ...handlers,
  });
  const mounted = await mountWithApp(AgentsView, "/agents", {}, user ? { user } : {});
  await flushPromises();
  return { ...api, ...mounted };
}

async function openTab(wrapper: VueWrapper, name: string) {
  const tab = wrapper.findAll("[role=tab]").find((one) => one.text() === name);
  if (tab === undefined) throw new Error(`no ${name} tab`);
  await tab.trigger("click");
  await flushPromises();
}

describe("AgentsView", () => {
  it("shows the commander and every test agent, and says no runner is connected", async () => {
    const { wrapper } = await agentsPage();
    const text = read(wrapper);
    expect(wrapper.get("h1").text()).toBe("Agents");
    expect(text).toContain("No tool runner is connected yet");
    expect(text).toContain("Mission Commander");
    expect(text).toContain("2 missions run · success 50% · $1.50 per mission");
    expect(text).toContain("3 test agents shown.");
    expect(text).toContain("Configuration");
    expect(text).toContain("Authentication");
  });

  it("is quiet about the runner once one is connected", async () => {
    const { wrapper } = await agentsPage({
      "GET /api/agents/overview": { json: overview({ runner_ready: true }) },
    });
    expect(wrapper.text()).not.toContain("No tool runner");
  });

  it("opens each section", async () => {
    const { wrapper } = await agentsPage();
    await openTab(wrapper, "Defaults and presets");
    expect(read(wrapper)).toContain("Caps a mission starts with");
    expect(read(wrapper)).toContain("Passive recon only");
    await openTab(wrapper, "Prompts");
    expect(read(wrapper)).toContain("A prompt is never edited");
    await openTab(wrapper, "Agents");
    expect(read(wrapper)).toContain("Mission Commander");
  });

  it("loads another methodology when one is chosen", async () => {
    const { wrapper, calls } = await agentsPage({
      "GET /api/agents/overview?methodology=house": {
        json: overview({ methodology_id: "house", runner_ready: true }),
      },
    });
    await fieldNamed(wrapper, "VSelect", "Methodology").setValue("house");
    await flushPromises();
    expect(calls.map((one) => one.key)).toContain("GET /api/agents/overview?methodology=house");
  });

  it("says so when no methodology is on, and still offers the settings", async () => {
    const { wrapper } = await agentsPage({
      "GET /api/agents/overview": {
        json: overview({ methodology_id: null, methodologies: [], commander: null }),
      },
    });
    expect(read(wrapper)).toContain("No methodology is turned on");
    await openTab(wrapper, "Prompts");
    expect(read(wrapper)).toContain("A prompt is never edited");
  });

  it("says what failed and tries again", async () => {
    let fail = true;
    const { wrapper } = await agentsPage({
      "GET /api/agents/overview": () =>
        fail
          ? { status: 500, json: { code: "boom", title: "The server broke" } }
          : { json: overview() },
    });
    expect(read(wrapper)).toContain("Could not load the agents");
    expect(read(wrapper)).toContain("The server broke");
    fail = false;
    await press(wrapper, "Try again");
    await flushPromises();
    expect(read(wrapper)).toContain("Mission Commander");
  });

  it("ignores an answer to an older request", async () => {
    let release: () => void = () => undefined;
    const slow = new Promise<void>((done) => {
      release = done;
    });
    const { wrapper } = await agentsPage({
      "GET /api/agents/overview?methodology=house": () => ({
        json: overview({
          methodology_id: "house",
          commander: { ...tree, name: "Stale commander" },
        }),
      }),
      "GET /api/agents/overview?methodology=wstg": { json: overview() },
    });
    const original = globalThis.fetch;
    vi.stubGlobal("fetch", (input: string, init?: RequestInit) =>
      input.endsWith("=house") ? slow.then(() => original(input, init)) : original(input, init),
    );
    await fieldNamed(wrapper, "VSelect", "Methodology").setValue("house");
    await fieldNamed(wrapper, "VSelect", "Methodology").setValue("wstg");
    await flushPromises();
    release();
    await flushPromises();
    expect(read(wrapper)).toContain("Mission Commander");
    expect(read(wrapper)).not.toContain("Stale commander");
  });
});

describe("the agent catalog", () => {
  it("narrows by search and by risk, in the grid and the tree", async () => {
    const { wrapper } = await agentsPage();
    await press(wrapper, "Grid");
    expect(read(wrapper)).toContain("WSTG-CONF-01 Network configuration");
    expect(read(wrapper)).toContain("67%");
    expect(read(wrapper)).toContain("$0.12");
    await fieldNamed(wrapper, "VTextField", "Search agents").setValue("http");
    await flushPromises();
    expect(read(wrapper)).toContain("1 test agent shown.");
    expect(read(wrapper)).not.toContain("Network configuration");
    await fieldNamed(wrapper, "VTextField", "Search agents").setValue("");
    await fieldNamed(wrapper, "VSelect", "Risk").setValue("intrusive");
    await flushPromises();
    expect(read(wrapper)).toContain("Default credentials");
    await fieldNamed(wrapper, "VTextField", "Search agents").setValue("zzz");
    await flushPromises();
    expect(read(wrapper)).toContain("No agent matches that.");
    await fieldNamed(wrapper, "VSelect", "Risk").setValue(null);
    await fieldNamed(wrapper, "VTextField", "Search agents").setValue("");
    await press(wrapper, "Tree");
    const titles = wrapper.findAll(".v-expansion-panel-title");
    expect(titles).toHaveLength(2);
    await titles[0]?.trigger("click");
    await flushPromises();
    const text = read(wrapper);
    expect(text).toContain("WSTG-CONF-01");
    expect(text).toContain("3 runs · success 67% · $0.12 per run · tools: c.nmap");
    expect(text).toContain("Working now");
    expect(text).toContain("Never run");
  });
});

describe("the defaults", () => {
  it("saves changed caps and can put the built-in ones back", async () => {
    let saved: unknown;
    const { wrapper, calls } = await agentsPage({
      "PUT /api/agents/settings/budget": (body) => {
        saved = body;
        return { json: body };
      },
    });
    await openTab(wrapper, "Defaults and presets");
    const save = () => wrapper.findAll("button").find((one) => one.text() === "Save the caps");
    expect(save()?.attributes("disabled")).toBeDefined();
    await fieldNamed(wrapper, "VTextField", "Steps in a mission").setValue("120");
    await flushPromises();
    expect(save()?.attributes("disabled")).toBeUndefined();
    await fieldNamed(wrapper, "VSelect", "Replay findings from").setValue("high");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(saved).toEqual({ ...budget, steps: 120, verify_from: "high" });
    expect(document.body.textContent).toContain("The default caps were saved.");
    expect(calls.filter((one) => one.key === "GET /api/agents/settings").length).toBe(2);
  });

  it("will not save caps the server would refuse", async () => {
    const { wrapper } = await agentsPage();
    await openTab(wrapper, "Defaults and presets");
    await fieldNamed(wrapper, "VTextField", "Steps in a test").setValue("999");
    await flushPromises();
    expect(read(wrapper)).toContain("Steps in a test must be between 1 and 200.");
    expect(
      wrapper
        .findAll("button")
        .find((one) => one.text() === "Save the caps")
        ?.attributes("disabled"),
    ).toBeDefined();
  });

  it("puts the built-in caps back, and says when saving fails", async () => {
    const custom = { ...budget, steps: 50 };
    let fail = true;
    const { wrapper } = await agentsPage({
      "GET /api/agents/settings": { json: settings({ budget: custom }) },
      "PUT /api/agents/settings/budget": () =>
        fail ? { status: 500, json: { code: "boom", title: "Could not save" } } : { json: budget },
    });
    await openTab(wrapper, "Defaults and presets");
    await press(wrapper, "Put back the built-in caps");
    await flushPromises();
    expect(read(wrapper)).toContain("Could not save");
    fail = false;
    await press(wrapper, "Put back the built-in caps");
    await flushPromises();
    expect(document.body.textContent).toContain("The default caps were put back.");
  });

  it("is read-only for a viewer", async () => {
    const { wrapper } = await agentsPage({}, viewer);
    await openTab(wrapper, "Defaults and presets");
    const buttons = wrapper.findAll("button").map((one) => one.text());
    expect(buttons).not.toContain("Save the caps");
    expect(buttons).not.toContain("Put back the built-in caps");
    await openTab(wrapper, "Prompts");
    expect(wrapper.findAll("button").map((one) => one.text())).not.toContain("Add a version");
  });
});

describe("the prompts", () => {
  const BODY = "Line one\nLine two\nLine three";
  const NEW = "Line one\nLine 2\nLine three\nLine four";
  const bodies: Handlers = {
    "GET /api/agents/prompts/test-agent/0": {
      json: { agent: "test-agent", version: 0, note: "Built in", body: BODY },
    },
    "GET /api/agents/prompts/test-agent/1": {
      json: { agent: "test-agent", version: 1, note: "Shorter", body: NEW },
    },
    "GET /api/agents/prompts/verifier/0": {
      json: { agent: "verifier", version: 0, note: "Built in", body: "Check it" },
    },
  };

  async function promptsPage(
    handlers: Handlers = {},
    user = undefined as typeof viewer | undefined,
  ) {
    const page = await agentsPage({ ...bodies, ...handlers }, user);
    await openTab(page.wrapper, "Prompts");
    return page;
  }

  it("lists the versions, shows the text and compares two", async () => {
    const { wrapper } = await promptsPage();
    const text = read(wrapper);
    expect(text).toContain("Built in");
    expect(text).toContain("Version 1");
    expect(text).toContain("Shorter · Ada Admin");
    expect(text).toContain("In use");
    expect(wrapper.get("pre[aria-label='Prompt text']").text()).toBe(BODY);
    await wrapper.findAll(".v-list-item")[1]?.trigger("click");
    await flushPromises();
    expect(wrapper.get("pre[aria-label='Prompt text']").text()).toBe(NEW);
    await fieldNamed(wrapper, "VSelect", "Compare with").setValue(0);
    await flushPromises();
    const diff = wrapper.get("pre[aria-label='Prompt changes']");
    expect(diff.findAll(".bs-removed").map((one) => one.text())).toEqual(["- Line two"]);
    expect(diff.findAll(".bs-added").map((one) => one.text())).toEqual(["+ Line 2", "+ Line four"]);
    expect(read(wrapper)).toContain("Changes from the built-in prompt");
    await fieldNamed(wrapper, "VSelect", "Compare with").setValue(1);
    await wrapper.findAll(".v-list-item")[0]?.trigger("click");
    await flushPromises();
    expect(read(wrapper)).toContain("Changes from version 1");
  });

  it("switches to the other agent's prompts", async () => {
    const { wrapper } = await promptsPage();
    await press(wrapper, "Verifier");
    await flushPromises();
    expect(wrapper.get("pre[aria-label='Prompt text']").text()).toBe("Check it");
  });

  it("chooses a version and puts the built-in one back", async () => {
    const sent: unknown[] = [];
    const { wrapper } = await promptsPage({
      "POST /api/agents/prompts/test-agent/activate": (body) => {
        sent.push(body);
        return { json: prompt("test-agent", 1) };
      },
    });
    await wrapper.get("button[aria-label='Use Version 1']").trigger("click");
    await flushPromises();
    expect(sent).toEqual([{ version: 1 }]);
    expect(document.body.textContent).toContain("Version 1 is in use.");
  });

  it("puts the built-in prompt back when another version is in use", async () => {
    const sent: unknown[] = [];
    const { wrapper } = await promptsPage({
      "GET /api/agents/settings": {
        json: settings({ prompts: [prompt("test-agent", 1), prompt("verifier")] }),
      },
      "POST /api/agents/prompts/test-agent/activate": (body) => {
        sent.push(body);
        return { json: prompt("test-agent", 0) };
      },
    });
    await press(wrapper, "Put back the built-in prompt");
    await flushPromises();
    expect(sent).toEqual([{ version: 0 }]);
    expect(document.body.textContent).toContain("The built-in prompt is in use again.");
  });

  it("says when a version cannot be chosen or read", async () => {
    const { wrapper } = await promptsPage({
      "POST /api/agents/prompts/test-agent/activate": {
        status: 404,
        json: { code: "unknown_version", title: "There is no such version" },
      },
      "GET /api/agents/prompts/test-agent/1": {
        status: 404,
        json: { code: "unknown_version", title: "There is no such version" },
      },
    });
    await wrapper.get("button[aria-label='Use Version 1']").trigger("click");
    await flushPromises();
    expect(read(wrapper)).toContain("There is no such version");
    await wrapper.findAll(".v-list-item")[1]?.trigger("click");
    await flushPromises();
    expect(read(wrapper)).toContain("There is no such version");
  });

  it("adds a version from the current text", async () => {
    let sent: { body: string; note: string; activate: boolean } | undefined;
    const { wrapper } = await promptsPage({
      "POST /api/agents/prompts/test-agent": (body) => {
        sent = body as typeof sent;
        return {
          status: 201,
          json: {
            ...prompt("test-agent", 2),
            versions: [
              ...prompt("test-agent", 2).versions,
              { version: 2, note: "", created_at: null, created_by: null, active: true },
            ],
          },
        };
      },
      "GET /api/agents/prompts/test-agent/2": {
        json: {
          agent: "test-agent",
          version: 2,
          note: "",
          body: "New text, long enough to be kept.",
        },
      },
    });
    await press(wrapper, "Add a version");
    await flushPromises();
    const area = document.body.querySelector<HTMLTextAreaElement>(".v-dialog textarea");
    expect(area?.value).toBe(BODY);
    expect(dialogButton("Add the version")?.disabled).toBe(false);
    for (const [selector, value] of [[".v-dialog textarea", "short"]] as const) {
      const field = document.body.querySelector<HTMLTextAreaElement>(selector);
      if (field) {
        field.value = value;
        field.dispatchEvent(new Event("input"));
      }
    }
    await flushPromises();
    expect(dialogButton("Add the version")?.disabled).toBe(true);
    const field = document.body.querySelector<HTMLTextAreaElement>(".v-dialog textarea");
    if (field) {
      field.value = "x".repeat(20_001);
      field.dispatchEvent(new Event("input"));
    }
    await flushPromises();
    expect(document.body.textContent).toContain("At most 20000 characters.");
    expect(dialogButton("Add the version")?.disabled).toBe(true);
    if (field) {
      field.value = "New text, long enough to be kept.";
      field.dispatchEvent(new Event("input"));
    }
    const note = document.body.querySelector<HTMLInputElement>(".v-dialog input[type=text]");
    if (note) {
      note.value = "Why";
      note.dispatchEvent(new Event("input"));
    }
    await flushPromises();
    document.body
      .querySelector<HTMLFormElement>(".v-dialog form")
      ?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flushPromises();
    expect(sent).toEqual({
      body: "New text, long enough to be kept.",
      note: "Why",
      activate: true,
    });
    expect(document.body.textContent).toContain("A new version was added.");
  });

  it("says why a version could not be added", async () => {
    const { wrapper } = await promptsPage({
      "POST /api/agents/prompts/test-agent": {
        status: 422,
        json: { code: "invalid", title: "That prompt is not valid" },
      },
    });
    await press(wrapper, "Add a version");
    await flushPromises();
    document.body
      .querySelector<HTMLFormElement>(".v-dialog form")
      ?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flushPromises();
    expect(document.body.textContent).toContain("That prompt is not valid");
  });
});

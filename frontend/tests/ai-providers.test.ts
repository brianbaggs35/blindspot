import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { VDialog, VSnackbar } from "vuetify/components";
import type {
  ConnectionReport,
  DiscoveredModel,
  KindInfo,
  Price,
  Provider,
  ProviderModel,
  RoleDefault,
} from "../src/api/types";
import FormDialog from "../src/components/FormDialog.vue";
import StateView from "../src/components/StateView.vue";
import AiProvidersView from "../src/views/AiProvidersView.vue";
import ModelFormDialog from "../src/views/providers/ModelFormDialog.vue";
import ModelsDialog from "../src/views/providers/ModelsDialog.vue";
import ProviderFormDialog from "../src/views/providers/ProviderFormDialog.vue";
import RoleDefaults from "../src/views/providers/RoleDefaults.vue";
import { dialogButton, dialogName, mockApi, mountWithApp, submitDialog, viewer } from "./helpers";

type Handlers = Parameters<typeof mockApi>[0];

const kinds: KindInfo[] = [
  {
    kind: "anthropic",
    label: "Anthropic",
    default_base_url: "https://api.anthropic.com",
    needs_key: true,
  },
  {
    kind: "openai",
    label: "OpenAI",
    default_base_url: "https://api.openai.com/v1",
    needs_key: true,
  },
  {
    kind: "ollama-local",
    label: "Ollama (local)",
    default_base_url: "http://host.docker.internal:11434",
    needs_key: false,
  },
  {
    kind: "ollama-cloud",
    label: "Ollama (cloud)",
    default_base_url: "https://ollama.com",
    needs_key: true,
  },
];

const claude: Provider = {
  id: "p-1",
  kind: "anthropic",
  name: "Anthropic",
  base_url: "https://api.anthropic.com",
  enabled: true,
  has_key: true,
  key_last4: "wxyz",
  monthly_budget_usd: "100.0000",
  hard_stop: true,
  spent_this_month_usd: "80.5",
  model_count: 1,
  created_at: "2026-11-01T10:00:00Z",
};
const local: Provider = {
  ...claude,
  id: "p-2",
  kind: "ollama-local",
  name: "Workstation",
  base_url: "http://host.docker.internal:11434",
  enabled: false,
  has_key: true,
  key_last4: "1234",
  monthly_budget_usd: null,
  hard_stop: false,
  spent_this_month_usd: "0",
  model_count: 0,
};
const keyless: Provider = { ...local, id: "p-3", name: "Bare", has_key: false, key_last4: null };
const hostedNoKey: Provider = {
  ...claude,
  id: "p-4",
  name: "Broken",
  has_key: false,
  key_last4: null,
};

const none: Price = {
  input: null,
  output: null,
  cache_read: null,
  cache_write: null,
  cache_write_long: null,
};
const opus: ProviderModel = {
  id: "m-1",
  provider_id: "p-1",
  model_id: "claude-opus-5-5",
  display_name: "Claude Opus 5.5",
  context_tokens: 1_000_000,
  max_output_tokens: 128_000,
  capabilities: ["tools", "thinking"],
  supports_tools: true,
  enabled: true,
  price: { input: "4", output: "20", cache_read: "0.2", cache_write: "5", cache_write_long: "8" },
  price_source: "catalog",
  overrides: none,
};
const llama: ProviderModel = {
  ...opus,
  id: "m-2",
  provider_id: "p-2",
  model_id: "llama3.3:70b",
  display_name: "llama3.3:70b",
  context_tokens: null,
  capabilities: [],
  supports_tools: false,
  enabled: false,
  price: { input: "0", output: "0", cache_read: "0", cache_write: "0", cache_write_long: "0" },
  price_source: "free",
};
const roles: RoleDefault[] = [
  {
    role: "commander",
    label: "Commander: plans the pentest and hands out the work",
    model_ref: null,
    provider_name: null,
    model_id: null,
  },
  {
    role: "chat",
    label: "Chat: answers your questions",
    model_ref: "m-1",
    provider_name: "Anthropic",
    model_id: "claude-opus-5-5",
  },
];

function handlers(extra: Handlers = {}, providers: Provider[] = [claude, local]): Handlers {
  return {
    "GET /api/ai/kinds": { json: kinds },
    "GET /api/providers": { json: providers },
    "GET /api/ai/role-defaults": { json: roles },
    "GET /api/providers/p-1/models": { json: [opus] },
    "GET /api/providers/p-2/models": { json: [llama] },
    ...extra,
  };
}

async function page(extra: Handlers = {}, providers: Provider[] = [claude, local]) {
  const api = mockApi(handlers(extra, providers));
  const mounted = await mountWithApp(AiProvidersView, "/ai-providers");
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

function body(calls: { key: string; body: unknown }[], key: string) {
  return calls.find((call) => call.key === key)?.body;
}

function alertText() {
  return Array.from(document.body.querySelectorAll(".v-dialog .v-alert[role=alert]"))
    .map((one) => one.textContent)
    .join(" ");
}

function field(form: Pick<VueWrapper, "findAllComponents">, label: string) {
  return form.findAllComponents({ name: "VTextField" }).find((one) => one.props("label") === label);
}

async function dialogOf(wrapper: Wrapper, label: string, index = 0) {
  await wrapper.findAll(`button[aria-label='${label}']`).at(index)?.trigger("click");
  await flushPromises();
}

describe("AiProvidersView", () => {
  it("lists every provider with its key, spend and models", async () => {
    const { wrapper } = await page();
    expect(wrapper.get("h1").text()).toBe("AI providers");
    const cards = wrapper.findAll(".v-card.h-100");
    expect(cards).toHaveLength(2);
    expect(cards[0]?.text()).toContain("Anthropic");
    expect(cards[0]?.text()).toContain("Key ending in wxyz");
    expect(cards[0]?.text()).toContain("$80.50 of $100.00 this month, calls stop at the budget");
    expect(cards[0]?.text()).toContain("1 model");
    expect(cards[0]?.text()).not.toContain("1 models");
    expect(cards[0]?.find("[aria-label='Budget used for Anthropic']").exists()).toBe(true);
    expect(cards[1]?.text()).toContain("Workstation");
    expect(cards[1]?.text()).toContain("off");
    expect(cards[1]?.text()).toContain("$0.00 this month, no budget");
    expect(cards[1]?.text()).toContain("0 models");
    expect(cards[1]?.find("[aria-label='Budget used for Workstation']").exists()).toBe(false);
  });

  it("says what is missing for each kind of key", async () => {
    const { wrapper } = await page(
      {
        "GET /api/providers/p-3/models": { json: [] },
        "GET /api/providers/p-4/models": { json: [] },
      },
      [keyless, hostedNoKey],
    );
    const text = wrapper.text();
    expect(text).toContain("No key needed");
    expect(text).toContain("No key saved");
  });

  it("explains an empty list, and a failure with a retry", async () => {
    const empty = await page({}, []);
    expect(empty.wrapper.text()).toContain("Add Anthropic, OpenAI or Ollama");
    const failing = mockApi(
      handlers({ "GET /api/ai/kinds": { status: 500, json: { title: "Down" } } }),
    );
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers");
    await flushPromises();
    expect(wrapper.text()).toContain("Could not load the providers");
    expect(wrapper.text()).toContain("Down");
    failing.fetchMock.mockClear();
  });

  it("shows a viewer the providers but none of the controls", async () => {
    mockApi(handlers());
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers", {}, { user: viewer });
    await flushPromises();
    expect(button(wrapper, "Add a provider")).toBeUndefined();
    expect(button(wrapper, "Test")).toBeUndefined();
    expect(wrapper.find("button[aria-label='Edit Anthropic']").exists()).toBe(false);
    expect(wrapper.find("button[aria-label='Delete Anthropic']").exists()).toBe(false);
    expect(button(wrapper, "Models")).toBeDefined();
    expect(wrapper.findAll(".v-input--disabled").length).toBeGreaterThan(0);
  });

  it("tells a viewer nobody has added a provider yet", async () => {
    mockApi(handlers({}, []));
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers", {}, { user: viewer });
    await flushPromises();
    expect(wrapper.text()).toContain("An administrator has not added one yet.");
  });

  it("drops a load that arrives after a newer one", async () => {
    const waiting = new Map<string, ((response: Response) => void)[]>();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (input: RequestInfo | URL) =>
          new Promise<Response>((resolve) => {
            const path = input as string;
            waiting.set(path, [...(waiting.get(path) ?? []), resolve]);
          }),
      ),
    );
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers");
    wrapper.getComponent(StateView).vm.$emit("action");
    await flushPromises();
    const reply = (path: string, index: number, json: unknown) => {
      const answer = waiting.get(path)?.at(index);
      answer?.(
        new Response(JSON.stringify(json), { headers: { "Content-Type": "application/json" } }),
      );
    };
    // The newer load finishes with one provider.
    reply("/api/ai/kinds", 1, kinds);
    reply("/api/providers", 1, [claude]);
    reply("/api/ai/role-defaults", 1, roles);
    await flushPromises();
    reply("/api/providers/p-1/models", 0, [opus]);
    await flushPromises();
    // Then the older one finishes with two, and is ignored.
    reply("/api/ai/kinds", 0, kinds);
    reply("/api/providers", 0, [claude, local]);
    reply("/api/ai/role-defaults", 0, roles);
    await flushPromises();
    reply("/api/providers/p-1/models", 1, [opus]);
    reply("/api/providers/p-2/models", 0, [llama]);
    await flushPromises();
    expect(wrapper.findAll(".v-card.h-100")).toHaveLength(1);
  });

  it("ignores a failure that arrives after a newer load", async () => {
    const pending: { resolve: (value: Response) => void; reject: (error: Error) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (input: RequestInfo | URL) =>
          new Promise<Response>((resolve, reject) => {
            if (input === "/api/ai/kinds") pending.push({ resolve, reject });
            else resolve(new Response("[]", { headers: { "Content-Type": "application/json" } }));
          }),
      ),
    );
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers");
    wrapper.getComponent(StateView).vm.$emit("action");
    await flushPromises();
    pending[1]?.resolve(
      new Response(JSON.stringify(kinds), { headers: { "Content-Type": "application/json" } }),
    );
    await flushPromises();
    pending[0]?.reject(new Error("late failure"));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Could not load the providers");
  });

  it("adds a provider and says to fetch its models", async () => {
    const { wrapper, calls } = await page({
      "POST /api/providers": { status: 201, json: { ...claude, id: "p-9", name: "Second" } },
    });
    await click(wrapper, "Add a provider");
    const form = wrapper.getComponent(ProviderFormDialog);
    expect(document.body.textContent).toContain("Create a key in the Anthropic Console");
    await form.findComponent({ name: "VSelect" }).setValue("openai");
    expect(document.body.textContent).toContain("Create a key on the OpenAI platform");
    await field(form, "Name")?.setValue("Second");
    expect(field(form, "Address")?.props("modelValue")).toBe("https://api.openai.com/v1");
    await field(form, "API key")?.setValue("sk-new-0123456789");
    await field(form, "Monthly budget (USD)")?.setValue("25");
    await form.findComponent({ name: "VSwitch" }).setValue(true);
    await submitDialog();
    expect(body(calls, "POST /api/providers")).toEqual({
      kind: "openai",
      name: "Second",
      base_url: "https://api.openai.com/v1",
      api_key: "sk-new-0123456789",
      enabled: true,
      monthly_budget_usd: "25",
      hard_stop: true,
    });
    expect(document.body.textContent).toContain("Added Second. Fetch its models next.");
    expect(calls.filter((call) => call.key === "GET /api/providers")).toHaveLength(2);
  });

  it("leaves the key and budget out when they are empty, and shows a refusal", async () => {
    const { wrapper, calls } = await page({
      "POST /api/providers": { status: 422, json: { title: "That address is not allowed" } },
    });
    await click(wrapper, "Add a provider");
    await field(wrapper.getComponent(ProviderFormDialog), "Name")?.setValue("Bare");
    await submitDialog();
    expect(body(calls, "POST /api/providers")).toEqual({
      kind: "anthropic",
      name: "Bare",
      base_url: "https://api.anthropic.com",
      enabled: true,
      monthly_budget_usd: null,
      hard_stop: false,
    });
    expect(alertText()).toContain("That address is not allowed");
  });

  it("edits a provider: the saved key is not shown and stays unless replaced", async () => {
    const { wrapper, calls } = await page({
      "PATCH /api/providers/p-1": { json: { ...claude, name: "Renamed" } },
    });
    await dialogOf(wrapper, "Edit Anthropic");
    const form = wrapper.getComponent(ProviderFormDialog);
    expect(document.body.textContent).toContain(
      "A key ending in wxyz is saved. Leave this empty to keep it.",
    );
    expect(document.body.textContent).toContain("The kind cannot be changed.");
    expect(
      document.body.querySelector<HTMLInputElement>(".v-dialog input[type=password]")?.value,
    ).toBe("");
    await field(form, "Name")?.setValue("Renamed");
    await submitDialog();
    expect(body(calls, "PATCH /api/providers/p-1")).toEqual({
      name: "Renamed",
      base_url: "https://api.anthropic.com",
      enabled: true,
      monthly_budget_usd: "100.0000",
      hard_stop: true,
    });
    expect(document.body.textContent).toContain("Saved Renamed.");
  });

  it("replaces a key, and removes one where none is needed", async () => {
    const { wrapper, calls } = await page({
      "PATCH /api/providers/p-1": { json: claude },
      "PATCH /api/providers/p-2": { json: local },
    });
    await dialogOf(wrapper, "Edit Anthropic");
    expect(wrapper.getComponent(ProviderFormDialog).text()).not.toContain("Remove the saved key");
    await field(wrapper.getComponent(ProviderFormDialog), "API key")?.setValue("sk-replaced");
    await submitDialog();
    expect(body(calls, "PATCH /api/providers/p-1")).toMatchObject({ api_key: "sk-replaced" });

    await dialogOf(wrapper, "Edit Workstation");
    const form = wrapper.getComponent(ProviderFormDialog);
    await form.findComponent({ name: "VCheckbox" }).setValue(true);
    await submitDialog();
    expect(body(calls, "PATCH /api/providers/p-2")).toMatchObject({ remove_key: true });
  });

  it("says when a provider has no key saved and when a new key is optional", async () => {
    const { wrapper } = await page({ "GET /api/providers/p-3/models": { json: [] } }, [
      claude,
      keyless,
    ]);
    await dialogOf(wrapper, "Edit Bare");
    expect(document.body.textContent).toContain("No key is saved.");
    wrapper.getComponent(ProviderFormDialog).vm.$emit("update:modelValue", false);
    await flushPromises();
    await click(wrapper, "Add a provider");
    await wrapper
      .getComponent(ProviderFormDialog)
      .findComponent({ name: "VSelect" })
      .setValue("ollama-local");
    expect(document.body.textContent).toContain("Optional.");
    expect(document.body.textContent).toContain("OLLAMA_HOST=0.0.0.0");
  });

  it("keeps the address of a provider being edited when the kind is not touched", async () => {
    const { wrapper } = await page();
    await dialogOf(wrapper, "Edit Workstation");
    const address = field(wrapper.getComponent(ProviderFormDialog), "Address");
    expect(address?.props("modelValue")).toBe("http://host.docker.internal:11434");
  });

  it("tests a connection and shows the result on the card", async () => {
    const report: ConnectionReport = {
      ok: true,
      latency_ms: 123,
      model_count: 4,
      failure: null,
      detail: "Connected. 4 models are available.",
    };
    const { wrapper } = await page({ "POST /api/providers/p-1/test": { json: report } });
    await click(wrapper, "Test");
    expect(wrapper.text()).toContain("Connected. 4 models are available.");
    expect(wrapper.text()).toContain("(123 ms)");
  });

  it("shows why a connection failed, and a request that itself failed", async () => {
    const { wrapper } = await page({
      "POST /api/providers/p-1/test": {
        json: {
          ok: false,
          latency_ms: 5,
          model_count: null,
          failure: "key_rejected",
          detail: "Anthropic did not accept the key.",
        },
      },
      "POST /api/providers/p-2/test": { status: 500, json: { title: "Broken" } },
    });
    await click(wrapper, "Test");
    expect(wrapper.text()).toContain("Anthropic did not accept the key.");
    expect(wrapper.text()).not.toContain("ms)");
    await wrapper
      .findAll("button")
      .filter((one) => one.text() === "Test")[1]
      ?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Broken");
  });

  it("deletes a provider after asking, and shows a refusal", async () => {
    const { wrapper, calls } = await page({ "DELETE /api/providers/p-1": { status: 204 } });
    await dialogOf(wrapper, "Delete Anthropic");
    expect(document.body.textContent).toContain("Delete Anthropic?");
    await press("Cancel");
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false);
    await dialogOf(wrapper, "Delete Anthropic");
    await press("Delete");
    expect(calls.some((call) => call.key === "DELETE /api/providers/p-1")).toBe(true);
    expect(document.body.textContent).toContain("Deleted Anthropic.");
    wrapper.getComponent(VSnackbar).vm.$emit("update:modelValue", false);
  });

  it("shows why a provider could not be deleted", async () => {
    const { wrapper } = await page({
      "DELETE /api/providers/p-1": { status: 500, json: { title: "Nope" } },
    });
    await dialogOf(wrapper, "Delete Anthropic");
    await press("Delete");
    expect(alertText()).toContain("Nope");
  });

  it("does nothing when a delete is submitted with nothing chosen", async () => {
    const { wrapper, calls } = await page();
    const confirm = wrapper.findAllComponents(FormDialog).at(-1);
    confirm?.vm.$emit("submit");
    await flushPromises();
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false);
  });
});

describe("Provider form details", () => {
  it("falls back to the raw kind when the API does not know it", async () => {
    mockApi(handlers({ "GET /api/ai/kinds": { json: [kinds[0]] } }));
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers");
    await flushPromises();
    const text = wrapper.findAll(".v-card.h-100")[1]?.text() ?? "";
    expect(text).toContain("ollama-local");
    expect(text).toContain("Key ending in 1234");
  });

  it("opens with an empty address while the kinds have not loaded", async () => {
    mockApi(handlers());
    const { wrapper } = await mountWithApp(ProviderFormDialog, "/", {
      provider: null,
      kinds: [],
      modelValue: false,
    });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(field(wrapper, "Address")?.props("modelValue")).toBe("");
    expect(document.body.textContent).toContain("Optional.");
    await wrapper.findComponent({ name: "VSelect" }).setValue("openai");
    expect(field(wrapper, "Address")?.props("modelValue")).toBe("");
  });

  it("lets the address, the switch and the dialog itself be changed", async () => {
    const { wrapper, calls } = await page({
      "PATCH /api/providers/p-1": { json: claude },
    });
    await dialogOf(wrapper, "Edit Anthropic");
    const form = wrapper.getComponent(ProviderFormDialog);
    await field(form, "Address")?.setValue("https://gateway.example.com");
    await form.findAllComponents({ name: "VSwitch" })[1]?.setValue(false);
    await submitDialog();
    expect(body(calls, "PATCH /api/providers/p-1")).toMatchObject({
      base_url: "https://gateway.example.com",
      enabled: false,
    });
    form.getComponent(FormDialog).vm.$emit("update:modelValue", false);
    await flushPromises();
    expect(form.emitted("update:modelValue")).toBeTruthy();
  });
});

describe("The models of a provider", () => {
  async function models(extra: Handlers = {}) {
    const mounted = await page(extra);
    await click(mounted.wrapper, "Models");
    return mounted;
  }

  const fresh: DiscoveredModel = {
    model_id: "claude-brand-new",
    display_name: "Claude Brand New",
    context_tokens: 200_000,
    max_output_tokens: 64_000,
    capabilities: ["tools"],
    added: false,
    price_source: "unknown",
  };
  const already: DiscoveredModel = {
    ...fresh,
    model_id: "claude-opus-5-5",
    display_name: "Claude Opus 5.5",
    added: true,
    price_source: "catalog",
  };

  function row() {
    return document.body.querySelector(".v-dialog .v-list-item");
  }

  it("lists them with their price and what is missing", async () => {
    await models();
    const rows = Array.from(document.body.querySelectorAll(".v-dialog .v-list-item"));
    expect(rows).toHaveLength(1);
    expect(rows[0]?.textContent).toContain("Claude Opus 5.5");
    expect(rows[0]?.textContent).toContain(
      "claude-opus-5-5 · 1,000,000 tokens · in $4.00 · out $20.00",
    );
    expect(rows[0]?.textContent).toContain("catalog price");
    expect(rows[0]?.textContent).not.toContain("no tools");
    expect(document.body.textContent).toContain("Models of Anthropic");
    expect(dialogName()).toBe("Models of Anthropic");
  });

  it("flags a model that cannot run agents and shows a free one as free", async () => {
    const { wrapper } = await page();
    await wrapper
      .findAll("button")
      .filter((one) => one.text() === "Models")[1]
      ?.trigger("click");
    await flushPromises();
    expect(row()?.textContent).toContain("no tools");
    expect(row()?.textContent).toContain("free");
    expect(row()?.textContent).toContain("—");
  });

  it("explains an empty list to an administrator", async () => {
    await models({ "GET /api/providers/p-1/models": { json: [] } });
    // The page loaded one model for the role defaults; the dialog asks again and finds none.
    expect(document.body.textContent).toContain("Fetch the models this provider offers");
  });

  it("shows a failure to load with a retry", async () => {
    const { wrapper } = await page();
    const state = mockApi(
      handlers({ "GET /api/providers/p-1/models": { status: 500, json: { title: "Down" } } }),
    );
    await click(wrapper, "Models");
    expect(document.body.textContent).toContain("Could not load the models");
    expect(document.body.textContent).toContain("Down");
    state.fetchMock.mockClear();
    mockApi(handlers());
    wrapper.getComponent(ModelsDialog).getComponent(StateView).vm.$emit("action");
    await flushPromises();
    expect(row()?.textContent).toContain("Claude Opus 5.5");
  });

  it("drops a list that arrives after the dialog was opened again", async () => {
    const { wrapper } = await page();
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
    const dialog = () => wrapper.getComponent(ModelsDialog);
    await click(wrapper, "Models");
    dialog().vm.$emit("update:modelValue", false);
    await flushPromises();
    await click(wrapper, "Models");
    const reply = (json: unknown) =>
      new Response(JSON.stringify(json), { headers: { "Content-Type": "application/json" } });
    waiting[1]?.(reply([opus]));
    await flushPromises();
    waiting[0]?.(reply([]));
    await flushPromises();
    expect(row()?.textContent).toContain("Claude Opus 5.5");
  });

  it("ignores a failure that arrives after a newer list", async () => {
    const { wrapper } = await page();
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
    await click(wrapper, "Models");
    wrapper.getComponent(ModelsDialog).getComponent(StateView).vm.$emit("action");
    await flushPromises();
    waiting[1]?.resolve(
      new Response(JSON.stringify([opus]), { headers: { "Content-Type": "application/json" } }),
    );
    await flushPromises();
    waiting[0]?.reject(new Error("late failure"));
    await flushPromises();
    expect(document.body.textContent).not.toContain("Could not load the models");
  });

  it("shows a viewer the models without any way to change them", async () => {
    mockApi(handlers());
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers", {}, { user: viewer });
    await flushPromises();
    await click(wrapper, "Models");
    expect(dialogButton("Fetch models")).toBeUndefined();
    expect(document.body.querySelector("button[aria-label='Edit Claude Opus 5.5']")).toBeNull();
    expect(
      document.body
        .querySelector("input[aria-label='Use Claude Opus 5.5']")
        ?.hasAttribute("disabled"),
    ).toBe(true);
  });

  it("tells a viewer that no models were added", async () => {
    mockApi(handlers());
    const { wrapper } = await mountWithApp(AiProvidersView, "/ai-providers", {}, { user: viewer });
    await flushPromises();
    mockApi(handlers({ "GET /api/providers/p-1/models": { json: [] } }));
    await click(wrapper, "Models");
    expect(document.body.textContent).toContain("An administrator has not added any.");
  });

  it("fetches what the provider offers and adds the models that are picked", async () => {
    const { calls } = await models({
      "POST /api/providers/p-1/models/fetch": { json: [fresh, already] },
      "POST /api/providers/p-1/models": { status: 201, json: opus },
    });
    await press("Fetch models");
    expect(document.body.textContent).toContain("The provider offers 2 models");
    expect(document.body.textContent).toContain("Claude Brand New");
    expect(document.body.textContent).toContain("price unknown");
    const boxes = document.body.querySelectorAll<HTMLInputElement>(
      ".v-dialog section input[type=checkbox]",
    );
    expect(boxes).toHaveLength(1);
    expect(dialogButton("Add 0 selected")?.hasAttribute("disabled")).toBe(true);
    boxes[0]?.click();
    await flushPromises();
    await press("Add 1 selected");
    expect(body(calls, "POST /api/providers/p-1/models")).toEqual({
      model_id: "claude-brand-new",
      display_name: "Claude Brand New",
      context_tokens: 200_000,
      max_output_tokens: 64_000,
      capabilities: ["tools"],
    });
    expect(document.body.textContent).toContain("Added 1 model.");
    expect(document.body.textContent).not.toContain("The provider offers");
  });

  it("says how many models were added", async () => {
    const { calls } = await models({
      "POST /api/providers/p-1/models/fetch": {
        json: [fresh, { ...fresh, model_id: "two", display_name: "Two" }],
      },
      "POST /api/providers/p-1/models": { status: 201, json: opus },
    });
    await press("Fetch models");
    for (const box of document.body.querySelectorAll<HTMLInputElement>(
      ".v-dialog section input[type=checkbox]",
    )) {
      box.click();
      await flushPromises();
    }
    await press("Add 2 selected");
    expect(calls.filter((call) => call.key === "POST /api/providers/p-1/models")).toHaveLength(2);
    expect(document.body.textContent).toContain("Added 2 models.");
  });

  it("says when everything the provider offers is added already", async () => {
    await models({
      "POST /api/providers/p-1/models/fetch": { json: [already] },
    });
    await press("Fetch models");
    expect(document.body.textContent).toContain("Every one of them is added already.");
  });

  it("shows why fetching failed, and why adding a model failed", async () => {
    await models({
      "POST /api/providers/p-1/models/fetch": {
        status: 502,
        json: { title: "Anthropic did not accept the key." },
      },
    });
    await press("Fetch models");
    expect(document.body.textContent).toContain("Anthropic did not accept the key.");

    mockApi(
      handlers({
        "POST /api/providers/p-1/models/fetch": {
          json: [fresh, { ...fresh, model_id: "two", display_name: "Two" }],
        },
        "POST /api/providers/p-1/models": {
          status: 409,
          json: { title: "That model is already listed" },
        },
      }),
    );
    await press("Fetch models");
    document.body
      .querySelectorAll<HTMLInputElement>(".v-dialog section input[type=checkbox]")[0]
      ?.click();
    await flushPromises();
    await press("Add 1 selected");
    expect(document.body.textContent).toContain("That model is already listed");
  });

  it("turns a model on or off, and says when that failed", async () => {
    const { wrapper, calls } = await models({
      "PATCH /api/providers/p-1/models/m-1": { json: { ...opus, enabled: false } },
    });
    document.body
      .querySelector<HTMLInputElement>("input[aria-label='Use Claude Opus 5.5']")
      ?.click();
    await flushPromises();
    expect(body(calls, "PATCH /api/providers/p-1/models/m-1")).toEqual({ enabled: false });
    expect(
      calls.filter((call) => call.key === "GET /api/providers/p-1/models").length,
    ).toBeGreaterThan(1);
    expect(wrapper.getComponent(ModelsDialog).emitted("changed")).toBeTruthy();

    mockApi(
      handlers({ "PATCH /api/providers/p-1/models/m-1": { status: 500, json: { title: "Nope" } } }),
    );
    document.body
      .querySelector<HTMLInputElement>("input[aria-label='Use Claude Opus 5.5']")
      ?.click();
    await flushPromises();
    expect(document.body.textContent).toContain("Nope");
  });

  it("removes a model after asking, and shows a refusal", async () => {
    const { calls } = await models({
      "DELETE /api/providers/p-1/models/m-1": { status: 204 },
    });
    document.body
      .querySelector<HTMLButtonElement>("button[aria-label='Remove Claude Opus 5.5']")
      ?.click();
    await flushPromises();
    expect(document.body.textContent).toContain("Remove Claude Opus 5.5?");
    await press("Cancel");
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false);
    document.body
      .querySelector<HTMLButtonElement>("button[aria-label='Remove Claude Opus 5.5']")
      ?.click();
    await flushPromises();
    await press("Remove");
    expect(calls.some((call) => call.key === "DELETE /api/providers/p-1/models/m-1")).toBe(true);
    expect(document.body.textContent).toContain("Removed Claude Opus 5.5.");

    mockApi(
      handlers({
        "DELETE /api/providers/p-1/models/m-1": { status: 500, json: { title: "Locked" } },
      }),
    );
    document.body
      .querySelector<HTMLButtonElement>("button[aria-label='Remove Claude Opus 5.5']")
      ?.click();
    await flushPromises();
    await press("Remove");
    expect(alertText()).toContain("Locked");
  });

  it("closes from the dialog itself and from the removal question", async () => {
    const { wrapper } = await models();
    const dialog = wrapper.getComponent(ModelsDialog);
    dialog.findAllComponents(FormDialog).at(-1)?.vm.$emit("update:modelValue", false);
    dialog.getComponent(VDialog).vm.$emit("update:modelValue", false);
    await flushPromises();
    await press("Close");
    expect(dialog.emitted("update:modelValue")).toBeTruthy();
  });

  it("does nothing when a removal is submitted with nothing chosen", async () => {
    const { wrapper, calls } = await models();
    wrapper.getComponent(ModelsDialog).findAllComponents(FormDialog).at(-1)?.vm.$emit("submit");
    await flushPromises();
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false);
  });
});

describe("Adding and changing a model", () => {
  async function form(extra: Handlers = {}, edit = false) {
    const mounted = await page(extra);
    await click(mounted.wrapper, "Models");
    if (edit) {
      document.body
        .querySelector<HTMLButtonElement>("button[aria-label='Edit Claude Opus 5.5']")
        ?.click();
    } else {
      dialogButton("Add by hand")?.click();
    }
    await flushPromises();
    return { ...mounted, dialog: mounted.wrapper.getComponent(ModelFormDialog) };
  }

  it("closes without saving", async () => {
    const { dialog, calls } = await form();
    await press("Cancel");
    expect(calls.some((call) => call.key.startsWith("POST"))).toBe(false);
    dialog.vm.$emit("update:modelValue", false);
  });

  it("adds a model with everything filled in", async () => {
    const { dialog, calls } = await form({
      "POST /api/providers/p-1/models": { status: 201, json: opus },
    });
    await field(dialog, "Model id")?.setValue("claude-new");
    await field(dialog, "Name")?.setValue("Claude New");
    await field(dialog, "Context size (tokens)")?.setValue("200000");
    await field(dialog, "Largest answer (tokens)")?.setValue("not a number");
    await field(dialog, "Input")?.setValue("1.5");
    await field(dialog, "Cache write, long")?.setValue(" 2 ");
    await dialog.findComponent({ name: "VSelect" }).setValue(["tools", "vision"]);
    await dialog.findComponent({ name: "VSwitch" }).setValue(false);
    await submitDialog();
    expect(body(calls, "POST /api/providers/p-1/models")).toEqual({
      model_id: "claude-new",
      display_name: "Claude New",
      context_tokens: 200_000,
      max_output_tokens: null,
      capabilities: ["tools", "vision"],
      enabled: false,
      price_input: "1.5",
      price_output: null,
      price_cache_read: null,
      price_cache_write: null,
      price_cache_write_long: "2",
    });
    expect(document.body.textContent).toContain("Saved Claude Opus 5.5.");
  });

  it("uses the catalog's capabilities when none are chosen, and shows a refusal", async () => {
    const { dialog, calls } = await form({
      "POST /api/providers/p-1/models": {
        status: 409,
        json: { title: "That model is already listed" },
      },
    });
    await field(dialog, "Model id")?.setValue("claude-opus-5-5");
    await submitDialog();
    expect(body(calls, "POST /api/providers/p-1/models")).toMatchObject({ capabilities: null });
    expect(alertText()).toContain("That model is already listed");
  });

  it("changes a model: its name, capabilities and your prices", async () => {
    const priced = { ...opus, overrides: { ...none, input: "3", cache_write: "6" } };
    const { dialog, calls } = await form(
      {
        "GET /api/providers/p-1/models": { json: [priced] },
        "PATCH /api/providers/p-1/models/m-1": { json: priced },
      },
      true,
    );
    expect(document.body.textContent).toContain("Edit Claude Opus 5.5");
    expect(field(dialog, "Input")?.props("modelValue")).toBe("3");
    expect(field(dialog, "Output")?.props("modelValue")).toBe("");
    expect(field(dialog, "Model id")).toBeUndefined();
    await field(dialog, "Name")?.setValue("Opus");
    await field(dialog, "Input")?.setValue("");
    await submitDialog();
    expect(body(calls, "PATCH /api/providers/p-1/models/m-1")).toEqual({
      display_name: "Opus",
      capabilities: ["tools", "thinking"],
      enabled: true,
      price_input: null,
      price_output: null,
      price_cache_read: null,
      price_cache_write: "6",
      price_cache_write_long: null,
    });
  });
});

describe("The default model for each job", () => {
  function selects(wrapper: Wrapper) {
    return wrapper.getComponent(RoleDefaults).findAllComponents({ name: "VSelect" });
  }

  it("offers only models that are on, on providers that are on", async () => {
    const { wrapper } = await page();
    const [commander, chat] = selects(wrapper);
    expect(commander?.props("items")).toEqual([
      { title: "Anthropic · Claude Opus 5.5", value: "m-1" },
    ]);
    expect(commander?.props("label")).toContain("Commander");
    expect(chat?.props("modelValue")).toBe("m-1");
  });

  it("saves a choice the moment it is made, and clears it", async () => {
    const { wrapper, calls } = await page({
      "PUT /api/ai/role-defaults/commander": { status: 204 },
      "DELETE /api/ai/role-defaults/chat": { status: 204 },
    });
    await selects(wrapper)[0]?.setValue("m-1");
    await flushPromises();
    expect(body(calls, "PUT /api/ai/role-defaults/commander")).toEqual({ model_ref: "m-1" });
    expect(document.body.textContent).toContain("Saved the default for commander.");
    await selects(wrapper)[1]?.setValue(null);
    await flushPromises();
    expect(calls.some((call) => call.key === "DELETE /api/ai/role-defaults/chat")).toBe(true);
  });

  it("shows why a choice was refused", async () => {
    const { wrapper } = await page({
      "PUT /api/ai/role-defaults/commander": {
        status: 409,
        json: { title: "That model is turned off" },
      },
    });
    await selects(wrapper)[0]?.setValue("m-1");
    await flushPromises();
    expect(wrapper.text()).toContain("That model is turned off");
  });
});

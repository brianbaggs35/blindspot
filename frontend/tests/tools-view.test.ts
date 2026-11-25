import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ToolSettings, ToolTestResult, User } from "../src/api/types";
import ToolsView from "../src/views/ToolsView.vue";
import ToolTestDialog from "../src/views/tools/ToolTestDialog.vue";
import { admin, dialogButton, dialogName, mockApi, mountWithApp, viewer } from "./helpers";
import { emitFrom, fieldNamed } from "./pentest-fixtures";
import { custom, nmap, noOverrides, toolSettings } from "./tools-fixtures";

type Handlers = Parameters<typeof mockApi>[0];

const tested: ToolTestResult = {
  mode: "local",
  command: ["/usr/bin/nmap", "--version"],
  exit_code: 0,
  output: "Nmap version 7.95",
  duration_ms: 41,
  version: "7.95",
  timed_out: false,
};

async function page(
  extra: Handlers = {},
  settings: ToolSettings = toolSettings(),
  user: User = admin,
) {
  const api = mockApi({ "GET /api/tools/settings": { json: settings }, ...extra });
  const mounted = await mountWithApp(ToolsView, "/tools", {}, { user });
  await flushPromises();
  return { ...api, ...mounted };
}

type Wrapper = Awaited<ReturnType<typeof page>>["wrapper"];

function card(wrapper: Wrapper, name: string) {
  const found = wrapper.findAll(".v-card").find((one) => one.attributes("aria-label") === name);
  if (found === undefined) throw new Error(`no card for ${name}`);
  return found;
}

async function press(wrapper: Wrapper, name: string, label: string) {
  await card(wrapper, name)
    .findAll("button")
    .find((one) => one.text() === label)
    ?.trigger("click");
  await flushPromises();
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("the Tools page", () => {
  it("shows each tool, where it runs and what is wrong", async () => {
    const { wrapper } = await page();
    expect(wrapper.text()).toContain("Docker is not connected");
    expect(wrapper.text()).toContain("No Docker socket is mounted.");
    const text = (name: string) => card(wrapper, name).text();
    expect(text("Nmap")).toContain("Ready");
    expect(text("Nmap")).toContain("/usr/bin/nmap");
    expect(text("Nmap")).toContain("600 s, 32 MB of output, no rate limit, up to active");
    expect(text("Nuclei")).toContain("Program not found");
    expect(text("Nuclei")).toContain("nuclei is not installed here.");
    expect(text("Nuclei")).toContain("It would run Docker. Choose that in its settings");
    expect(text("Nuclei")).toContain("5 requests per second");
    expect(text("Nuclei")).toContain("@sha256:");
    expect(text("Echo")).toContain("Docker (the other way, as the default allows)");
    expect(text("Report")).toContain("Built in");
  });

  it("hides the Docker note once Docker is connected", async () => {
    const { wrapper } = await page({}, toolSettings({ docker: { reachable: true, note: "" } }));
    expect(wrapper.text()).not.toContain("No Docker socket");
  });

  it("offers Settings, Test and Reset only where they apply", async () => {
    const { wrapper } = await page();
    const buttons = (name: string) =>
      card(wrapper, name)
        .findAll("button")
        .map((one) => one.text());
    expect(buttons("Nmap")).toEqual(["Settings", "Test"]);
    expect(buttons("Nuclei")).toEqual(["Settings"]);
    expect(buttons("Echo")).toEqual(["Settings", "Reset"]);
  });

  it("is read-only for a viewer", async () => {
    const { wrapper } = await page({}, toolSettings(), viewer);
    expect(wrapper.text()).toContain("Only an administrator can change these settings.");
    expect(wrapper.findAll("button").map((one) => one.text())).not.toContain("Settings");
  });

  it("shows why the tools could not be loaded and tries again", async () => {
    const api = mockApi({ "GET /api/tools/settings": { status: 500, json: { title: "Broken" } } });
    const { wrapper } = await mountWithApp(ToolsView, "/tools");
    await flushPromises();
    expect(wrapper.text()).toContain("Could not load the tools");
    api.fetchMock.mockClear();
    await wrapper
      .findAll("button")
      .find((one) => one.text() === "Try again")
      ?.trigger("click");
    await flushPromises();
    expect(api.calls.some((call) => call.key === "GET /api/tools/settings")).toBe(true);
  });

  it("keeps the newest answer when two loads overlap", async () => {
    const { wrapper } = await page({
      "PUT /api/tools/settings/default": { status: 204 },
    });
    const waiting: ((reply: Response) => void)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "PUT"
          ? Promise.resolve(new Response(null, { status: 204 }))
          : new Promise<Response>((resolve) => waiting.push(resolve)),
      ),
    );
    const answer = (mode: string) =>
      new Response(JSON.stringify(toolSettings({ run_mode: mode as never })), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    const select = fieldNamed(wrapper, "VSelect", "Where tools run");
    emitFrom(select, "update:modelValue", "prefer_local");
    await flushPromises();
    emitFrom(select, "update:modelValue", "prefer_docker");
    await flushPromises();
    expect(waiting).toHaveLength(2);
    // The newer load answers first; the older one arrives late and is dropped.
    waiting[1]?.(answer("prefer_docker"));
    await flushPromises();
    waiting[0]?.(answer("prefer_local"));
    await flushPromises();
    expect(fieldNamed(wrapper, "VSelect", "Where tools run").props("modelValue")).toBe(
      "prefer_docker",
    );
  });

  it("drops a late failure of an older load", async () => {
    const { wrapper } = await page({ "PUT /api/tools/settings/default": { status: 204 } });
    const waiting: { resolve: (reply: Response) => void; reject: (error: Error) => void }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "PUT"
          ? Promise.resolve(new Response(null, { status: 204 }))
          : new Promise<Response>((resolve, reject) => waiting.push({ resolve, reject })),
      ),
    );
    const select = fieldNamed(wrapper, "VSelect", "Where tools run");
    emitFrom(select, "update:modelValue", "prefer_local");
    await flushPromises();
    emitFrom(select, "update:modelValue", "prefer_docker");
    await flushPromises();
    waiting[1]?.resolve(
      new Response(JSON.stringify(toolSettings()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await flushPromises();
    waiting[0]?.reject(new Error("late"));
    await flushPromises();
    expect(wrapper.text()).not.toContain("Could not load the tools");
  });

  it("saves a new default and says so", async () => {
    let mode = "auto";
    const { wrapper, calls } = await page({
      "GET /api/tools/settings": () => ({ json: toolSettings({ run_mode: mode as never }) }),
      "PUT /api/tools/settings/default": (body) => {
        mode = (body as { mode: string }).mode;
        return { status: 204 };
      },
    });
    emitFrom(fieldNamed(wrapper, "VSelect", "Where tools run"), "update:modelValue", "docker_only");
    await flushPromises();
    expect(calls.find((call) => call.key === "PUT /api/tools/settings/default")?.body).toEqual({
      mode: "docker_only",
    });
    expect(document.body.textContent).toContain("The default was saved.");
    expect(wrapper.text()).toContain("Docker, and nothing else.");
  });

  it("says when a default could not be saved", async () => {
    const { wrapper } = await page({
      "PUT /api/tools/settings/default": { status: 400, json: { title: "Not allowed" } },
    });
    emitFrom(
      fieldNamed(wrapper, "VSelect", "Where tools run"),
      "update:modelValue",
      "prefer_local",
    );
    await flushPromises();
    expect(document.body.textContent).toContain("Could not save it:");
  });

  it("edits a tool and reloads", async () => {
    const { wrapper, calls } = await page({
      "PUT /api/tools/settings/c.nmap": { json: nmap },
    });
    await press(wrapper, "Nmap", "Settings");
    expect(dialogName()).toBe("Settings for Nmap");
    dialogButton("Save")?.click();
    await flushPromises();
    expect(calls.find((call) => call.key === "PUT /api/tools/settings/c.nmap")?.body).toEqual(
      noOverrides,
    );
    expect(document.body.textContent).toContain("Saved the settings of Nmap.");
    expect(calls.filter((call) => call.key === "GET /api/tools/settings")).toHaveLength(2);
  });

  it("resets a tool to its defaults", async () => {
    const { wrapper, calls } = await page({ "DELETE /api/tools/settings/x.echo": {} });
    await press(wrapper, "Echo", "Reset");
    expect(calls.some((call) => call.key === "DELETE /api/tools/settings/x.echo")).toBe(true);
    expect(document.body.textContent).toContain("Echo is back to its defaults.");
  });

  it("says when a reset failed", async () => {
    const { wrapper } = await page({
      "DELETE /api/tools/settings/x.echo": { status: 500, json: { title: "Nope" } },
    });
    await press(wrapper, "Echo", "Reset");
    expect(document.body.textContent).toContain("Could not do that:");
  });

  it("tests a tool and shows what ran", async () => {
    const { wrapper } = await page({ "POST /api/tools/settings/c.nmap/test": { json: tested } });
    await press(wrapper, "Nmap", "Test");
    expect(dialogName()).toBe("Test Nmap");
    expect(document.body.textContent).toContain("/usr/bin/nmap --version");
    expect(document.body.textContent).toContain("exit code 0");
    expect(document.body.textContent).toContain("7.95");
  });

  it("shows why a test could not run", async () => {
    const { wrapper } = await page({
      "POST /api/tools/settings/c.nmap/test": { status: 409, json: { title: "Switched off" } },
    });
    await press(wrapper, "Nmap", "Test");
    expect(document.body.querySelector(".v-dialog .v-alert[role=alert]")?.textContent).toContain(
      "Switched off",
    );
  });

  it("shows a test that ran out of time, found no version and printed nothing", async () => {
    const wrapper = (
      await mountWithApp(ToolTestDialog, "/tools", {
        modelValue: true,
        name: "Echo",
        busy: false,
        failure: "",
        result: {
          ...tested,
          mode: "docker",
          exit_code: null,
          output: "",
          version: null,
          timed_out: true,
        },
      })
    ).wrapper;
    await flushPromises();
    const text = document.body.textContent;
    expect(text).toContain("It did not finish in time");
    expect(text).toContain("Docker");
    expect(text).toContain("no exit code");
    expect(text).toContain("not found in the output");
    expect(text).toContain("(nothing)");
    wrapper.unmount();
  });

  it("closes the test dialog", async () => {
    const { wrapper } = await page({ "POST /api/tools/settings/c.nmap/test": { json: tested } });
    await press(wrapper, "Nmap", "Test");
    dialogButton("Close")?.click();
    await flushPromises();
    expect(custom.id).toBe("x.echo");
  });
});

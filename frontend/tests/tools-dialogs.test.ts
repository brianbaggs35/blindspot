import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import ToolSettingsDialog from "../src/views/tools/ToolSettingsDialog.vue";
import { dialogButton, mockApi, mountWithApp } from "./helpers";
import { emitFrom, fieldNamed } from "./pentest-fixtures";
import { builtin, custom, nmap, noOverrides, nuclei } from "./tools-fixtures";

afterEach(() => {
  document.body.innerHTML = "";
});

async function open(tool = nmap, reply: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({ [`PUT /api/tools/settings/${tool.id}`]: { json: tool }, ...reply });
  const mounted = await mountWithApp(ToolSettingsDialog, "/tools", { modelValue: false, tool });
  await mounted.wrapper.setProps({ modelValue: true });
  await flushPromises();
  return { ...api, ...mounted };
}

const labels = () =>
  Array.from(document.body.querySelectorAll(".v-dialog label")).map((one) => one.textContent);

describe("the settings of a tool", () => {
  it("shows the program of a tool that runs Local and the image of one that runs in Docker", async () => {
    const { wrapper } = await open();
    expect(labels()).toContain("Program path (Local)");
    expect(labels()).toContain("Image with its digest (Docker)");
    emitFrom(fieldNamed(wrapper, "VSelect", "Where it runs"), "update:modelValue", "docker");
    await flushPromises();
    expect(labels()).not.toContain("Program path (Local)");
    expect(labels()).toContain("Image with its digest (Docker)");
    emitFrom(fieldNamed(wrapper, "VSelect", "Where it runs"), "update:modelValue", "local");
    await flushPromises();
    expect(labels()).toContain("Program path (Local)");
    expect(labels()).not.toContain("Image with its digest (Docker)");
  });

  it("says what empty means for the program and the image", async () => {
    await open(nuclei);
    const hints = document.body.textContent;
    expect(hints).toContain("Empty means nuclei.");
    expect(hints).toContain("Empty means ghcr.io/projectdiscovery/nuclei@sha256:");
    expect(hints).toContain("Empty means 600.");
    expect(hints).toContain("Empty means 32.");
    expect(hints).toContain("Empty means intrusive, the tool's own class.");
  });

  it("explains the format of an image when the tool has none", async () => {
    await open({ ...custom, default_binary: null });
    const hints = document.body.textContent;
    expect(hints).toContain("the program the tool defines");
    expect(hints).toContain("ending in @sha256: and 64 hex characters");
  });

  it("offers only the switch and the limits for a tool that comes built in", async () => {
    await open(builtin);
    expect(labels()).not.toContain("Where it runs");
    expect(labels()).not.toContain("Program path (Local)");
    expect(labels()).not.toContain("Image with its digest (Docker)");
    expect(labels()).toContain("Timeout (seconds)");
  });

  it("sends what was typed and tells the page", async () => {
    const { wrapper, calls } = await open();
    emitFrom(
      fieldNamed(wrapper, "VTextField", "Program path (Local)"),
      "update:modelValue",
      "/opt/nmap",
    );
    emitFrom(
      fieldNamed(wrapper, "VTextField", "Image with its digest (Docker)"),
      "update:modelValue",
      "reg/nmap@sha256:" + "c".repeat(64),
    );
    const timeout = fieldNamed(wrapper, "VTextField", "Timeout (seconds)");
    emitFrom(timeout, "update:modelValue", "30");
    emitFrom(fieldNamed(wrapper, "VTextField", "Output cap (MB)"), "update:modelValue", "4");
    emitFrom(
      fieldNamed(wrapper, "VTextField", "Requests per second, for each target"),
      "update:modelValue",
      "2.5",
    );
    emitFrom(fieldNamed(wrapper, "VTextField", "CPUs (Docker only)"), "update:modelValue", "1.5");
    emitFrom(
      fieldNamed(wrapper, "VTextField", "Memory in MB (Docker only)"),
      "update:modelValue",
      "512",
    );
    emitFrom(fieldNamed(wrapper, "VSelect", "Most it may do"), "update:modelValue", "passive");
    await flushPromises();
    dialogButton("Save")?.click();
    await flushPromises();
    expect(calls.find((call) => call.key === "PUT /api/tools/settings/c.nmap")?.body).toMatchObject(
      {
        binary_path: "/opt/nmap",
        image: "reg/nmap@sha256:" + "c".repeat(64),
        timeout_s: 30,
        max_output_mb: 4,
        rate_per_s: 2.5,
        cpus: "1.5",
        memory_mb: 512,
        max_risk: "passive",
      },
    );
    expect(wrapper.emitted("saved")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("starts again from the saved settings each time it opens", async () => {
    const { wrapper } = await open(custom);
    expect(fieldNamed(wrapper, "VSwitch", "This tool may be used").props("modelValue")).toBe(false);
    emitFrom(fieldNamed(wrapper, "VSwitch", "This tool may be used"), "update:modelValue", true);
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(fieldNamed(wrapper, "VSwitch", "This tool may be used").props("modelValue")).toBe(false);
  });

  it("closes without saving", async () => {
    const { wrapper, calls } = await open();
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
    expect(calls).toHaveLength(0);
  });

  it("shows why it could not save", async () => {
    const { wrapper } = await open(nmap, {
      "PUT /api/tools/settings/c.nmap": { status: 422, json: { title: "Not a digest" } },
    });
    dialogButton("Save")?.click();
    await flushPromises();
    expect(document.body.querySelector(".v-dialog .v-alert[role=alert]")?.textContent).toContain(
      "Not a digest",
    );
    expect(wrapper.emitted("saved")).toBeUndefined();
    expect(noOverrides.enabled).toBe(true);
  });
});

import { describe, expect, it } from "vitest";
import { bodyOf, customised, draftOf, MODE_CHOICES, risksUpTo, whereOf } from "../src/tools";
import { custom, nmap, noOverrides, nuclei } from "./tools-fixtures";

describe("the tool settings helpers", () => {
  it("offers the risk classes up to the tool's own", () => {
    expect(risksUpTo("passive").map((one) => one.value)).toEqual(["passive"]);
    expect(risksUpTo("intrusive").map((one) => one.value)).toEqual([
      "passive",
      "active",
      "intrusive",
    ]);
  });

  it("says where a tool runs, or what stops it", () => {
    expect(whereOf(nmap.effective)).toBe("Local");
    expect(whereOf(custom.effective)).toBe("Docker (the other way, as the default allows)");
    expect(whereOf(nuclei.effective)).toBe("Program not found");
  });

  it("offers to follow the default, Local or Docker", () => {
    expect(MODE_CHOICES.map((one) => one.value)).toEqual([null, "local", "docker"]);
  });

  it("knows when something was set for a tool", () => {
    expect(customised(nmap)).toBe(false);
    expect(customised(custom)).toBe(true);
    expect(customised({ ...nmap, overrides: { ...noOverrides, cpus: "1.5" } })).toBe(true);
    expect(customised({ ...nmap, overrides: { ...noOverrides, enabled: false } })).toBe(true);
  });

  it("turns settings into a form and back, with empty fields as null", () => {
    const set = {
      ...noOverrides,
      mode: "local" as const,
      binary_path: "/opt/nmap",
      image: "x@sha256:" + "b".repeat(64),
      cpus: "1.5",
      memory_mb: 512,
      timeout_s: 30,
      max_output_mb: 4,
      rate_per_s: 2.5,
      max_risk: "passive" as const,
    };
    const draft = draftOf({ ...nmap, overrides: set });
    expect(draft).toMatchObject({ binary_path: "/opt/nmap", cpus: "1.5", memory_mb: "512" });
    // The image belongs to Docker, so it is left out of a Local setting.
    expect(bodyOf(draft)).toEqual({ ...set, image: null });
    expect(bodyOf({ ...draft, mode: "docker" })).toEqual({
      ...set,
      mode: "docker",
      binary_path: null,
    });
    expect(bodyOf({ ...draft, mode: null })).toEqual({ ...set, mode: null });
    expect(bodyOf(draftOf(nmap))).toEqual(noOverrides);
    expect(bodyOf({ ...draftOf(nmap), timeout_s: "  ", binary_path: "  " })).toEqual(noOverrides);
  });
});

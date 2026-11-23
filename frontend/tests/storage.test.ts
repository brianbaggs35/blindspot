import { afterEach, describe, expect, it, vi } from "vitest";
import { readSetting, writeSetting } from "../src/storage";

describe("storage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps and returns a setting", () => {
    expect(readSetting("blindspot.x")).toBeNull();
    writeSetting("blindspot.x", "1");
    expect(readSetting("blindspot.x")).toBe("1");
  });

  it("carries on when the browser blocks storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readSetting("blindspot.x")).toBeNull();
    expect(() => {
      writeSetting("blindspot.x", "1");
    }).not.toThrow();
  });
});

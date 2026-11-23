import { describe, expect, it } from "vitest";
import { browserName, formatWhen } from "../src/format";
import { allMet, passwordRules } from "../src/passwords";

describe("password rules", () => {
  it("marks each rule as it is met", () => {
    const rules = (password: string, username = "ann") =>
      Object.fromEntries(passwordRules(password, username).map((rule) => [rule.id, rule.met]));
    expect(rules("")).toEqual({ length: false, short: true, variety: false, username: true });
    expect(rules("aaaaaaaaaaaaaaaa")).toMatchObject({ length: true, variety: false });
    expect(rules("x".repeat(300))).toMatchObject({ short: false });
    expect(rules("my-ANN-secret-phrase")).toMatchObject({ username: false });
    expect(rules("my-ANN-secret-phrase", "an")).toMatchObject({ username: true });
    expect(rules("my-ANN-secret-phrase", "  ")).toMatchObject({ username: true });
  });

  it("is all met for a good password", () => {
    expect(allMet(passwordRules("correct horse battery", "ann"))).toBe(true);
    expect(allMet(passwordRules("short", "ann"))).toBe(false);
  });
});

describe("format", () => {
  it("shows a time in the reader's style, or a dash", () => {
    expect(formatWhen(null)).toBe("—");
    expect(formatWhen("2026-11-20T10:00:00Z")).toMatch(/2026/);
  });

  it.each([
    [null, "An unknown browser"],
    ["Mozilla/5.0 (Windows NT 10.0) Edg/130", "Edge on Windows"],
    ["Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Firefox/130.0", "Firefox on Linux"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130 Safari/537", "Chrome on macOS"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/605", "Safari on iOS"],
    ["Mozilla/5.0 (Linux; Android 14) Chrome/130", "Chrome on Android"],
    ["curl/8", "A browser"],
  ])("names %s as %s", (agent, name) => {
    expect(browserName(agent)).toBe(name);
  });
});

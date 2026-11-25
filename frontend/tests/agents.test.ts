import { describe, expect, it } from "vitest";
import {
  BUDGET_FIELDS,
  budgetProblem,
  describeEvent,
  dollars,
  duration,
  isLive,
  lineDiff,
  percent,
  pruneTree,
  testRows,
} from "../src/agents";
import { budget, event, tree } from "./agents-fixtures";

describe("agents helpers", () => {
  it("knows which missions are still going", () => {
    expect(["pending", "running", "cancelling"].every(isLive)).toBe(true);
    expect(["paused", "completed", "stopped"].some(isLive)).toBe(false);
  });

  it("accepts the built-in caps and says which cap is wrong", () => {
    expect(budgetProblem(budget)).toBe("");
    expect(budgetProblem({ ...budget, steps: 0 })).toBe(
      "Steps in a mission must be between 1 and 100000.",
    );
    expect(budgetProblem({ ...budget, steps_per_test: Number.NaN })).toContain("Steps in a test");
    expect(budgetProblem({ ...budget, concurrency: 2.5 })).toBe(
      "Tests at the same time must be a whole number.",
    );
    expect(budgetProblem({ ...budget, cost_usd: 0.25 })).toBe("");
    expect(BUDGET_FIELDS).toHaveLength(8);
  });

  it("words rates, money and time", () => {
    expect(percent(null)).toBe("—");
    expect(percent(0.667)).toBe("67%");
    expect(dollars(null)).toBe("—");
    expect(dollars(undefined)).toBe("—");
    expect(dollars(1.5)).toBe("$1.50");
    expect(duration(45)).toBe("45 s");
    expect(duration(600)).toBe("10 min");
    expect(duration(7200)).toBe("2 h");
  });

  it("narrows the tree to what matches", () => {
    expect(pruneTree(tree, "", null).children.map((one) => one.children.length)).toEqual([2, 1]);
    const byTest = pruneTree(tree, " http ", null);
    expect(byTest.children.map((one) => one.id)).toEqual(["WSTG-CONF"]);
    expect(byTest.children[0]?.children.map((one) => one.id)).toEqual(["WSTG-CONF-06"]);
    const byCategory = pruneTree(tree, "authentication", null);
    expect(byCategory.children[0]?.children).toHaveLength(1);
    expect(pruneTree(tree, "WSTG-CONF-01", null).children[0]?.children).toHaveLength(1);
    const byRisk = pruneTree(tree, "", "intrusive");
    expect(byRisk.children.map((one) => one.id)).toEqual(["WSTG-ATHN"]);
    expect(pruneTree(tree, "nothing like this", null).children).toEqual([]);
    expect(pruneTree(tree, "configuration", "safe").children[0]?.children).toHaveLength(1);
  });

  it("lists every test with its category", () => {
    const rows = testRows(tree);
    expect(rows.map((row) => row.node.id)).toEqual([
      "WSTG-CONF-01",
      "WSTG-CONF-06",
      "WSTG-ATHN-02",
    ]);
    expect(rows[2]?.category).toBe("Authentication");
  });

  it("shows what changed between two texts, line by line", () => {
    expect(lineDiff("a\nb", "a\nb")).toEqual([
      { kind: "same", text: "a" },
      { kind: "same", text: "b" },
    ]);
    expect(lineDiff("a\nb\nc", "a\nc\nd")).toEqual([
      { kind: "same", text: "a" },
      { kind: "removed", text: "b" },
      { kind: "same", text: "c" },
      { kind: "added", text: "d" },
    ]);
    expect(lineDiff("a", "b")).toEqual([
      { kind: "removed", text: "a" },
      { kind: "added", text: "b" },
    ]);
    expect(lineDiff("", "x\ny").filter((line) => line.kind === "added")).toHaveLength(2);
    expect(lineDiff("x\ny", "x").at(-1)).toEqual({ kind: "removed", text: "y" });
  });

  it("does not compare very long texts line by line", () => {
    const long = Array.from({ length: 700 }, (_, at) => `line ${String(at)}`).join("\n");
    const lines = lineDiff(long, "short");
    expect(lines.filter((line) => line.kind === "removed")).toHaveLength(700);
    expect(lines.filter((line) => line.kind === "added")).toEqual([
      { kind: "added", text: "short" },
    ]);
  });

  it("puts each log entry in words", () => {
    const say = (type: string, data: Record<string, unknown> = {}) =>
      describeEvent(event({ type, data }));
    expect(say("mission_started", { runs: 3, skipped: 1 })).toBe(
      "Mission started: 3 tests to run, 1 skipped.",
    );
    expect(say("mission_started")).toBe("Mission started: 0 tests to run, 0 skipped.");
    expect(say("mission_paused", { reason: "Paused by a person." })).toBe(
      "Mission paused. Paused by a person.",
    );
    expect(say("mission_paused")).toBe("Mission paused.");
    expect(say("mission_resumed")).toBe("Mission resumed.");
    expect(say("mission_cancelling")).toBe("Mission is being cancelled.");
    expect(say("mission_cancelled")).toBe("Mission cancelled.");
    expect(say("mission_completed")).toBe("Mission completed.");
    expect(say("mission_failed")).toContain("failed");
    expect(say("mission_recovered")).toContain("restarted");
    expect(say("mission_stopped", { reason: "The mission used its 300 steps." })).toBe(
      "Mission stopped. The mission used its 300 steps.",
    );
    expect(say("test_started", { test: "WSTG-CONF-01" })).toBe("Started test WSTG-CONF-01.");
    expect(say("test_failed")).toContain("could not be done");
    expect(say("category_done")).toContain("finished");
    expect(say("step_started", { seq: 2, tool: "c.nmap" })).toBe("Step 2: c.nmap started.");
    expect(say("approval_needed", { seq: 2 })).toContain("waiting for a person");
    expect(say("step_approved", { seq: 2, by: "ada" })).toBe("Step 2 approved by ada.");
    expect(say("step_denied", { seq: 2, by: "ada" })).toBe("Step 2 denied by ada.");
    expect(say("something_new")).toBe("something new");
  });
});

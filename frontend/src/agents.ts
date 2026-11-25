// What the agent screens share: the words for statuses and risk, the caps a mission has, the
// pruning of the agent tree, and the line diff between two prompt versions.
import type { AgentNode, Budget, MissionEvent, RiskClass } from "./api/types";

export const RISK_LABELS: Record<RiskClass, string> = {
  safe: "Safe: only observes",
  active: "Active: sends probing requests",
  intrusive: "Intrusive: can change data or disturb the service",
};

export const RISK_COLORS: Record<RiskClass, string> = {
  safe: "success",
  active: "warning",
  intrusive: "error",
};

export const RISKS: RiskClass[] = ["safe", "active", "intrusive"];

export const STATUS_LABELS: Record<string, string> = {
  pending: "Waiting to start",
  running: "Running",
  paused: "Paused",
  cancelling: "Cancelling",
  cancelled: "Cancelled",
  completed: "Completed",
  failed: "Failed",
  stopped: "Stopped on a cap",
  waiting: "Waiting for a person",
  done: "Done",
  skipped: "Will not run",
  planned: "Planned",
  awaiting_approval: "Needs approval",
  approved: "Approved",
  denied: "Denied",
  interrupted: "Interrupted",
};

export const STATUS_COLORS: Record<string, string> = {
  running: "primary",
  completed: "success",
  done: "success",
  approved: "success",
  failed: "error",
  denied: "error",
  stopped: "warning",
  paused: "warning",
  waiting: "warning",
  awaiting_approval: "warning",
  interrupted: "warning",
};

/** Whether a mission is still going (or may be picked up again), so a page keeps watching it. */
export function isLive(status: string): boolean {
  return ["pending", "running", "cancelling"].includes(status);
}

export const PROMPT_AGENTS: Record<string, string> = {
  "test-agent": "Test agent",
  verifier: "Verifier",
};

export interface BudgetField {
  key: Exclude<keyof Budget, "verify_from">;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
}

export const BUDGET_FIELDS: BudgetField[] = [
  {
    key: "steps",
    label: "Steps in a mission",
    hint: "Every tool run counts",
    min: 1,
    max: 100_000,
    step: 1,
  },
  {
    key: "steps_per_test",
    label: "Steps in a test",
    hint: "A test stops here",
    min: 1,
    max: 200,
    step: 1,
  },
  {
    key: "tokens",
    label: "Tokens in a mission",
    hint: "Model input and output",
    min: 1000,
    max: 1_000_000_000,
    step: 1000,
  },
  {
    key: "tokens_per_test",
    label: "Tokens in a test",
    hint: "A test stops here",
    min: 1000,
    max: 100_000_000,
    step: 1000,
  },
  {
    key: "cost_usd",
    label: "Cost cap in a mission (USD)",
    hint: "Model spend; 0 allows none",
    min: 0,
    max: 100_000,
    step: 1,
  },
  {
    key: "seconds",
    label: "Seconds in a mission",
    hint: "Time spent working",
    min: 10,
    max: 1_209_600,
    step: 60,
  },
  {
    key: "seconds_per_test",
    label: "Seconds in a test",
    hint: "A test stops here",
    min: 5,
    max: 86_400,
    step: 30,
  },
  {
    key: "concurrency",
    label: "Tests at the same time",
    hint: "More is faster and louder",
    min: 1,
    max: 16,
    step: 1,
  },
];

/** The first cap that falls outside what the server takes, said in words; empty when all fit. */
export function budgetProblem(budget: Budget): string {
  for (const field of BUDGET_FIELDS) {
    const value = budget[field.key];
    if (!Number.isFinite(value) || value < field.min || value > field.max) {
      return `${field.label} must be between ${String(field.min)} and ${String(field.max)}.`;
    }
    if (field.key !== "cost_usd" && !Number.isInteger(value)) {
      return `${field.label} must be a whole number.`;
    }
  }
  return "";
}

export function percent(rate: number | null): string {
  return rate === null ? "—" : `${String(Math.round(rate * 100))}%`;
}

export function dollars(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `$${value.toFixed(2)}`;
}

/** Seconds as the biggest unit that reads well: "45 s", "12 min", "3 h". */
export function duration(seconds: number): string {
  if (seconds < 90) return `${String(Math.round(seconds))} s`;
  if (seconds < 5400) return `${String(Math.round(seconds / 60))} min`;
  return `${String(Math.round(seconds / 3600))} h`;
}

/** The tree with only what matches: a test whose name, id or risk fits, and its category. A
 * category whose own name fits keeps all of its tests that fit the risk. */
export function pruneTree(root: AgentNode, query: string, risk: RiskClass | null): AgentNode {
  const needle = query.trim().toLowerCase();
  const fits = (node: AgentNode) =>
    needle === "" ||
    node.name.toLowerCase().includes(needle) ||
    node.id.toLowerCase().includes(needle);
  const children = root.children.flatMap((category) => {
    const tests = category.children.filter(
      (test) => (risk === null || test.risk_class === risk) && (fits(category) || fits(test)),
    );
    return tests.length > 0 ? [{ ...category, children: tests }] : [];
  });
  return { ...root, children };
}

export interface TestRow {
  node: AgentNode;
  category: string;
}

/** Every test agent with the name of its category, for the grid. */
export function testRows(root: AgentNode): TestRow[] {
  return root.children.flatMap((category) =>
    category.children.map((node) => ({ node, category: category.name })),
  );
}

export interface DiffLine {
  kind: "same" | "added" | "removed";
  text: string;
}

const DIFF_LIMIT = 600;

/** The lines two texts share and the ones that differ, in order. Texts longer than the limit are
 * shown as wholly replaced instead of being compared line by line. */
export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  if (a.length > DIFF_LIMIT || b.length > DIFF_LIMIT) {
    return [
      ...a.map((text): DiffLine => ({ kind: "removed", text })),
      ...b.map((text): DiffLine => ({ kind: "added", text })),
    ];
  }
  // How many lines the two share from a pair of positions to the end, filled from the back.
  const width = b.length + 1;
  const common = new Map<number, number>();
  const at = (i: number, j: number) => common.get(i * width + j) ?? 0;
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      const shared =
        a.at(i) === b.at(j) ? at(i + 1, j + 1) + 1 : Math.max(at(i + 1, j), at(i, j + 1));
      common.set(i * width + j, shared);
    }
  }
  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a.at(i) === b.at(j)) {
      lines.push({ kind: "same", text: a.at(i) ?? "" });
      i++;
      j++;
    } else if (at(i + 1, j) >= at(i, j + 1)) {
      lines.push({ kind: "removed", text: a.at(i++) ?? "" });
    } else {
      lines.push({ kind: "added", text: b.at(j++) ?? "" });
    }
  }
  for (; i < a.length; i++) lines.push({ kind: "removed", text: a.at(i) ?? "" });
  for (; j < b.length; j++) lines.push({ kind: "added", text: b.at(j) ?? "" });
  return lines;
}

/** One line of the mission's log in words. */
export function describeEvent(event: MissionEvent): string {
  const data = new Map(Object.entries(event.data));
  const word = (key: string) => {
    const found = data.get(key);
    return typeof found === "string" ? found : "";
  };
  const count = (key: string) => {
    const found = data.get(key);
    return String(typeof found === "number" ? found : 0);
  };
  switch (event.type) {
    case "mission_started":
      return `Mission started: ${count("runs")} tests to run, ${count("skipped")} skipped.`;
    case "mission_paused":
      return `Mission paused. ${word("reason")}`.trim();
    case "mission_resumed":
      return "Mission resumed.";
    case "mission_cancelling":
      return "Mission is being cancelled.";
    case "mission_stopped":
      return `Mission stopped. ${word("reason")}`.trim();
    case "mission_completed":
      return "Mission completed.";
    case "mission_cancelled":
      return "Mission cancelled.";
    case "mission_failed":
      return "Mission failed. The server's log has the detail.";
    case "mission_recovered":
      return "The server restarted; the mission carried on.";
    case "test_started":
      return `Started test ${word("test")}.`;
    case "test_failed":
      return "A test could not be done.";
    case "category_done":
      return "A category is finished.";
    case "step_started":
      return `Step ${count("seq")}: ${word("tool")} started.`;
    case "approval_needed":
      return `Step ${count("seq")} is waiting for a person to approve it.`;
    case "step_approved":
      return `Step ${count("seq")} approved by ${word("by")}.`;
    case "step_denied":
      return `Step ${count("seq")} denied by ${word("by")}.`;
    default:
      return event.type.replaceAll("_", " ");
  }
}

import type { PlaybookSource, RiskClass, SpecDiff, TestSummary } from "./api/types";

export const RISKS: Record<RiskClass, { label: string; hint: string; color: string }> = {
  safe: {
    label: "Safe",
    hint: "Only observes: reads pages, headers and public sources.",
    color: "success",
  },
  active: {
    label: "Active",
    hint: "Sends requests the application was not built to expect.",
    color: "warning",
  },
  intrusive: {
    label: "Intrusive",
    hint: "Can change data or disturb the service. Always asks first.",
    color: "error",
  },
};

export const SOURCES: Record<PlaybookSource, { label: string; hint: string }> = {
  generated: { label: "Generated", hint: "Built from the category's template and the test." },
  authored: { label: "Hand-written", hint: "Written by hand for this test." },
  custom: { label: "Changed here", hint: "An administrator replaced the playbook." },
};

/** Lines of a text box as a list: one entry per line, blanks dropped. */
export function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

/** A list as the lines of a text box. */
export function joinLines(items: string[]): string {
  return items.join("\n");
}

export interface Filter {
  text: string;
  risks: RiskClass[];
}

/** The tests that match what was typed (in the id, the name or a tool) and the risks chosen. */
export function matching(tests: TestSummary[], filter: Filter): TestSummary[] {
  const needle = filter.text.trim().toLowerCase();
  return tests.filter(
    (test) =>
      (filter.risks.length === 0 || filter.risks.includes(test.risk_class)) &&
      (needle === "" ||
        test.id.toLowerCase().includes(needle) ||
        test.name.toLowerCase().includes(needle) ||
        test.tools.some((tool) => tool.includes(needle))),
  );
}

/** Whether an update would change anything. */
export function isEmptyDiff(diff: SpecDiff): boolean {
  return (
    diff.added.length +
      diff.removed.length +
      diff.changed.length +
      diff.categories_added.length +
      diff.categories_removed.length +
      diff.details_changed.length ===
    0
  );
}

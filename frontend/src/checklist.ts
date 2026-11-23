import type { CheckCategory, CheckItem, CheckStatus } from "./api/types";

// Each state once: its words, what it means and its colour. The lookups below are made from it.
const STATES: readonly {
  value: CheckStatus;
  label: string;
  hint: string;
  color: string;
}[] = [
  { value: "todo", label: "To do", hint: "Nobody has started", color: "default" },
  { value: "in_progress", label: "In progress", hint: "Being looked at", color: "info" },
  { value: "passed", label: "Passed", hint: "Done, and no weakness was found", color: "success" },
  { value: "finding", label: "Finding", hint: "Done, and a weakness was found", color: "error" },
  { value: "blocked", label: "Blocked", hint: "Cannot be tested yet", color: "warning" },
  {
    value: "not_applicable",
    label: "Not applicable",
    hint: "Does not apply to this target",
    color: "default",
  },
];

function lookup(pick: (state: (typeof STATES)[number]) => string): Record<CheckStatus, string> {
  return Object.fromEntries(STATES.map((state) => [state.value, pick(state)])) as Record<
    CheckStatus,
    string
  >;
}

export const STATUS_ORDER: readonly CheckStatus[] = STATES.map((state) => state.value);
export const CHECK_LABELS = lookup((state) => state.label);
export const CHECK_HINTS = lookup((state) => state.hint);
export const CHECK_COLORS = lookup((state) => state.color);
/** The states as the items of a select. */
export const CHECK_CHOICES = STATES.map((state) => ({
  value: state.value,
  title: state.label,
  subtitle: state.hint,
}));

/** A test is finished once somebody has said what came of it, or that it does not apply. */
const FINISHED: readonly CheckStatus[] = ["passed", "finding", "not_applicable"];

export function finished(counts: Record<CheckStatus, number>): number {
  return counts.passed + counts.finding + counts.not_applicable;
}

/** Whole percent of tests finished. An empty checklist is complete. */
export function percent(done: number, total: number): number {
  return total === 0 ? 100 : Math.floor((done * 100) / total);
}

export function categoryFinished(category: CheckCategory): number {
  return category.tests.filter((test) => FINISHED.includes(test.status)).length;
}

export interface CheckFilter {
  text: string;
  status: CheckStatus | null;
  appliesOnly: boolean;
}

export function isFiltering(filter: CheckFilter): boolean {
  return filter.text.trim() !== "" || filter.status !== null || filter.appliesOnly;
}

/** The tests that match what was typed (in the id, name or notes), the state and "applies". */
export function matching(tests: CheckItem[], filter: CheckFilter): CheckItem[] {
  const words = filter.text.toLowerCase().split(/\s+/).filter(Boolean);
  return tests.filter((test) => {
    if (filter.status !== null && test.status !== filter.status) return false;
    if (filter.appliesOnly && !test.applies) return false;
    const haystack = `${test.test_id} ${test.name} ${test.notes}`.toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

import type {
  EvidenceKind,
  Finding,
  FindingConfidence,
  FindingDraft,
  FindingEvent,
  FindingSource,
  FindingStatus,
  FindingVerification,
  Severity,
} from "./api/types";

export const STATUS_CHOICES: readonly { value: FindingStatus; title: string; color: string }[] = [
  { value: "new", title: "New", color: "info" },
  { value: "confirmed", title: "Confirmed", color: "error" },
  { value: "retest_needed", title: "Retest needed", color: "warning" },
  { value: "fixed", title: "Fixed", color: "success" },
  { value: "accepted_risk", title: "Accepted risk", color: "default" },
  { value: "false_positive", title: "False positive", color: "default" },
];
export const STATUS_LABELS = Object.fromEntries(
  STATUS_CHOICES.map((one) => [one.value, one.title]),
) as Record<FindingStatus, string>;
export const STATUS_COLORS = Object.fromEntries(
  STATUS_CHOICES.map((one) => [one.value, one.color]),
) as Record<FindingStatus, string>;

export const CONFIDENCE_CHOICES: { value: FindingConfidence; title: string }[] = [
  { value: "tentative", title: "Tentative" },
  { value: "firm", title: "Firm" },
  { value: "certain", title: "Certain" },
];

export const CONFIDENCE_LABELS = Object.fromEntries(
  CONFIDENCE_CHOICES.map((one) => [one.value, one.title]),
) as Record<FindingConfidence, string>;

export const SOURCE_LABELS: Record<FindingSource, string> = {
  manual: "Written by hand",
  agent: "Found by an agent",
  result: "Made from a result",
  import: "Imported",
};

export const VERIFICATION_LABELS: Record<FindingVerification, string> = {
  unverified: "Not verified",
  confirmed: "Verified",
  unconfirmed: "Could not be reproduced",
};

export const EVIDENCE_KINDS: { value: EvidenceKind; title: string }[] = [
  { value: "note", title: "A note" },
  { value: "request_response", title: "A request and its response" },
  { value: "screenshot", title: "A screenshot" },
  { value: "result", title: "A result of this pentest" },
];

export const SORTS = [
  { value: "severity", title: "Severity" },
  { value: "cvss", title: "CVSS score" },
  { value: "number", title: "Number" },
  { value: "updated", title: "Last change" },
  { value: "title", title: "Title" },
] as const;
export type SortKey = (typeof SORTS)[number]["value"];

export const GROUPS = [
  { value: null, title: "No grouping" },
  { value: "category", title: "Test category" },
  { value: "target", title: "Target" },
  { value: "severity", title: "Severity" },
] as const;
export type GroupKey = Exclude<(typeof GROUPS)[number]["value"], null>;

/** How many the counts of a list give for a key, none when it is not there. */
export const countOf = (counts: Record<string, number>, key: string): number =>
  new Map(Object.entries(counts)).get(key) ?? 0;

/** What a finding is called in speech: F-12. */
export const label = (number: number): string => `F-${String(number)}`;

/** The best score a finding has, as the number a person reads, or an empty string. */
export function scoreOf(finding: { cvss4_score: string | null; cvss31_score: string | null }) {
  return finding.cvss4_score ?? finding.cvss31_score ?? "";
}

export interface Filters {
  view: "live" | "trash";
  q: string;
  status: FindingStatus[];
  severity: Severity[];
  test: string;
  target: string;
  sort: SortKey;
  order: "asc" | "desc";
  group: GroupKey | null;
  offset: number;
}

/** The query string of the findings list: only what is set. */
export function listQuery(filters: Filters, limit = 50): string {
  const query = new URLSearchParams({
    view: filters.view,
    sort: filters.sort,
    order: filters.order,
    limit: String(limit),
  });
  if (filters.q.trim() !== "") query.set("q", filters.q.trim());
  for (const one of filters.status) query.append("status", one);
  for (const one of filters.severity) query.append("severity", one);
  if (filters.test.trim() !== "") query.set("test", filters.test.trim());
  if (filters.target.trim() !== "") query.set("target", filters.target.trim());
  if (filters.group) query.set("group_by", filters.group);
  if (filters.offset > 0) query.set("offset", String(filters.offset));
  return query.toString();
}

export function emptyDraft(): FindingDraft {
  return {
    title: "",
    description: "",
    target: "",
    test_ids: [],
    cwe: [],
    owasp: null,
    cvss31_vector: null,
    cvss4_vector: null,
    severity: null,
    confidence: "firm",
    remediation: "",
    references: [],
  };
}

export function draftOf(finding: Finding): FindingDraft {
  return {
    title: finding.title,
    description: finding.description,
    target: finding.target,
    test_ids: [...finding.test_ids],
    cwe: [...finding.cwe],
    owasp: finding.owasp,
    cvss31_vector: finding.cvss31_vector,
    cvss4_vector: finding.cvss4_vector,
    severity: finding.severity,
    confidence: finding.confidence,
    remediation: finding.remediation,
    references: [...finding.references],
  };
}

/** Words typed with commas, spaces or new lines, as the list they stand for. */
export function words(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).filter((one) => one !== ""))];
}

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const STATUS_NAMES = new Map<string, string>(STATUS_CHOICES.map((one) => [one.value, one.title]));
export const statusName = (value: unknown): string => STATUS_NAMES.get(text(value)) ?? text(value);

/** One line of the timeline, in words. */
export function describeEvent(event: FindingEvent): string {
  const data = event.data;
  switch (event.kind) {
    case "created":
      return "Created.";
    case "updated":
      return `Changed ${Array.isArray(data["fields"]) ? data["fields"].map(String).join(", ") : "it"}.`;
    case "status":
      return `Status changed from ${statusName(data["before"])} to ${statusName(data["after"])}.`;
    case "verified":
      return `${text(data["by"]) === "manual" ? "A person" : "The verifier"} ${
        text(data["outcome"]) === "confirmed" ? "confirmed" : "could not reproduce"
      } it.`;
    case "retest_requested":
      return "A retest was asked for.";
    case "comment":
      return text(data["body"]);
    case "evidence_added":
      return `Added evidence: ${text(data["title"])}.`;
    case "evidence_removed":
      return `Removed evidence: ${text(data["title"])}.`;
    case "merged_into":
      return `Merged into F-${String(data["number"])}.`;
    case "merged_from":
      return `F-${String(data["number"])} was merged into this one.`;
    case "seen_again":
      return "An agent found it again.";
    case "deleted":
      return "Moved to the trash.";
    case "restored":
      return "Restored from the trash.";
    default:
      return event.kind.replaceAll("_", " ");
  }
}

// ---- CVSS ----------------------------------------------------------------------------------

export interface Metric {
  key: string;
  name: string;
  options: { value: string; title: string }[];
}

const option = (value: string, title: string) => ({ value, title });
const ATTACK_VECTOR = [
  option("N", "Network"),
  option("A", "Adjacent"),
  option("L", "Local"),
  option("P", "Physical"),
];
const LOW_HIGH = [option("L", "Low"), option("H", "High")];
const PRIVILEGES = [option("N", "None"), option("L", "Low"), option("H", "High")];
const IMPACT = [option("H", "High"), option("L", "Low"), option("N", "None")];

export const CVSS_VERSIONS = {
  "3.1": {
    prefix: "CVSS:3.1/",
    metrics: [
      { key: "AV", name: "Attack vector", options: ATTACK_VECTOR },
      { key: "AC", name: "Attack complexity", options: LOW_HIGH },
      { key: "PR", name: "Privileges required", options: PRIVILEGES },
      {
        key: "UI",
        name: "User interaction",
        options: [option("N", "None"), option("R", "Required")],
      },
      { key: "S", name: "Scope", options: [option("U", "Unchanged"), option("C", "Changed")] },
      { key: "C", name: "Confidentiality impact", options: IMPACT },
      { key: "I", name: "Integrity impact", options: IMPACT },
      { key: "A", name: "Availability impact", options: IMPACT },
    ] satisfies Metric[],
  },
  "4.0": {
    prefix: "CVSS:4.0/",
    metrics: [
      { key: "AV", name: "Attack vector", options: ATTACK_VECTOR },
      { key: "AC", name: "Attack complexity", options: LOW_HIGH },
      {
        key: "AT",
        name: "Attack requirements",
        options: [option("N", "None"), option("P", "Present")],
      },
      { key: "PR", name: "Privileges required", options: PRIVILEGES },
      {
        key: "UI",
        name: "User interaction",
        options: [option("N", "None"), option("P", "Passive"), option("A", "Active")],
      },
      { key: "VC", name: "Vulnerable system confidentiality", options: IMPACT },
      { key: "VI", name: "Vulnerable system integrity", options: IMPACT },
      { key: "VA", name: "Vulnerable system availability", options: IMPACT },
      { key: "SC", name: "Subsequent system confidentiality", options: IMPACT },
      { key: "SI", name: "Subsequent system integrity", options: IMPACT },
      { key: "SA", name: "Subsequent system availability", options: IMPACT },
    ] satisfies Metric[],
  },
} as const;
export type CvssVersion = keyof typeof CVSS_VERSIONS;
const specOf = (version: CvssVersion) =>
  version === "3.1" ? CVSS_VERSIONS["3.1"] : CVSS_VERSIONS["4.0"];

/** The metrics a vector sets, by key. Metrics the calculator has no field for are kept apart. */
export function parseVector(vector: string | null, version: CvssVersion): Map<string, string> {
  const found = new Map<string, string>();
  const { prefix } = specOf(version);
  if (vector?.startsWith(prefix) !== true) return found;
  for (const part of vector.slice(prefix.length).split("/")) {
    const [key, value] = part.split(":");
    if (key && value) found.set(key, value);
  }
  return found;
}

/** The vector the chosen metrics make, or null until every metric has a value. Metrics of the
 * old vector that the calculator has no field for (threat, environmental) stay as they were. */
export function buildVector(
  chosen: ReadonlyMap<string, string>,
  version: CvssVersion,
  before: string | null = null,
): string | null {
  const { prefix, metrics } = specOf(version);
  if (metrics.some((metric) => !chosen.has(metric.key))) return null;
  const known = new Set(metrics.map((metric) => metric.key));
  const extra = [...parseVector(before, version)].filter(([key]) => !known.has(key));
  const parts = [...metrics.map((metric) => [metric.key, chosen.get(metric.key)]), ...extra];
  return prefix + parts.map(([key, value]) => `${String(key)}:${String(value)}`).join("/");
}

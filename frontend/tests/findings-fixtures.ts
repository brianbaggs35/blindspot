import type {
  Finding,
  FindingEvidence,
  FindingEvent,
  FindingList,
  FindingSummary,
} from "../src/api/types";

export function summaryOf(changes: Partial<FindingSummary> = {}): FindingSummary {
  return {
    id: "f-1",
    number: 1,
    title: "Missing HSTS header",
    target: "https://shop.example.com",
    category: "Configuration",
    test_ids: ["WSTG-CONF-07"],
    severity: "high",
    confidence: "firm",
    status: "new",
    cvss31_score: null,
    cvss4_score: "8.7",
    verification: "unverified",
    source: "manual",
    evidence_count: 1,
    updated_at: "2026-11-25T10:00:00Z",
    deleted: false,
    merged_into: null,
    ...changes,
  };
}

export function listOf(
  items: FindingSummary[] = [summaryOf()],
  changes: Partial<FindingList> = {},
): FindingList {
  return {
    items,
    total: items.length,
    statuses: { new: items.length },
    severities: { high: items.length },
    groups: [],
    ...changes,
  };
}

export function evidenceOf(changes: Partial<FindingEvidence> = {}): FindingEvidence {
  return {
    id: "e-1",
    kind: "note",
    title: "How I saw it",
    body: "curl -I shows no Strict-Transport-Security",
    sealed: false,
    mime: null,
    result_id: null,
    result_title: null,
    created_at: "2026-11-25T10:00:00Z",
    ...changes,
  };
}

export function eventOf(changes: Partial<FindingEvent> = {}): FindingEvent {
  return {
    id: "v-1",
    kind: "created",
    actor: "ada",
    data: {},
    created_at: "2026-11-25T10:00:00Z",
    ...changes,
  };
}

export function findingOf(changes: Partial<Finding> = {}): Finding {
  return {
    ...summaryOf(),
    description: "The site never asks browsers to stay on HTTPS.",
    cwe: ["CWE-319"],
    owasp: "A05",
    cvss31_vector: null,
    cvss4_vector: "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N",
    remediation: "Send the header.",
    references: ["https://owasp.org/www-project-secure-headers/"],
    result_id: null,
    verified_by: null,
    verified_at: null,
    created_by: "u-1",
    created_at: "2026-11-25T09:00:00Z",
    allowed_statuses: ["confirmed", "false_positive", "accepted_risk"],
    evidence: [evidenceOf()],
    timeline: [eventOf()],
    duplicates: [],
    ...changes,
  };
}

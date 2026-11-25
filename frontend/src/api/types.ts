// What the API returns, as the account pages use it.
export type Role = "admin" | "viewer";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  last_sign_in_at: string | null;
  created_at: string;
  terms_accepted: boolean;
}

export interface TermsSection {
  id: string;
  title: string;
  paragraphs: string[];
}

export interface Terms {
  title: string;
  version: string;
  accepted: boolean;
  accepted_at: string | null;
  sections: TermsSection[];
}

export interface Status {
  setup_required: boolean;
  user: User | null;
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  ip_address: string | null;
  user_agent: string | null;
  current: boolean;
}

export interface PasskeyInfo {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  backup_eligible: boolean;
  backed_up: boolean;
  transports: string[];
}

export interface Ceremony {
  challenge_id: string;
  options: Record<string, unknown>;
}

export interface AuditEvent {
  id: string;
  created_at: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  outcome: string;
  target_type: string | null;
  target_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  detail: Record<string, unknown> | null;
}

export interface AuditPage {
  items: AuditEvent[];
  next_before: string | null;
}

export type ProviderKind = "anthropic" | "openai" | "ollama-local" | "ollama-cloud";

export interface KindInfo {
  kind: ProviderKind;
  label: string;
  default_base_url: string;
  needs_key: boolean;
}

/** Money and prices arrive as decimal strings, so no precision is lost on the way. */
export interface Provider {
  id: string;
  kind: ProviderKind;
  name: string;
  base_url: string;
  enabled: boolean;
  has_key: boolean;
  key_last4: string | null;
  monthly_budget_usd: string | null;
  hard_stop: boolean;
  spent_this_month_usd: string;
  model_count: number;
  created_at: string;
}

export interface Price {
  input: string | null;
  output: string | null;
  cache_read: string | null;
  cache_write: string | null;
  cache_write_long: string | null;
}

export type PriceSource = "override" | "catalog" | "free" | "unknown";

export interface ProviderModel {
  id: string;
  provider_id: string;
  model_id: string;
  display_name: string;
  context_tokens: number | null;
  max_output_tokens: number | null;
  capabilities: string[];
  supports_tools: boolean;
  enabled: boolean;
  price: Price;
  price_source: PriceSource;
  overrides: Price;
}

export interface DiscoveredModel {
  model_id: string;
  display_name: string;
  context_tokens: number | null;
  max_output_tokens: number | null;
  capabilities: string[];
  added: boolean;
  price_source: PriceSource;
}

export interface ConnectionReport {
  ok: boolean;
  latency_ms: number;
  model_count: number | null;
  failure: string | null;
  detail: string;
}

export interface RoleDefault {
  role: string;
  label: string;
  model_ref: string | null;
  provider_name: string | null;
  model_id: string | null;
}

export type RiskClass = "safe" | "active" | "intrusive";
export type PlaybookSource = "generated" | "authored" | "custom";

export interface Methodology {
  id: string;
  name: string;
  source_url: string;
  license: string;
  origin: "bundled" | "folder";
  enabled: boolean;
  version_number: number;
  version_label: string;
  content_hash: string;
  categories: number;
  tests: number;
  authored_playbooks: number;
  custom_playbooks: number;
  manual_review_tests: number;
  imported_at: string;
  can_update_from_upstream: boolean;
}

export interface TestSummary {
  id: string;
  name: string;
  reference: string | null;
  risk_class: RiskClass;
  tags: string[];
  requires: string[];
  tools: string[];
  manual_review: boolean;
  playbook_source: PlaybookSource;
}

export interface MethodologyCategory {
  id: string;
  name: string;
  reporting_label: string | null;
  tests: TestSummary[];
}

export interface MethodologyDetail extends Methodology {
  category_list: MethodologyCategory[];
}

export interface Playbook {
  summary: string;
  instructions: string;
  tools: string[];
  manual_review: boolean;
  safe_steps: string[];
  active_steps: string[];
  intrusive_steps: string[];
  evidence: string[];
  success: string;
  failure: string;
  not_applicable: string[];
}

export interface MethodologyTest {
  id: string;
  name: string;
  reference: string | null;
  objectives: string[];
  tags: string[];
  risk_class: RiskClass;
  requires: string[];
  approach: string | null;
  playbook: Playbook;
  playbook_source: PlaybookSource;
}

export interface TestDetail {
  methodology_id: string;
  category_id: string;
  category_name: string;
  test: MethodologyTest;
}

export interface SpecDiff {
  added: string[];
  removed: string[];
  changed: { id: string; fields: string[] }[];
  categories_added: string[];
  categories_removed: string[];
  details_changed: string[];
}

export interface UpdateCheck {
  source: string;
  current_hash: string;
  candidate_hash: string;
  candidate_label: string;
  changed: boolean;
  diff: SpecDiff;
}

export interface ReloadResult {
  added: string[];
  updates_available: string[];
  problems: Record<string, string>;
}

export type Box = "black" | "grey" | "white";
export type PentestStatus = "draft" | "authorized" | "running" | "paused" | "complete";
export type PentestView = "active" | "archived" | "trash" | "all";

export interface PentestSummary {
  id: string;
  name: string;
  client: string | null;
  status: PentestStatus;
  box: Box;
  methodology_id: string;
  targets: number;
  archived_at: string | null;
  deleted_at: string | null;
  updated_at: string;
}

export interface TestingWindow {
  start: string;
  end: string;
  timezone: string;
}

export interface PentestRules {
  max_risk: RiskClass;
  allow_destructive: boolean;
  requests_per_second: number;
  concurrency: number;
  window: TestingWindow | null;
  stop_on_first_critical: boolean;
  notes: string;
}

export interface PentestScope {
  in_scope: string[];
  out_of_scope: string[];
  excluded_paths: string[];
  methods: string[];
}

export interface PentestAccount {
  id: string;
  label: string;
  username: string;
  role_hint: string;
  has_secret: boolean;
}

export interface Attestation {
  id: string;
  attested_by_name: string;
  attested_at: string;
  ip_address: string | null;
  text_version: string;
  text: string;
  current: boolean;
}

export interface Letter {
  filename: string;
  content_type: string;
  size: number;
  sha256: string;
  uploaded_at: string;
}

export interface Pentest extends PentestSummary {
  description: string;
  methodology_name: string;
  methodology_version: number;
  features: string[];
  scope: PentestScope;
  compiled: PentestScope;
  rules: PentestRules;
  accounts: PentestAccount[];
  attestation: Attestation | null;
  letter: Letter | null;
  launch_problems: string[];
  created_at: string;
}

/** What a pentest form sends: a new pentest, or the parts of one that change. */
export interface PentestInput {
  name: string;
  client: string | null;
  description: string;
  methodology_id: string;
  box: Box;
  scope: PentestScope;
  rules: PentestRules;
}

export interface AttestationStatement {
  version: string;
  text: string;
}

export type CheckStatus =
  "todo" | "in_progress" | "passed" | "finding" | "blocked" | "not_applicable";

export interface Evidence {
  label: string;
  url: string;
}

export interface CheckItem {
  test_id: string;
  name: string;
  reference: string | null;
  risk_class: RiskClass | null;
  requires: string[];
  applies: boolean;
  status: CheckStatus;
  notes: string;
  evidence: Evidence[];
  custom: boolean;
  touched: boolean;
}

export interface CheckCategory {
  id: string;
  name: string;
  tests: CheckItem[];
}

export interface Checklist {
  methodology_name: string;
  methodology_version: number;
  features: string[];
  total: number;
  counts: Record<CheckStatus, number>;
  categories: CheckCategory[];
}

export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type ResultSource = "tool" | "import" | "manual";
export type ResultStatus = "ok" | "failed" | "manual";

export interface ResultSummary {
  id: string;
  title: string;
  source: ResultSource;
  status: ResultStatus;
  tool_id: string | null;
  agent_role: string | null;
  test_id: string | null;
  top_severity: Severity | null;
  issue_count: number;
  ran_at: string;
  tags: string[];
  deleted: boolean;
  summary: string[];
}

export interface ResultList {
  items: ResultSummary[];
  total: number;
  tools: string[];
  agents: string[];
}

export interface FriendlyCard {
  title: string;
  severity: Severity;
  target: string | null;
  what: string;
  why: string;
  todo: string;
}

export interface PortRow {
  port: number;
  protocol: string;
  state: string;
  service: string | null;
  software: string | null;
}

export interface Friendly {
  headline: string;
  summary: string[];
  cards: FriendlyCard[];
  hidden_cards: number;
  visuals: {
    port_map: { address: string; state: string; ports: PortRow[] }[];
    tls_grade: string | null;
    scorecard: { name: string; passed: boolean }[];
  };
  terms: { term: string; meaning: string }[];
}

export interface ResultCredential {
  index: number;
  target: string;
  kind: string;
  username: string | null;
  secret: string;
}

/** The normalized result: every list is there, and each item is a plain object. */
export type Technical = Record<string, unknown>;

export interface PentestResultFull extends ResultSummary {
  parser: string | null;
  command: string[];
  exit_code: number | null;
  duration_ms: number | null;
  notes: string;
  friendly: Friendly | null;
  technical: Technical | null;
  credentials: ResultCredential[];
  has_raw: boolean;
  created_by: string | null;
}

export interface RawOutput {
  command: string[];
  exit_code: number | null;
  duration_ms: number | null;
  output: string;
  truncated: boolean;
  size: number;
}

/** The caps of one mission. */
export interface Budget {
  steps: number;
  steps_per_test: number;
  tokens: number;
  tokens_per_test: number;
  cost_usd: number;
  seconds: number;
  seconds_per_test: number;
  concurrency: number;
  verify_from: Severity;
}

export interface AgentStats {
  runs: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
  cost_per_run_usd: number | null;
  last_run: string | null;
  active: boolean;
}

export interface AgentNode {
  id: string;
  name: string;
  kind: "commander" | "category" | "test";
  risk_class: RiskClass | null;
  tools: string[];
  stats: AgentStats;
  children: AgentNode[];
}

export interface AgentsOverview {
  methodology_id: string | null;
  methodologies: { id: string; name: string }[];
  commander: AgentNode | null;
  runner_ready: boolean;
}

export interface AgentPreset {
  id: string;
  name: string;
  summary: string;
  max_risk: RiskClass;
  budget: Budget;
}

export interface PromptVersion {
  version: number;
  note: string;
  created_at: string | null;
  created_by: string | null;
  active: boolean;
}

export interface PromptInfo {
  agent: string;
  label: string;
  active: number;
  versions: PromptVersion[];
}

export interface AgentSettings {
  budget: Budget;
  built_in_budget: Budget;
  presets: AgentPreset[];
  prompts: PromptInfo[];
  max_prompt: number;
}

export interface PromptBody {
  agent: string;
  version: number;
  note: string;
  body: string;
}

export interface PlanSummary {
  runs: number;
  skipped: number;
  risk: Record<RiskClass, number>;
  tools: string[];
  skips: { reason: string; tests: number }[];
  categories: { id: string; name: string; phase: number; runs: number; skipped: number }[];
}

export interface MissionPreview {
  summary: PlanSummary;
  budget: Budget;
  max_risk: RiskClass;
  prompts: Record<string, number>;
  in_scope: string[];
  runner_ready: boolean;
}

export interface StartRequest {
  preset?: string;
  budget?: Budget;
  max_risk?: RiskClass;
  only?: string[];
  confirmed?: boolean;
}

export interface Mission {
  id: string;
  pentest_id: string;
  status: string;
  budget: Budget;
  spent: { steps?: number; tokens?: number; cost_usd?: number; seconds?: number };
  plan: { runs?: number; skipped?: number; max_risk?: RiskClass };
  prompts: Record<string, number>;
  stop_reason: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface MissionTask {
  id: string;
  parent_id: string | null;
  kind: "commander" | "category" | "test";
  ref: string;
  name: string;
  phase: number;
  position: number;
  status: string;
  summary: string;
  outcome: Record<string, unknown> | null;
  spent: { steps?: number; tokens?: number; cost_usd?: number; seconds?: number };
}

export interface MissionStep {
  id: string;
  task_id: string;
  seq: number;
  status: string;
  tool: string;
  request: Record<string, unknown>;
  verdict: Record<string, unknown> | null;
  result_id: string | null;
  note: string;
  created_at: string;
}

export interface MissionEvent {
  id: number;
  task_id: string | null;
  type: string;
  data: Record<string, unknown>;
  created_at: string;
}

export type FindingStatus =
  "new" | "confirmed" | "false_positive" | "accepted_risk" | "fixed" | "retest_needed";
export type FindingConfidence = "tentative" | "firm" | "certain";
export type FindingSource = "manual" | "agent" | "result" | "import";
export type FindingVerification = "unverified" | "confirmed" | "unconfirmed";
export type EvidenceKind = "result" | "request_response" | "note" | "screenshot";

export interface FindingSummary {
  id: string;
  number: number;
  title: string;
  target: string;
  category: string;
  test_ids: string[];
  severity: Severity;
  confidence: FindingConfidence;
  status: FindingStatus;
  cvss31_score: string | null;
  cvss4_score: string | null;
  verification: FindingVerification;
  source: FindingSource;
  evidence_count: number;
  updated_at: string;
  deleted: boolean;
  merged_into: string | null;
}

export interface FindingList {
  items: FindingSummary[];
  total: number;
  statuses: Record<string, number>;
  severities: Record<string, number>;
  groups: { key: string; count: number }[];
}

export interface FindingEvidence {
  id: string;
  kind: EvidenceKind;
  title: string;
  body: string | null;
  sealed: boolean;
  mime: string | null;
  result_id: string | null;
  result_title: string | null;
  created_at: string;
}

export interface FindingEvent {
  id: string;
  kind: string;
  actor: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

export interface FindingDuplicate {
  id: string;
  number: number;
  title: string;
  status: FindingStatus;
  reason: string;
}

export interface Finding extends FindingSummary {
  description: string;
  cwe: string[];
  owasp: string | null;
  cvss31_vector: string | null;
  cvss4_vector: string | null;
  remediation: string;
  references: string[];
  result_id: string | null;
  verified_by: string | null;
  verified_at: string | null;
  created_by: string | null;
  created_at: string;
  allowed_statuses: FindingStatus[];
  evidence: FindingEvidence[];
  timeline: FindingEvent[];
  duplicates: FindingDuplicate[];
}

export interface FindingDraft {
  title: string;
  description: string;
  target: string;
  test_ids: string[];
  cwe: string[];
  owasp: string | null;
  cvss31_vector: string | null;
  cvss4_vector: string | null;
  severity: Severity | null;
  confidence: FindingConfidence;
  remediation: string;
  references: string[];
}

export interface CvssScore {
  vector: string;
  version: "3.1" | "4.0";
  score: string;
  severity: Severity;
}

export interface FindingsReference {
  owasp: Record<string, string>;
  transitions: Record<FindingStatus, FindingStatus[]>;
}

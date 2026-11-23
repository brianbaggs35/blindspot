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

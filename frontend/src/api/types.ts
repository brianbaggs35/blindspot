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

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

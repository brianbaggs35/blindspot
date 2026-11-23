// What the audit trail's action codes mean, in words. The API is the authority on the codes
// (backend/app/auth/*.py); a code this list does not know is shown as it is.
export const AUDIT_ACTIONS: ReadonlyMap<string, string> = new Map(
  Object.entries({
    "auth.setup": "First administrator created",
    "auth.login": "Signed in with a password",
    "auth.logout": "Signed out",
    "auth.password": "Changed own password",
    "auth.reauthenticate": "Confirmed password",
    "auth.lockout": "Account locked after failed sign-ins",
    "auth.session_end": "Ended a session",
    "passkey.add": "Added a passkey",
    "passkey.rename": "Renamed a passkey",
    "passkey.remove": "Removed a passkey",
    "passkey.login": "Signed in with a passkey",
    "passkey.clone_suspected": "Passkey may have been copied",
    "user.create": "Added an account",
    "user.update": "Changed an account",
    "user.password_reset": "Reset an account's password",
    "user.sign_out": "Signed an account out everywhere",
    "user.delete": "Deleted an account",
  }),
);

export function actionLabel(code: string): string {
  return AUDIT_ACTIONS.get(code) ?? code;
}

export interface AuditFilters {
  action: string;
  outcome: string;
  actor: string;
  /** A calendar day, `YYYY-MM-DD`, in the reader's time zone. */
  since: string;
}

export const NO_FILTERS: AuditFilters = { action: "", outcome: "", actor: "", since: "" };

/** The query string for the audit endpoint: only the filters that are set, plus the paging. */
export function auditQuery(filters: AuditFilters, before: string | null, limit = 50): string {
  const query = new URLSearchParams({ limit: String(limit) });
  if (filters.action !== "") query.set("action", filters.action);
  if (filters.outcome !== "") query.set("outcome", filters.outcome);
  if (filters.actor.trim() !== "") query.set("actor", filters.actor.trim());
  if (filters.since !== "") {
    // Midnight where the reader is, not in UTC, so "since 1 Nov" means their 1 November.
    query.set("since", new Date(`${filters.since}T00:00:00`).toISOString());
  }
  if (before !== null) query.set("before", before);
  return query.toString();
}

/** The detail of an event as short `key: value` text for a list line. */
export function detailText(detail: Record<string, unknown> | null): string {
  if (detail === null) return "";
  return Object.entries(detail)
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(", ");
}

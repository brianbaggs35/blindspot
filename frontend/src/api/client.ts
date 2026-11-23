// The one way the app talks to the API. Errors come back as RFC 9457 problem documents
// ({ code, title, detail }); they are turned into an ApiError so a screen can say something
// useful instead of "Request failed".

export type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string | undefined;
  readonly requestId: string | undefined;
  /** Seconds to wait, when the API said (429). */
  readonly retryAfter: number | undefined;

  constructor(
    status: number,
    code: string,
    title: string,
    extra: {
      detail?: string | undefined;
      requestId?: string | undefined;
      retryAfter?: number | undefined;
    } = {},
  ) {
    super(title);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = extra.detail;
    this.requestId = extra.requestId;
    this.retryAfter = extra.retryAfter;
  }
}

interface Problem {
  title?: unknown;
  code?: unknown;
  detail?: unknown;
  request_id?: unknown;
}

let onSessionEnded: (() => void) | undefined;

/** Called when the API says the person is no longer signed in (a 401 on a signed-in session). */
export function setSessionEndedHandler(handler: (() => void) | undefined): void {
  onSessionEnded = handler;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

async function problemOf(response: Response): Promise<ApiError> {
  let body: Problem = {};
  try {
    body = (await response.json()) as Problem;
  } catch {
    // Not JSON (a proxy's error page, say); the status is all there is.
  }
  const wait = Number(response.headers.get("Retry-After"));
  return new ApiError(
    response.status,
    text(body.code) ?? "error",
    text(body.title) ?? `The request failed (${String(response.status)})`,
    {
      detail: text(body.detail),
      requestId: text(body.request_id),
      retryAfter: Number.isFinite(wait) && wait > 0 ? wait : undefined,
    },
  );
}

async function send(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network", "Blindspot could not be reached. Check your connection.");
  }
  if (!response.ok) {
    const error = await problemOf(response);
    if (error.status === 401 && error.code === "not_signed_in") onSessionEnded?.();
    throw error;
  }
  return response;
}

export async function api<T = undefined>(method: Method, path: string, body?: unknown): Promise<T> {
  const response = await send(path, {
    method,
    headers: body === undefined ? { Accept: "application/json" } : jsonHeaders,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return (response.status === 204 ? undefined : await response.json()) as T;
}

/** Send a file as the whole request body (the API reads the bytes as they are). */
export async function upload<T>(path: string, file: Blob): Promise<T> {
  const response = await send(path, {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/octet-stream" },
    body: file,
  });
  return (await response.json()) as T;
}

const jsonHeaders = { Accept: "application/json", "Content-Type": "application/json" };

/** Refusals whose detail is the useful part (what is missing, what to do next), so it is shown too. */
const EXPLAINED = new Set(["terms_not_accepted", "cannot_launch", "out_of_scope"]);

/** The words to show a person for an error, with the request id when there is one to quote. */
export function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429 && error.retryAfter !== undefined) {
      return `Too many attempts. Try again in ${waitWords(error.retryAfter)}.`;
    }
    const words =
      error.detail !== undefined && EXPLAINED.has(error.code)
        ? `${error.message}. ${error.detail}`
        : error.message;
    return error.requestId === undefined ? words : `${words} (reference ${error.requestId})`;
  }
  return "Something went wrong. Try again.";
}

/** "2 minutes", "45 seconds": for "try again in ...". */
export function waitWords(seconds: number): string {
  if (seconds >= 120) return `${String(Math.ceil(seconds / 60))} minutes`;
  if (seconds >= 60) return "1 minute";
  return `${String(Math.max(1, Math.ceil(seconds)))} seconds`;
}

const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** A time from the API, in the reader's own language and time zone; a dash when there is none. */
export function formatWhen(iso: string | null): string {
  return iso === null ? "—" : when.format(new Date(iso));
}

/** The browser and system from a User-Agent line, short enough for a list. */
export function browserName(userAgent: string | null): string {
  if (userAgent === null) return "An unknown browser";
  const browser = /Edg\//.test(userAgent)
    ? "Edge"
    : /Firefox\//.test(userAgent)
      ? "Firefox"
      : /Chrome\//.test(userAgent)
        ? "Chrome"
        : /Safari\//.test(userAgent)
          ? "Safari"
          : "A browser";
  const system = /Windows/.test(userAgent)
    ? "Windows"
    : /Android/.test(userAgent)
      ? "Android"
      : /iPhone|iPad/.test(userAgent)
        ? "iOS"
        : /Mac OS X/.test(userAgent)
          ? "macOS"
          : /Linux/.test(userAgent)
            ? "Linux"
            : null;
  return system === null ? browser : `${browser} on ${system}`;
}

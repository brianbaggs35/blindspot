const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** A time from the API, in the reader's own language and time zone; a dash when there is none. */
export function formatWhen(iso: string | null): string {
  return iso === null ? "—" : when.format(new Date(iso));
}

// The first pattern that matches wins, so the more specific names come first (Edge and Chrome
// both say "Chrome", and Chrome says "Safari").
const BROWSERS: readonly (readonly [RegExp, string])[] = [
  [/Edg\//, "Edge"],
  [/Firefox\//, "Firefox"],
  [/Chrome\//, "Chrome"],
  [/Safari\//, "Safari"],
];

const SYSTEMS: readonly (readonly [RegExp, string])[] = [
  [/Windows/, "Windows"],
  [/Android/, "Android"],
  [/iPhone|iPad/, "iOS"],
  [/Mac OS X/, "macOS"],
  [/Linux/, "Linux"],
];

function firstMatch(table: readonly (readonly [RegExp, string])[], text: string): string | null {
  return table.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

/** The browser and system from a User-Agent line, short enough for a list. */
export function browserName(userAgent: string | null): string {
  if (userAgent === null) return "An unknown browser";
  const browser = firstMatch(BROWSERS, userAgent) ?? "A browser";
  const system = firstMatch(SYSTEMS, userAgent);
  return system === null ? browser : `${browser} on ${system}`;
}

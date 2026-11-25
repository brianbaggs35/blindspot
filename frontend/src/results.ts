import type { PentestResultFull, ResultSource, Severity, Technical } from "./api/types";
import { readSetting, writeSetting } from "./storage";

// Each severity once: its words and colour, most serious first.
const SEVERITIES: readonly { value: Severity; label: string; color: string }[] = [
  { value: "critical", label: "Critical", color: "error" },
  { value: "high", label: "High", color: "error" },
  { value: "medium", label: "Medium", color: "warning" },
  { value: "low", label: "Low", color: "info" },
  { value: "info", label: "Info", color: "default" },
];

export const SEVERITY_CHOICES = SEVERITIES.map(({ value, label }) => ({ value, title: label }));
export const SEVERITY_LABELS = Object.fromEntries(
  SEVERITIES.map((s) => [s.value, s.label]),
) as Record<Severity, string>;
export const SEVERITY_COLORS = Object.fromEntries(
  SEVERITIES.map((s) => [s.value, s.color]),
) as Record<Severity, string>;

export const SOURCE_LABELS: Record<ResultSource, string> = {
  tool: "Tool run",
  import: "Imported",
  manual: "Note",
};

/** The three ways to read a result. */
export const VIEWS = ["friendly", "technical", "raw"] as const;
export type ResultView = (typeof VIEWS)[number];
export const VIEW_LABELS: Record<ResultView, string> = {
  friendly: "Friendly",
  technical: "Technical",
  raw: "Raw",
};

const viewKey = (userId: string) => `blindspot.results-view.${userId}`;

/** The view this person last picked, or the friendly one. */
export function rememberedView(userId: string): ResultView {
  const stored = readSetting(viewKey(userId));
  return VIEWS.find((one) => one === stored) ?? "friendly";
}

export function rememberView(userId: string, view: ResultView): void {
  writeSetting(viewKey(userId), view);
}

/** A time span in words a person reads: "850 ms", "12.3 s", "3 min 5 s". */
export function duration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${String(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const minutes = Math.floor(ms / 60_000);
  return `${String(minutes)} min ${String(Math.round((ms % 60_000) / 1000))} s`;
}

const SHELL_SAFE = /^[\w@%+=:,./-]+$/;
const QUOTE_INSIDE = String.raw`'\''`;

function shellWord(part: string): string {
  return SHELL_SAFE.test(part) ? part : "'" + part.replaceAll("'", QUOTE_INSIDE) + "'";
}

/** The command exactly as it ran, one argument at a time: an argument with a space is quoted so
 * it reads the way a shell would take it, though no shell ever ran it. */
export function commandLine(command: string[]): string {
  return command.map(shellWord).join(" ");
}

export interface Segment {
  text: string;
  /** The glossary meaning, when this stretch of text is a term. */
  meaning?: string;
}

function isLetter(char: string): boolean {
  return /[A-Za-z]/.test(char);
}

/** A sentence cut into plain stretches and glossary terms, so the terms can carry a tooltip. A
 * term counts only as a whole word, in any case. */
export function withTerms(text: string, terms: { term: string; meaning: string }[]): Segment[] {
  const lower = text.toLowerCase();
  const found: Segment[] = [];
  let at = 0;
  let plainFrom = 0;
  while (at < text.length) {
    const term = terms.find((one) => {
      const word = one.term.toLowerCase();
      return (
        lower.startsWith(word, at) &&
        !isLetter(text.charAt(at - 1)) &&
        !isLetter(text.charAt(at + word.length))
      );
    });
    if (term === undefined) {
      at += 1;
      continue;
    }
    if (at > plainFrom) found.push({ text: text.slice(plainFrom, at) });
    found.push({ text: text.slice(at, at + term.term.length), meaning: term.meaning });
    at += term.term.length;
    plainFrom = at;
  }
  if (plainFrom < text.length) found.push({ text: text.slice(plainFrom) });
  return found;
}

export interface Section {
  key: string;
  title: string;
  headers: { title: string; key: string }[];
  items: Record<string, string | number>[];
}

const SECTIONS: readonly { key: string; title: string; columns: readonly string[] }[] = [
  {
    key: "issues",
    title: "Issues",
    columns: ["severity", "title", "target", "confidence", "reference"],
  },
  {
    key: "hosts",
    title: "Hosts and services",
    columns: ["address", "port", "protocol", "state", "name", "product", "version"],
  },
  {
    key: "http",
    title: "Web responses",
    columns: ["url", "status", "length", "content_type", "title", "server", "redirect", "input"],
  },
  {
    key: "technologies",
    title: "Technologies",
    columns: ["name", "version", "category", "target"],
  },
  { key: "tls", title: "TLS checks", columns: ["id", "severity", "finding", "host", "port"] },
  { key: "artifacts", title: "Files", columns: ["name", "kind", "size", "ref"] },
];

type Row = Record<string, unknown>;

function fieldsOf(row: Row): Map<string, unknown> {
  return new Map(Object.entries(row));
}

function cell(value: unknown): string | number {
  if (typeof value === "number") return value;
  if (typeof value === "string") return value;
  return value === null || value === undefined ? "" : JSON.stringify(value);
}

function rowsOf(key: string, list: Row[]): Row[] {
  if (key !== "hosts") return list;
  // A host is one row for each service, so the table can be sorted by port.
  return list.flatMap((host) => {
    const fields = fieldsOf(host);
    const services = (fields.get("services") as Row[] | undefined) ?? [];
    const base = { address: fields.get("address"), state: fields.get("state") };
    return services.length === 0 ? [base] : services.map((service) => ({ ...base, ...service }));
  });
}

/** The tables of the technical view: one for each list of the result that has something in it,
 * with the columns that have a value somewhere. */
export function sectionsOf(technical: Technical): Section[] {
  const lists = fieldsOf(technical);
  return SECTIONS.flatMap(({ key, title, columns }) => {
    const rows = rowsOf(key, (lists.get(key) as Row[] | undefined) ?? []).map(fieldsOf);
    if (rows.length === 0) return [];
    const used = columns.filter((column) => rows.some((row) => cell(row.get(column)) !== ""));
    return [
      {
        key,
        title,
        headers: used.map((column) => ({ title: column.replaceAll("_", " "), key: column })),
        items: rows.map((row) =>
          Object.fromEntries(used.map((column) => [column, cell(row.get(column))])),
        ),
      },
    ];
  });
}

export interface Token {
  text: string;
  kind: "plain" | "tag" | "string" | "number" | "key" | "match";
}

const SIMPLE: readonly [Token["kind"], RegExp][] = [
  ["tag", /^<\/?[\w:.-]+|^\/?>/],
  ["number", /^-?\d+\.\d+|^-?\d+/],
];

/** The length of the quoted string at the start of `text` (its quotes included), or 0. */
function quoted(text: string): number {
  if (!text.startsWith('"')) return 0;
  for (let at = 1; at < text.length; at += 1) {
    if (text.charAt(at) === "\\") at += 1;
    else if (text.charAt(at) === '"') return at + 1;
  }
  return 0;
}

function nextToken(rest: string): Token | null {
  const length = quoted(rest);
  if (length > 0) {
    const key = rest.slice(length).trimStart().startsWith(":");
    return { text: rest.slice(0, length), kind: key ? "key" : "string" };
  }
  for (const [kind, pattern] of SIMPLE) {
    const found = pattern.exec(rest);
    if (found) return { text: found[0], kind };
  }
  return null;
}

function paint(line: string): Token[] {
  const tokens: Token[] = [];
  let rest = line;
  let plain = "";
  while (rest !== "") {
    const token = nextToken(rest);
    if (token) {
      if (plain !== "") tokens.push({ text: plain, kind: "plain" });
      plain = "";
      tokens.push(token);
      rest = rest.slice(token.text.length);
    } else {
      plain += rest.charAt(0);
      rest = rest.slice(1);
    }
  }
  if (plain !== "") tokens.push({ text: plain, kind: "plain" });
  return tokens;
}

function mark(tokens: Token[], query: string): Token[] {
  const needle = query.toLowerCase();
  return tokens.flatMap((token) => {
    const out: Token[] = [];
    const hay = token.text.toLowerCase();
    let at = 0;
    for (let found = hay.indexOf(needle); found !== -1; found = hay.indexOf(needle, at)) {
      if (found > at) out.push({ text: token.text.slice(at, found), kind: token.kind });
      out.push({ text: token.text.slice(found, found + needle.length), kind: "match" });
      at = found + needle.length;
    }
    return at === 0
      ? [token]
      : [
          ...out,
          ...(at < token.text.length ? [{ text: token.text.slice(at), kind: token.kind }] : []),
        ];
  });
}

export const MAX_LINES = 2000;

export interface Highlighted {
  lines: Token[][];
  /** Lines left out of the page (the whole text is still there to copy and download). */
  hiddenLines: number;
  matches: number;
}

/** The raw output as lines of coloured stretches, with what was searched for marked. Only the
 * first `MAX_LINES` lines are made, so a very long output cannot freeze the page. */
export function highlight(output: string, query: string): Highlighted {
  const all = output.split("\n");
  const needle = query.trim();
  const lines = all.slice(0, MAX_LINES).map((line) => {
    const painted = paint(line);
    return needle === "" ? painted : mark(painted, needle);
  });
  const matches = needle === "" ? 0 : output.toLowerCase().split(needle.toLowerCase()).length - 1;
  return { lines, hiddenLines: Math.max(0, all.length - MAX_LINES), matches };
}

/** A file name for a download of one result's raw output. */
export function rawFileName(result: Pick<PentestResultFull, "title" | "tool_id">): string {
  const slug = result.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 50);
  return `${result.tool_id ?? "result"}-${slug === "" ? "output" : slug}.txt`;
}

/** The kinds of tool output that can be imported, with how the tool should have been run. */
export const IMPORT_PARSERS: readonly { value: string; title: string; subtitle: string }[] = [
  { value: "nmap_xml", title: "Nmap", subtitle: "XML, from nmap -oX" },
  { value: "nuclei_jsonl", title: "Nuclei", subtitle: "JSON Lines, from nuclei -jsonl" },
  { value: "httpx_jsonl", title: "httpx", subtitle: "JSON Lines, from httpx -json" },
  { value: "ffuf_json", title: "ffuf", subtitle: "JSON, from ffuf -of json" },
  { value: "testssl_json", title: "testssl.sh", subtitle: "JSON, from --jsonfile" },
  { value: "whatweb_json", title: "WhatWeb", subtitle: "JSON, from --log-json" },
  { value: "wafw00f_json", title: "wafw00f", subtitle: "JSON, from -f json" },
  { value: "nikto_csv", title: "Nikto", subtitle: "CSV, from -Format csv" },
];

/** The query string of the results list: only what is set. */
export function listQuery(filters: {
  view: "live" | "trash";
  q: string;
  tool: string | null;
  agent: string | null;
  severity: Severity | null;
  test: string;
  offset: number;
}): string {
  const query = new URLSearchParams({ view: filters.view, limit: "50" });
  if (filters.q.trim() !== "") query.set("q", filters.q.trim());
  if (filters.tool) query.set("tool", filters.tool);
  if (filters.agent) query.set("agent", filters.agent);
  if (filters.severity) query.set("severity", filters.severity);
  if (filters.test.trim() !== "") query.set("test", filters.test.trim());
  if (filters.offset > 0) query.set("offset", String(filters.offset));
  return query.toString();
}

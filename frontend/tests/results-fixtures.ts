import type {
  Friendly,
  PentestResultFull,
  ResultList,
  ResultSummary,
  Technical,
} from "../src/api/types";

export function summaryOf(changes: Partial<ResultSummary> = {}): ResultSummary {
  return {
    id: "r-1",
    title: "Nmap scan of shop.example.com",
    source: "tool",
    status: "ok",
    tool_id: "p.nmap",
    agent_role: "recon",
    test_id: "WSTG-INFO-02",
    top_severity: "medium",
    issue_count: 2,
    ran_at: "2026-11-25T10:00:00Z",
    tags: ["web"],
    deleted: false,
    summary: ["One host is up and 2 ports are open."],
    ...changes,
  };
}

export function listOf(items: ResultSummary[] = [summaryOf()], total = items.length): ResultList {
  return { items, total, tools: ["p.nmap", "p.nuclei"], agents: ["recon"] };
}

export const friendly: Friendly = {
  headline: "One host is up with 2 open ports",
  summary: ["The tls handshake worked.", "Nothing else to say"],
  cards: [
    {
      title: "Old TLS version",
      severity: "medium",
      target: "shop.example.com:443",
      what: "The server accepts an old TLS version.",
      why: "Attackers can force it.",
      todo: "Turn it off.",
    },
    {
      title: "Plain note",
      severity: "info",
      target: null,
      what: "A thing.",
      why: "Because.",
      todo: "Nothing.",
    },
  ],
  hidden_cards: 3,
  visuals: {
    port_map: [
      {
        address: "web.test",
        state: "up",
        ports: [
          { port: 80, protocol: "tcp", state: "open", service: "http", software: "nginx 1.31" },
          { port: 22, protocol: "tcp", state: "closed", service: null, software: null },
        ],
      },
      { address: "db.test", state: "down", ports: [] },
    ],
    tls_grade: "B",
    scorecard: [
      { name: "Content-Security-Policy", passed: false },
      { name: "X-Content-Type-Options", passed: true },
    ],
  },
  terms: [{ term: "TLS", meaning: "Encryption for connections." }],
};

export const technical: Technical = {
  issues: [{ severity: "medium", title: "Old TLS version", target: "shop:443" }],
  hosts: [{ address: "web.test", state: "up", services: [{ port: 80, protocol: "tcp" }] }],
  warnings: ["Two lines were left out"],
  truncated: true,
};

export function fullOf(changes: Partial<PentestResultFull> = {}): PentestResultFull {
  return {
    ...summaryOf(),
    parser: "nmap_xml",
    command: ["nmap", "-oX", "-", "shop.example.com"],
    exit_code: 0,
    duration_ms: 1500,
    notes: "Checked by hand.\nSecond line.",
    friendly,
    technical,
    credentials: [],
    has_raw: true,
    created_by: "u-1",
    ...changes,
  };
}

export const rawOf = {
  command: ["nmap", "-oX", "-", "shop.example.com"],
  exit_code: 0,
  duration_ms: 1500,
  output: '<port protocol="tcp" portid="80"/>\n{"name": "nginx"}',
  truncated: false,
  size: 52,
};

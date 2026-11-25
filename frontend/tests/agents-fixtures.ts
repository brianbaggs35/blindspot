import type {
  AgentNode,
  AgentSettings,
  AgentStats,
  AgentsOverview,
  Budget,
  Mission,
  MissionEvent,
  MissionPreview,
  MissionStep,
  MissionTask,
  PromptInfo,
} from "../src/api/types";

export const budget: Budget = {
  steps: 300,
  steps_per_test: 12,
  tokens: 2_000_000,
  tokens_per_test: 120_000,
  cost_usd: 25,
  seconds: 21_600,
  seconds_per_test: 900,
  concurrency: 2,
  verify_from: "medium",
};

export function stats(changes: Partial<AgentStats> = {}): AgentStats {
  return {
    runs: 0,
    succeeded: 0,
    failed: 0,
    success_rate: null,
    cost_per_run_usd: null,
    last_run: null,
    active: false,
    ...changes,
  };
}

export function test(id: string, name: string, changes: Partial<AgentNode> = {}): AgentNode {
  return {
    id,
    name,
    kind: "test",
    risk_class: "active",
    tools: ["c.nmap"],
    stats: stats(),
    children: [],
    ...changes,
  };
}

export const tree: AgentNode = {
  id: "commander",
  name: "Mission Commander",
  kind: "commander",
  risk_class: null,
  tools: [],
  stats: stats({ runs: 2, succeeded: 1, failed: 1, success_rate: 0.5, cost_per_run_usd: 1.5 }),
  children: [
    {
      id: "WSTG-CONF",
      name: "Configuration",
      kind: "category",
      risk_class: null,
      tools: [],
      stats: stats({ active: true }),
      children: [
        test("WSTG-CONF-01", "Network configuration", {
          stats: stats({
            runs: 3,
            succeeded: 2,
            failed: 1,
            success_rate: 0.667,
            cost_per_run_usd: 0.12,
            last_run: "2026-11-24T10:00:00Z",
          }),
        }),
        test("WSTG-CONF-06", "HTTP methods", {
          risk_class: "safe",
          stats: stats({ active: true }),
        }),
      ],
    },
    {
      id: "WSTG-ATHN",
      name: "Authentication",
      kind: "category",
      risk_class: null,
      tools: [],
      stats: stats(),
      children: [
        test("WSTG-ATHN-02", "Default credentials", { risk_class: "intrusive", tools: [] }),
      ],
    },
  ],
};

export function overview(changes: Partial<AgentsOverview> = {}): AgentsOverview {
  return {
    methodology_id: "wstg",
    methodologies: [
      { id: "wstg", name: "OWASP Web Security Testing Guide" },
      { id: "house", name: "House checks" },
    ],
    commander: tree,
    runner_ready: false,
    ...changes,
  };
}

export function prompt(agent: string, active = 0): PromptInfo {
  return {
    agent,
    label: `${agent} label`,
    active,
    versions: [
      { version: 0, note: "Built in", created_at: null, created_by: null, active: active === 0 },
      {
        version: 1,
        note: "Shorter",
        created_at: "2026-11-24T10:00:00Z",
        created_by: "Ada Admin",
        active: active === 1,
      },
    ],
  };
}

export function settings(changes: Partial<AgentSettings> = {}): AgentSettings {
  return {
    budget,
    built_in_budget: budget,
    presets: [
      {
        id: "passive-recon",
        name: "Passive recon only",
        summary: "Only tests that observe.",
        max_risk: "safe",
        budget: { ...budget, steps_per_test: 6, seconds_per_test: 300 },
      },
      {
        id: "safe-full",
        name: "Safe full assessment",
        summary: "Everything but intrusive.",
        max_risk: "active",
        budget,
      },
    ],
    prompts: [prompt("test-agent"), prompt("verifier")],
    max_prompt: 20_000,
    ...changes,
  };
}

export function mission(changes: Partial<Mission> = {}): Mission {
  return {
    id: "m-1",
    pentest_id: "p-1",
    status: "running",
    budget,
    spent: { steps: 4, cost_usd: 0.5, seconds: 120, tokens: 1000 },
    plan: { runs: 2, skipped: 1, max_risk: "active" },
    prompts: { "test-agent": 0, verifier: 0 },
    stop_reason: "",
    started_at: "2026-11-25T10:00:00Z",
    finished_at: null,
    created_at: "2026-11-25T10:00:00Z",
    ...changes,
  };
}

export function task(changes: Partial<MissionTask> = {}): MissionTask {
  return {
    id: "t-1",
    parent_id: null,
    kind: "commander",
    ref: "commander",
    name: "Mission Commander",
    phase: 0,
    position: 0,
    status: "done",
    summary: "Planned 2 tests in 1 categories; 1 will not run.",
    outcome: null,
    spent: {},
    ...changes,
  };
}

export const tasks: MissionTask[] = [
  task(),
  task({
    id: "t-2",
    parent_id: "t-1",
    kind: "category",
    ref: "WSTG-CONF",
    name: "Configuration",
    status: "running",
    summary: "",
  }),
  task({
    id: "t-3",
    parent_id: "t-2",
    kind: "test",
    ref: "WSTG-CONF-01",
    name: "Network configuration",
    status: "waiting",
    summary: "Waiting for approval.",
  }),
  task({
    id: "t-4",
    parent_id: "t-2",
    kind: "test",
    ref: "WSTG-CONF-06",
    name: "HTTP methods",
    status: "skipped",
    summary: "",
  }),
];

export function step(changes: Partial<MissionStep> = {}): MissionStep {
  return {
    id: "s-1",
    task_id: "t-3",
    seq: 1,
    status: "awaiting_approval",
    tool: "c.nmap",
    request: { target: "shop.example.com", ports: [80, 443] },
    verdict: null,
    result_id: null,
    note: "",
    created_at: "2026-11-25T10:01:00Z",
    ...changes,
  };
}

export function event(changes: Partial<MissionEvent> = {}): MissionEvent {
  return {
    id: 1,
    task_id: null,
    type: "mission_started",
    data: { runs: 2, skipped: 1 },
    created_at: "2026-11-25T10:00:00Z",
    ...changes,
  };
}

export function preview(changes: Partial<MissionPreview> = {}): MissionPreview {
  return {
    summary: {
      runs: 5,
      skipped: 2,
      risk: { safe: 3, active: 2, intrusive: 0 },
      tools: ["b.headers", "c.nmap"],
      skips: [{ reason: "A person has already recorded the result.", tests: 2 }],
      categories: [{ id: "WSTG-CONF", name: "Configuration", phase: 0, runs: 5, skipped: 2 }],
    },
    budget,
    max_risk: "active",
    prompts: { "test-agent": 0, verifier: 0 },
    in_scope: ["https://shop.example.com/"],
    runner_ready: true,
    ...changes,
  };
}

import type { ToolSetting, ToolSettings } from "../src/api/types";

export const noOverrides: ToolSetting["overrides"] = {
  enabled: true,
  mode: null,
  binary_path: null,
  image: null,
  cpus: null,
  memory_mb: null,
  timeout_s: null,
  max_output_mb: null,
  rate_per_s: null,
  max_risk: null,
};

export const nmap: ToolSetting = {
  id: "c.nmap",
  name: "Nmap",
  tier: "core",
  origin: "core",
  execution: "command",
  risk: "active",
  explain: "Finds open ports and the services behind them.",
  enabled: true,
  mode: null,
  binary_path: null,
  image: null,
  default_binary: "nmap",
  default_image: null,
  limits: {
    cpus: null,
    memory_mb: null,
    timeout_s: 600,
    max_output_mb: 32,
    rate_per_s: null,
    max_risk: "active",
  },
  overrides: noOverrides,
  effective: {
    mode: "local",
    status: "ready",
    problem: "",
    fell_back: false,
    offer: null,
    path: "/usr/bin/nmap",
  },
};

export const nuclei: ToolSetting = {
  ...nmap,
  id: "p.nuclei",
  name: "Nuclei",
  tier: "extra",
  origin: "plugin",
  risk: "intrusive",
  explain: "Checks a target against known weaknesses.",
  default_binary: "nuclei",
  default_image: "ghcr.io/projectdiscovery/nuclei@sha256:" + "a".repeat(64),
  image: "ghcr.io/projectdiscovery/nuclei@sha256:" + "a".repeat(64),
  limits: { ...nmap.limits, rate_per_s: 5, max_risk: "intrusive" },
  effective: {
    mode: null,
    status: "binary_not_found",
    problem: "nuclei is not installed here.",
    fell_back: false,
    offer: "docker",
    path: null,
  },
};

export const builtin: ToolSetting = {
  ...nmap,
  id: "b.report",
  name: "Report",
  origin: "builtin",
  execution: "builtin",
  risk: "passive",
  default_binary: null,
  effective: {
    mode: "builtin",
    status: "ready",
    problem: "",
    fell_back: false,
    offer: null,
    path: null,
  },
};

export const custom: ToolSetting = {
  ...nmap,
  id: "x.echo",
  name: "Echo",
  origin: "custom",
  risk: "destructive",
  default_binary: null,
  overrides: { ...noOverrides, enabled: false, binary_path: "/bin/echo" },
  effective: {
    mode: "docker",
    status: "docker_unreachable",
    problem: "Docker is not connected.",
    fell_back: true,
    offer: null,
    path: null,
  },
  limits: { ...nmap.limits, memory_mb: 512, rate_per_s: null, max_risk: "destructive" },
};

export function toolSettings(extra: Partial<ToolSettings> = {}): ToolSettings {
  return {
    run_mode: "auto",
    docker: { reachable: false, note: "No Docker socket is mounted." },
    tools: [nmap, nuclei, builtin, custom],
    ...extra,
  };
}

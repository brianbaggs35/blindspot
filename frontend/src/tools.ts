import type {
  RunMode,
  ToolOverrides,
  ToolResolution,
  ToolRisk,
  ToolSetting,
  ToolStatus,
  ToolWhere,
} from "./api/types";

export const RUN_MODES: readonly { value: RunMode; title: string; hint: string }[] = [
  {
    value: "auto",
    title: "Auto",
    hint: "Local for tools that come with Blindspot, Docker for the rest.",
  },
  {
    value: "prefer_local",
    title: "Prefer Local",
    hint: "Local, and Docker when Local cannot run.",
  },
  {
    value: "prefer_docker",
    title: "Prefer Docker",
    hint: "Docker, and Local when Docker cannot run.",
  },
  { value: "docker_only", title: "Docker only", hint: "Docker, and nothing else." },
];

export const WHERE_LABELS: Record<ToolWhere, string> = {
  local: "Local",
  docker: "Docker",
  builtin: "Built in",
};

export const STATUS_LABELS: Record<ToolStatus, string> = {
  ready: "Ready",
  disabled: "Switched off",
  binary_not_found: "Program not found",
  docker_unreachable: "Docker not reachable",
  image_missing: "No image",
};

export const STATUS_COLORS: Record<ToolStatus, string> = {
  ready: "success",
  disabled: "default",
  binary_not_found: "error",
  docker_unreachable: "error",
  image_missing: "warning",
};

export const RISKS: readonly { value: ToolRisk; title: string }[] = [
  { value: "passive", title: "Passive" },
  { value: "active", title: "Active" },
  { value: "intrusive", title: "Intrusive" },
  { value: "destructive", title: "Destructive" },
];
export const RISK_COLORS: Record<ToolRisk, string> = {
  passive: "success",
  active: "info",
  intrusive: "warning",
  destructive: "error",
};

export const MODE_CHOICES = [
  { value: null, title: "Follow the default" },
  { value: "local", title: "Local" },
  { value: "docker", title: "Docker" },
] as const;

/** The risk classes a tool may be held to: its own, or lower. */
export function risksUpTo(risk: ToolRisk): { value: ToolRisk; title: string }[] {
  const last = RISKS.findIndex((one) => one.value === risk);
  return RISKS.slice(0, last + 1).map((one) => ({ ...one }));
}

/** Where a tool runs, in words, or what stops it. */
export function whereOf(effective: ToolResolution): string {
  if (effective.mode === null) return STATUS_LABELS[effective.status];
  return `${WHERE_LABELS[effective.mode]}${effective.fell_back ? " (the other way, as the default allows)" : ""}`;
}

/** Whether an administrator has set anything for the tool, so that Reset has something to undo. */
export function customised(tool: ToolSetting): boolean {
  const { enabled, ...rest } = tool.overrides;
  return !enabled || Object.values(rest).some((value) => value !== null);
}

/** The form of a tool's settings: numbers are text while they are typed. */
export interface SettingDraft {
  enabled: boolean;
  mode: "local" | "docker" | null;
  binary_path: string;
  image: string;
  cpus: string;
  memory_mb: string;
  timeout_s: string;
  max_output_mb: string;
  rate_per_s: string;
  max_risk: ToolRisk | null;
}

const text = (value: string | number | null): string => (value === null ? "" : String(value));

export function draftOf(tool: ToolSetting): SettingDraft {
  const set: ToolOverrides = tool.overrides;
  return {
    enabled: set.enabled,
    mode: set.mode,
    binary_path: text(set.binary_path),
    image: text(set.image),
    cpus: text(set.cpus),
    memory_mb: text(set.memory_mb),
    timeout_s: text(set.timeout_s),
    max_output_mb: text(set.max_output_mb),
    rate_per_s: text(set.rate_per_s),
    max_risk: set.max_risk,
  };
}

const orNull = (value: string): string | null => (value.trim() === "" ? null : value.trim());
const numberOrNull = (value: string): number | null => (value.trim() === "" ? null : Number(value));

/** What to send: empty fields are null, and the fields of the way not chosen are left out. */
export function bodyOf(draft: SettingDraft): ToolOverrides {
  return {
    enabled: draft.enabled,
    mode: draft.mode,
    binary_path: draft.mode === "docker" ? null : orNull(draft.binary_path),
    image: draft.mode === "local" ? null : orNull(draft.image),
    cpus: orNull(draft.cpus),
    memory_mb: numberOrNull(draft.memory_mb),
    timeout_s: numberOrNull(draft.timeout_s),
    max_output_mb: numberOrNull(draft.max_output_mb),
    rate_per_s: numberOrNull(draft.rate_per_s),
    max_risk: draft.max_risk,
  };
}

import type { Price, PriceSource, Provider, ProviderKind } from "./api/types";

const dollars = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const prices = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
});
const counts = new Intl.NumberFormat("en-US");

/** An amount of money from the API ("12.5" becomes "$12.50"). */
export function usd(value: string): string {
  return dollars.format(Number(value));
}

/** A price per million tokens, with the pennies it needs and no more. */
export function perMillion(value: string | null): string {
  return value === null ? "unknown" : prices.format(Number(value));
}

/** "1,000,000 tokens", or a dash when it is not known. */
export function tokens(value: number | null): string {
  return value === null ? "—" : `${counts.format(value)} tokens`;
}

export const PRICE_SOURCES: Record<PriceSource, { label: string; hint: string }> = {
  override: { label: "your price", hint: "A price an administrator set on this model." },
  catalog: { label: "catalog price", hint: "From the built-in price list." },
  free: { label: "free", hint: "Runs on your own hardware, so there is no charge." },
  unknown: {
    label: "price unknown",
    hint: "Calls are counted but have no cost until a price is set.",
  },
};

/** The line under a model's name: the price it will be charged at, in short. */
export function priceSummary(price: Price): string {
  if (price.input === null && price.output === null) return "price unknown";
  return `in ${perMillion(price.input)} · out ${perMillion(price.output)} per million tokens`;
}

export interface Budget {
  /** 0 to 100, for the bar. */
  percent: number;
  color: "primary" | "warning" | "error";
  text: string;
}

function colorFor(percent: number): Budget["color"] {
  if (percent >= 100) return "error";
  return percent >= 75 ? "warning" : "primary";
}

/** How much of the month's budget is used, or just what was spent when there is no budget. */
export function budgetOf(provider: Provider): Budget {
  const spent = Number(provider.spent_this_month_usd);
  const spentText = usd(provider.spent_this_month_usd);
  if (provider.monthly_budget_usd === null) {
    return { percent: 0, color: "primary", text: `${spentText} this month, no budget` };
  }
  const budget = Number(provider.monthly_budget_usd);
  const percent = budget === 0 ? 100 : Math.min(100, (spent / budget) * 100);
  const stop = provider.hard_stop ? ", calls stop at the budget" : "";
  return {
    percent,
    color: colorFor(percent),
    text: `${spentText} of ${usd(provider.monthly_budget_usd)} this month${stop}`,
  };
}

/** What to tell someone setting up each kind. */
export const KIND_NOTES: Record<ProviderKind, string> = {
  anthropic:
    "Create a key in the Anthropic Console. Nothing is sent to Anthropic until a pentest or chat uses it.",
  openai:
    "Create a key on the OpenAI platform. Nothing is sent to OpenAI until a pentest or chat uses it.",
  "ollama-local":
    "Ollama running on your own computer or network. From inside Blindspot's container, your computer is host.docker.internal. Ollama only listens on the local machine by default, so start it with OLLAMA_HOST=0.0.0.0, and on Linux run the container with --add-host=host.docker.internal:host-gateway. No key is needed.",
  "ollama-cloud":
    "Ollama's hosted service. Create a key at ollama.com/settings/keys. Cloud models do not enforce JSON schemas, so Blindspot checks their answers itself.",
};

export const CAPABILITIES = [
  { title: "Tools (needed to run agents)", value: "tools" },
  { title: "Thinking", value: "thinking" },
  { title: "Vision", value: "vision" },
] as const;

/** The empty form text for a price field is "use the catalog's"; anything else is sent as typed. */
export function priceOrNull(text: string): string | null {
  const trimmed = text.trim();
  return trimmed === "" ? null : trimmed;
}

/** A whole number from a form field, or null when it is empty or not a positive whole number. */
export function wholeOrNull(text: string): number | null {
  const value = Number(text);
  return text.trim() !== "" && Number.isInteger(value) && value > 0 ? value : null;
}

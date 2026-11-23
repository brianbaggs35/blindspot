import { describe, expect, it } from "vitest";
import type { Provider } from "../src/api/types";
import {
  budgetOf,
  perMillion,
  priceOrNull,
  priceSummary,
  tokens,
  usd,
  wholeOrNull,
} from "../src/providers";

const provider: Provider = {
  id: "p-1",
  kind: "openai",
  name: "OpenAI",
  base_url: "https://api.openai.com/v1",
  enabled: true,
  has_key: true,
  key_last4: "abcd",
  monthly_budget_usd: "100.0000",
  hard_stop: false,
  spent_this_month_usd: "0",
  model_count: 0,
  created_at: "2026-11-01T10:00:00Z",
};

describe("money and sizes", () => {
  it("shows amounts as dollars and cents", () => {
    expect(usd("12.5")).toBe("$12.50");
    expect(usd("1234.567")).toBe("$1,234.57");
  });

  it("shows a price with the pennies it needs and no more", () => {
    expect(perMillion("4")).toBe("$4.00");
    expect(perMillion("0.125")).toBe("$0.125");
    expect(perMillion("0.000001")).toBe("$0.000001");
    expect(perMillion(null)).toBe("unknown");
  });

  it("shows token counts, or a dash", () => {
    expect(tokens(1_000_000)).toBe("1,000,000 tokens");
    expect(tokens(null)).toBe("—");
  });

  it("summarises what a model costs", () => {
    const none = {
      input: null,
      output: null,
      cache_read: null,
      cache_write: null,
      cache_write_long: null,
    };
    expect(priceSummary(none)).toBe("price unknown");
    expect(priceSummary({ ...none, input: "4", output: "20" })).toBe(
      "in $4.00 · out $20.00 per million tokens",
    );
    expect(priceSummary({ ...none, input: "4" })).toBe("in $4.00 · out unknown per million tokens");
  });
});

describe("the budget", () => {
  it("is just the spend when there is no budget", () => {
    expect(budgetOf({ ...provider, monthly_budget_usd: null, spent_this_month_usd: "3" })).toEqual({
      percent: 0,
      color: "primary",
      text: "$3.00 this month, no budget",
    });
  });

  it("goes from calm to warning to error as it is used", () => {
    const at = (spent: string) => budgetOf({ ...provider, spent_this_month_usd: spent });
    expect(at("10")).toMatchObject({ percent: 10, color: "primary" });
    expect(at("75")).toMatchObject({ percent: 75, color: "warning" });
    expect(at("100")).toMatchObject({ percent: 100, color: "error" });
    expect(at("250")).toMatchObject({ percent: 100, color: "error" });
    expect(at("10").text).toBe("$10.00 of $100.00 this month");
  });

  it("says when calls stop at the budget, and treats a zero budget as used up", () => {
    expect(budgetOf({ ...provider, hard_stop: true }).text).toContain("calls stop at the budget");
    expect(budgetOf({ ...provider, monthly_budget_usd: "0" })).toMatchObject({
      percent: 100,
      color: "error",
    });
  });
});

describe("form fields", () => {
  it("sends an empty price as null and anything else as typed", () => {
    expect(priceOrNull("  ")).toBeNull();
    expect(priceOrNull(" 1.5 ")).toBe("1.5");
  });

  it("reads whole positive numbers only", () => {
    expect(wholeOrNull("128000")).toBe(128000);
    expect(wholeOrNull("")).toBeNull();
    expect(wholeOrNull("0")).toBeNull();
    expect(wholeOrNull("1.5")).toBeNull();
    expect(wholeOrNull("many")).toBeNull();
  });
});

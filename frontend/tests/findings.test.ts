import { describe, expect, it } from "vitest";
import {
  buildVector,
  countOf,
  describeEvent,
  draftOf,
  emptyDraft,
  label,
  listQuery,
  parseVector,
  scoreOf,
  words,
  type Filters,
} from "../src/findings";
import { eventOf, findingOf } from "./findings-fixtures";

const V31 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H";
const V4 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N";

const filters = (changes: Partial<Filters> = {}): Filters => ({
  view: "live",
  q: "",
  status: [],
  severity: [],
  test: "",
  target: "",
  sort: "severity",
  order: "desc",
  group: null,
  offset: 0,
  ...changes,
});

describe("finding helpers", () => {
  it("says a number as F-12 and reads a count that is not there as none", () => {
    expect(label(12)).toBe("F-12");
    expect(countOf({ new: 3 }, "new")).toBe(3);
    expect(countOf({ new: 3 }, "fixed")).toBe(0);
  });

  it("takes the CVSS 4.0 score before the 3.1 one", () => {
    expect(scoreOf({ cvss4_score: "9.3", cvss31_score: "9.8" })).toBe("9.3");
    expect(scoreOf({ cvss4_score: null, cvss31_score: "9.8" })).toBe("9.8");
    expect(scoreOf({ cvss4_score: null, cvss31_score: null })).toBe("");
  });

  it("splits words by commas, spaces and lines, once each", () => {
    expect(words("CWE-79, CWE-89\nCWE-79  ")).toEqual(["CWE-79", "CWE-89"]);
    expect(words("")).toEqual([]);
  });

  it("makes a draft from a finding without sharing its lists", () => {
    const finding = findingOf();
    const draft = draftOf(finding);
    expect(draft.title).toBe(finding.title);
    expect(draft.test_ids).toEqual(finding.test_ids);
    expect(draft.test_ids).not.toBe(finding.test_ids);
    expect(emptyDraft().title).toBe("");
    expect(emptyDraft().severity).toBeNull();
  });
});

describe("listQuery", () => {
  it("sends only what is set", () => {
    expect(listQuery(filters())).toBe("view=live&sort=severity&order=desc&limit=50");
  });

  it("sends every filter, the grouping and the offset", () => {
    const query = new URLSearchParams(
      listQuery(
        filters({
          view: "trash",
          q: " hsts ",
          status: ["new", "fixed"],
          severity: ["high"],
          test: " WSTG-CONF-07 ",
          target: " shop ",
          group: "target",
          offset: 50,
        }),
        25,
      ),
    );
    expect(query.get("view")).toBe("trash");
    expect(query.get("limit")).toBe("25");
    expect(query.get("q")).toBe("hsts");
    expect(query.getAll("status")).toEqual(["new", "fixed"]);
    expect(query.getAll("severity")).toEqual(["high"]);
    expect(query.get("test")).toBe("WSTG-CONF-07");
    expect(query.get("target")).toBe("shop");
    expect(query.get("group_by")).toBe("target");
    expect(query.get("offset")).toBe("50");
  });
});

describe("describeEvent", () => {
  const say = (kind: string, data: Record<string, unknown> = {}) =>
    describeEvent(eventOf({ kind, data }));

  it("says each kind of event in words", () => {
    expect(say("created")).toBe("Created.");
    expect(say("updated", { fields: ["title", "severity"] })).toBe("Changed title, severity.");
    expect(say("updated")).toBe("Changed it.");
    expect(say("status", { before: "new", after: "fixed" })).toBe(
      "Status changed from New to Fixed.",
    );
    expect(say("status", { before: "odd", after: 3 })).toBe("Status changed from odd to .");
    expect(say("verified", { by: "manual", outcome: "confirmed" })).toBe("A person confirmed it.");
    expect(say("verified", { by: "agent", outcome: "unconfirmed" })).toBe(
      "The verifier could not reproduce it.",
    );
    expect(say("retest_requested")).toBe("A retest was asked for.");
    expect(say("comment", { body: "Looks right" })).toBe("Looks right");
    expect(say("evidence_added", { title: "Shot" })).toBe("Added evidence: Shot.");
    expect(say("evidence_removed", { title: "Shot" })).toBe("Removed evidence: Shot.");
    expect(say("merged_into", { number: 4 })).toBe("Merged into F-4.");
    expect(say("merged_from", { number: 5 })).toBe("F-5 was merged into this one.");
    expect(say("seen_again")).toBe("An agent found it again.");
    expect(say("deleted")).toBe("Moved to the trash.");
    expect(say("restored")).toBe("Restored from the trash.");
    expect(say("something_new")).toBe("something new");
  });
});

describe("CVSS vectors", () => {
  it("reads the metrics of a vector of the right version only", () => {
    expect(parseVector(V31, "3.1").get("AV")).toBe("N");
    expect(parseVector(V31, "4.0").size).toBe(0);
    expect(parseVector(null, "3.1").size).toBe(0);
    expect(parseVector("CVSS:3.1/AV:N/broken//X", "3.1").size).toBe(1);
  });

  it("builds a vector only when every metric has a value", () => {
    const chosen = parseVector(V31, "3.1");
    expect(buildVector(chosen, "3.1")).toBe(V31);
    const partial = new Map(chosen);
    partial.delete("A");
    expect(buildVector(partial, "3.1")).toBeNull();
    expect(buildVector(parseVector(V4, "4.0"), "4.0")).toBe(V4);
  });

  it("keeps the metrics of the old vector that the calculator has no field for", () => {
    const before = `${V4}/E:A`;
    expect(buildVector(parseVector(before, "4.0"), "4.0", before)).toBe(`${V4}/E:A`);
  });
});

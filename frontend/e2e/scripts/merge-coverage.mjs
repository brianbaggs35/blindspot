// Merges the browser coverage of every shard into one report and checks it.
// The markdown summary is written to <out>/coverage-summary.md, which the workflow adds to the job summary.
// Usage: node e2e/scripts/merge-coverage.mjs <shard-coverage-dir>...
// Each directory is a shard's e2e-results/coverage, with the "raw" report inside.
// Fails below E2E_COVERAGE_MIN (default 80%), and warns below E2E_COVERAGE_TARGET (default 90%).
import { join } from "node:path";
import { CoverageReport } from "monocart-coverage-reports";
import filters from "../coverage-filters.json" with { type: "json" };

const minimum = Number(process.env["E2E_COVERAGE_MIN"] ?? "80");
const target = Number(process.env["E2E_COVERAGE_TARGET"] ?? "90");
const outputDir = process.env["E2E_COVERAGE_OUT"] ?? "e2e-results/coverage-merged";
const shards = process.argv.slice(2);

if (shards.length === 0) {
  console.error("Give the shards' coverage directories.");
  process.exit(2);
}

const report = new CoverageReport({
  ...filters,
  name: "Blindspot web app, end to end (all shards)",
  inputDir: shards.map((dir) => join(dir, "raw")),
  outputDir,
  reports: ["v8", "lcovonly", "markdown-summary", "console-summary"],
});
const results = await report.generate();
const lines = results?.summary?.lines?.pct;

if (typeof lines !== "number") {
  console.error("No coverage was collected: nothing in src/ was loaded by the tests.");
  process.exit(1);
}

const summary = `End-to-end coverage of the web app: **${lines.toFixed(1)}%** of lines (minimum ${minimum}%, target ${target}%).\n`;
console.log(summary);

if (lines < minimum) {
  console.error(
    `::error::End-to-end coverage ${lines.toFixed(1)}% is below the ${minimum}% minimum.`,
  );
  process.exit(1);
}
if (lines < target) {
  console.log(
    `::warning::End-to-end coverage ${lines.toFixed(1)}% is below the ${target}% target.`,
  );
}

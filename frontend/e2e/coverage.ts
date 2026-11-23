import { CoverageReport, type CoverageReportOptions } from "monocart-coverage-reports";
import filters from "./coverage-filters.json" with { type: "json" };

// Browser coverage of the web app. It is only collected when E2E_COVERAGE=1, against a build
// with the source maps inside the files (npm run build:e2e), so the numbers are for src/*.
// The real image ships without source maps, so container mode does not collect it.
export const collectCoverage = process.env["E2E_COVERAGE"] === "1";

export const coverageDir = process.env["E2E_COVERAGE_DIR"] ?? "e2e-results/coverage";

export const coverageOptions: CoverageReportOptions = {
  name: "Blindspot web app, end to end",
  outputDir: coverageDir,
  // "raw" is what the merge across shards reads; the others are for people and for Sonar.
  reports: ["raw", "lcovonly", "console-summary"],
  // Only our own bundles, and within them only our own source (not Vue, Vuetify or Vite).
  // The same file is read by the merge script, so the shards and the merge agree.
  ...filters,
};

export function newCoverageReport(options: Partial<CoverageReportOptions> = {}): CoverageReport {
  return new CoverageReport({ ...coverageOptions, ...options });
}

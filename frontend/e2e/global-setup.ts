import { collectCoverage, newCoverageReport } from "./coverage";

// Start each run with an empty coverage cache.
export default function globalSetup(): void {
  if (collectCoverage) newCoverageReport().cleanCache();
}

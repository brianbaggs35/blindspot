import { collectCoverage, newCoverageReport } from "./coverage";

// All workers added their coverage to the same cache; write the report for this shard.
export default async function globalTeardown(): Promise<void> {
  if (collectCoverage) await newCoverageReport().generate();
}

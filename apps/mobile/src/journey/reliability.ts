import type { AnalysisReliability } from "./apiTypes";

export type ReliabilityValue = string | AnalysisReliability;

export function formatReliability(value: ReliabilityValue): string {
  if (typeof value === "string") {
    return value;
  }
  if (value.reason_codes.length === 0) {
    return value.level;
  }
  const reasons = value.reason_codes.map((reason) => reason.replaceAll("_", " ")).join(", ");
  return `${value.level} (${reasons})`;
}

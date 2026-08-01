import { describe, expect, test } from "@jest/globals";

import { formatReliability } from "./reliability";

describe("formatReliability", () => {
  test("preserves legacy mock string values", () => {
    expect(formatReliability("high")).toBe("high");
  });

  test("renders the real backend object without React object children", () => {
    expect(formatReliability({ level: "medium", reason_codes: [] })).toBe("medium");
    expect(
      formatReliability({
        level: "low",
        reason_codes: ["low_coverage", "conflicting_records"],
      }),
    ).toBe("low (low coverage, conflicting records)");
  });
});

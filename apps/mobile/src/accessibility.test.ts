import { describe, expect, test } from "@jest/globals";

import { contrastRatio, MIN_TOUCH_TARGET } from "./accessibility";
import { MOBILE_STRINGS, stringsFor, SUPPORTED_LOCALES } from "./i18n/resources";

describe("mobile accessibility baseline", () => {
  test("uses a minimum 44px touch target for new interactive controls", () => {
    expect(MIN_TOUCH_TARGET).toBeGreaterThanOrEqual(44);
  });

  test("core foreground/background pairs meet normal-text contrast", () => {
    expect(contrastRatio("#173B3B", "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio("#304C4C", "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio("#285C5C", "#FFFFFF")).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio("#FFFFFF", "#285C5C")).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21);
  });

  test("ships safety text in English, Chinese and Japanese", () => {
    expect(SUPPORTED_LOCALES).toEqual(["en", "zh", "ja"]);
    for (const locale of SUPPORTED_LOCALES) {
      const strings = stringsFor(locale);
      expect(strings).toBe(MOBILE_STRINGS[locale]);
      expect(strings.safety.title.length).toBeGreaterThan(5);
      expect(strings.safety.body.length).toBeGreaterThan(20);
      expect(strings.safety.urgent.length).toBeGreaterThan(20);
      expect(strings.common.retry.length).toBeGreaterThan(0);
    }
  });

  test("rejects malformed colours instead of silently auditing them", () => {
    expect(() => contrastRatio("red", "#FFFFFF")).toThrow("six-digit hex colour");
  });
});

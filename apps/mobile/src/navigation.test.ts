import { describe, expect, test } from "@jest/globals";

import { CORE_NAVIGATION_TABS, NAVIGATION_TABS } from "./navigation";

describe("mobile navigation contract", () => {
  test("preserves the four frozen CarePath Core destinations in order", () => {
    expect(CORE_NAVIGATION_TABS).toEqual(["Today", "Coach", "Health Data", "Plan & History"]);
  });

  test("adds Tokyo as a separate product entry before the frozen Core destinations", () => {
    expect(NAVIGATION_TABS).toEqual(["Tokyo", ...CORE_NAVIGATION_TABS]);
  });
});

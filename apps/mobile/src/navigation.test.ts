import { describe, expect, test } from "@jest/globals";

import { NAVIGATION_TABS } from "./navigation";

describe("mobile navigation contract", () => {
  test("contains the four frozen CarePath destinations in order", () => {
    expect(NAVIGATION_TABS).toEqual(["Today", "Coach", "Health Data", "Plan & History"]);
  });
});

import { describe, expect, test } from "@jest/globals";

import { isHealthResponse } from "./health";

describe("isHealthResponse", () => {
  test("accepts the backend mock-provider health contract", () => {
    expect(isHealthResponse({ status: "ok", provider: "mock" })).toBe(true);
  });

  test.each([null, {}, { status: "down", provider: "mock" }, { status: "ok", provider: 42 }])(
    "rejects invalid payload %p",
    (payload) => {
      expect(isHealthResponse(payload)).toBe(false);
    },
  );
});

import { afterEach, describe, expect, test } from "@jest/globals";

import {
  resetRuntimeAuthState,
  runtimeAccountUserId,
  runtimeApiHeaders,
  runtimePrivateMode,
  setRuntimeAccessToken,
  setRuntimeAccountUserId,
  setRuntimePrivateSession,
} from "./runtimeState";

afterEach(() => {
  resetRuntimeAuthState();
});

describe("shared authentication runtime state", () => {
  test("starts anonymous with standard storage headers", () => {
    resetRuntimeAuthState();
    expect(runtimeApiHeaders()).toEqual({});
    expect(runtimeAccountUserId()).toBeNull();
    expect(runtimePrivateMode()).toBe(false);
  });

  test("combines account and private-session request headers", () => {
    setRuntimeAccessToken("access-token");
    setRuntimeAccountUserId("account-user-id");
    setRuntimePrivateSession("private-session-id");

    expect(runtimeApiHeaders()).toEqual({
      Authorization: "Bearer access-token",
      "X-CarePath-Private-Session": "private-session-id",
    });
    expect(runtimeAccountUserId()).toBe("account-user-id");
    expect(runtimePrivateMode()).toBe(true);

    setRuntimeAccessToken(null);
    setRuntimePrivateSession(null);
    setRuntimeAccountUserId(null);
    expect(runtimeApiHeaders()).toEqual({});
    expect(runtimeAccountUserId()).toBeNull();
    expect(runtimePrivateMode()).toBe(false);
  });
});

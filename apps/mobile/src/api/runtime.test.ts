import { afterEach, describe, expect, test } from "@jest/globals";

import {
  createRuntimeApiClient,
  LOCAL_API_URL,
  resolveApiBaseUrl,
  SAME_ORIGIN_API_URL,
} from "./runtime";

const originalFetch = globalThis.fetch;
const originalConfiguredUrl = process.env.EXPO_PUBLIC_CAREPATH_API_URL;

function inputUrl(input: string | URL | Request): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalConfiguredUrl === undefined) {
    delete process.env.EXPO_PUBLIC_CAREPATH_API_URL;
  } else {
    process.env.EXPO_PUBLIC_CAREPATH_API_URL = originalConfiguredUrl;
  }
});

describe("Expo runtime API transport", () => {
  test("resolves configured, same-origin and local API base URLs", () => {
    expect(resolveApiBaseUrl("  https://carepath.example  ")).toBe("https://carepath.example");
    expect(resolveApiBaseUrl(SAME_ORIGIN_API_URL)).toBe("");
    expect(resolveApiBaseUrl("   ")).toBe(LOCAL_API_URL);
    expect(resolveApiBaseUrl(undefined)).toBe(LOCAL_API_URL);
  });

  test("uses the explicit base URL with the platform fetch implementation", async () => {
    let requestedUrl = "";
    const fakeFetch: typeof fetch = (input) => {
      requestedUrl = inputUrl(input);
      return Promise.resolve(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    };
    globalThis.fetch = fakeFetch;

    const result = await createRuntimeApiClient("https://explicit.test").get<{ status: string }>(
      "/health",
    );

    expect(requestedUrl).toBe("https://explicit.test/health");
    expect(result).toEqual({ ok: true, data: { status: "ok" } });
  });

  test("uses EXPO_PUBLIC_CAREPATH_API_URL when no explicit base URL is provided", async () => {
    process.env.EXPO_PUBLIC_CAREPATH_API_URL = "https://env.test";
    let requestedUrl = "";
    const fakeFetch: typeof fetch = (input) => {
      requestedUrl = inputUrl(input);
      return Promise.resolve(
        new Response(JSON.stringify({ provider: "mock" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    };
    globalThis.fetch = fakeFetch;

    await createRuntimeApiClient().get("/health");

    expect(requestedUrl).toBe("https://env.test/health");
  });

  test("uses relative requests for the integrated reviewer deployment", async () => {
    process.env.EXPO_PUBLIC_CAREPATH_API_URL = SAME_ORIGIN_API_URL;
    let requestedUrl = "";
    const fakeFetch: typeof fetch = (input) => {
      requestedUrl = inputUrl(input);
      return Promise.resolve(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    };
    globalThis.fetch = fakeFetch;

    await createRuntimeApiClient().get("/health/ready");

    expect(requestedUrl).toBe("/health/ready");
  });
});

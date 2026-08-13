import { describe, expect, test } from "@jest/globals";

import { CarePathApiClient, type ApiFetcher } from "../api/client";
import { searchTokyoAgent, type RetryWait } from "./api";

const request = {
  query: "Find a cooling shelter",
  interface_language: "en" as const,
  location: { mode: "municipality" as const, municipality: "江東区" },
  radius_km: 10,
  limit: 5,
};

const validUnsupportedResponse = {
  status: "unsupported",
  intent: {},
  intent_model_status: "not_needed",
  explanation_model_status: "not_needed",
  explanations: [],
  clarification: { reason: "unsupported", message: "Unsupported request." },
};

describe("Tokyo transient network resilience", () => {
  test("retries network failures and returns the first recovered response", async () => {
    let attempts = 0;
    const fetcher: ApiFetcher = () => {
      attempts += 1;
      if (attempts < 3) {
        return Promise.reject(new TypeError("temporary network failure"));
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(validUnsupportedResponse),
      });
    };
    const waits: number[] = [];
    const retryWait: RetryWait = (delayMs) => {
      waits.push(delayMs);
      return Promise.resolve();
    };
    const client = new CarePathApiClient("https://example.test", fetcher);

    const result = await searchTokyoAgent(client, request, [2_000, 5_000, 10_000], retryWait);

    expect(result.ok).toBe(true);
    expect(attempts).toBe(3);
    expect(waits).toEqual([2_000, 5_000]);
  });

  test("does not retry controlled HTTP failures", async () => {
    let attempts = 0;
    const fetcher: ApiFetcher = () => {
      attempts += 1;
      return Promise.resolve({
        ok: false,
        status: 503,
        json: () =>
          Promise.resolve({
            error: {
              code: "service_unavailable",
              message: "Unavailable",
              request_id: "req-1",
            },
          }),
      });
    };
    const retryWait: RetryWait = () => Promise.reject(new Error("retry should not run"));
    const client = new CarePathApiClient("https://example.test", fetcher);

    const result = await searchTokyoAgent(client, request, [1], retryWait);

    expect(result.ok).toBe(false);
    expect(attempts).toBe(1);
  });
});

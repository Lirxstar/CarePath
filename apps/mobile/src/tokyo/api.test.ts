import { describe, expect, test } from "@jest/globals";

import { CarePathApiClient, type ApiFetcher } from "../api/client";
import {
  explanationFor,
  isTokyoAgentApiResponse,
  responseHasModelFallback,
  responseHasPartialResourceData,
  searchTokyoAgent,
} from "./api";

const provenance = {
  source_id: "tokyo-official",
  source_record_id: "record-1",
  source_url: "https://example.metro.tokyo.lg.jp/source.csv",
  catalog_url: "https://catalog.data.metro.tokyo.lg.jp/dataset/example",
  publisher: "Tokyo public authority",
  licence: "CC BY",
  source_as_of: "2026-08-01",
  retrieved_at: "2026-08-12",
  content_sha256: "0".repeat(64),
};

function successfulResponse() {
  return {
    status: "ok",
    intent: {
      resolution: "resolved",
      intent: "find_cooling_shelter",
      category: "cooling_shelter",
      interface_language: "en",
      location_mode: "manual",
      requested_languages: [],
      language_constraint: "none",
      require_known_opening_hours: false,
      require_access_notes: false,
      require_phone: false,
      require_website: false,
      clarification_reason: null,
    },
    intent_source: "deterministic",
    intent_model_status: "not_needed",
    explanation_model_status: "unavailable",
    search: {
      status: "ok",
      location: { mode: "municipality", municipality: "江東区" },
      radius_km: null,
      applied_filters: {
        category: "cooling_shelter",
        required_languages: [],
        require_known_opening_hours: false,
        require_access_notes: false,
        require_phone: false,
        require_website: false,
        allowed_freshness: [],
      },
      count: 1,
      results: [
        {
          rank: 1,
          distance_km: null,
          resource: {
            resource_id: "cooling-1",
            name: "Cooling Place",
            category: "cooling_shelter",
            address: "東京都江東区1-1",
            municipality: "江東区",
            latitude: null,
            longitude: null,
            languages: [],
            opening_hours: null,
            access_notes: null,
            phone: null,
            website: null,
            freshness: "current",
            provenance: [provenance],
            data_quality_flags: ["language_support_unknown"],
          },
        },
      ],
      no_match: null,
    },
    explanations: [],
    clarification: null,
  };
}

describe("CP-206 Tokyo API boundary", () => {
  test("accepts a grounded resource response and exposes fallback/partial state", () => {
    const response = successfulResponse();
    expect(isTokyoAgentApiResponse(response)).toBe(true);
    if (!isTokyoAgentApiResponse(response)) {
      throw new Error("fixture should validate");
    }
    expect(responseHasModelFallback(response)).toBe(true);
    expect(responseHasPartialResourceData(response)).toBe(true);
    expect(explanationFor(response, "cooling-1")).toBeNull();
  });

  test("accepts the CP-205 safety boundary", () => {
    const response = {
      status: "safety_boundary",
      safety: {
        disposition: "emergency_escalation",
        bypass_resource_navigation: true,
        message: "Call 119 now.",
        matched_rule_ids: ["URG-001"],
        policy_flags: [],
        references: [
          {
            source_id: "tokyo-health-ambulance-119",
            title: "How to call an ambulance",
            publisher: "東京都保健医療局",
            canonical_url: "https://www.hokeniryo.metro.tokyo.lg.jp/example",
            retrieved_at: "2026-08-12",
            source_as_of: null,
          },
        ],
        privacy: {
          precise_location_use: "current_request_only",
          precise_location_persisted: false,
          free_text_persisted_by_tokyo_route: false,
          longitudinal_health_history_required: false,
        },
      },
    };

    expect(isTokyoAgentApiResponse(response)).toBe(true);
  });

  test("rejects malformed resource payloads instead of rendering invented facts", async () => {
    const fetcher: ApiFetcher = () =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "ok", results: [{ name: "invented" }] }),
      });
    const client = new CarePathApiClient("https://example.test", fetcher);

    const result = await searchTokyoAgent(client, {
      query: "Find a cooling shelter",
      interface_language: "en",
      location: { mode: "municipality", municipality: "江東区" },
      radius_km: 10,
      limit: 5,
    });

    expect(result).toEqual({
      ok: false,
      error: {
        code: "invalid_tokyo_response",
        message: "CarePath Tokyo received an invalid API response.",
        requestId: null,
        status: null,
      },
    });
  });

  test("renders only a validated grounded explanation for the matching resource", () => {
    const response = successfulResponse();
    response.explanation_model_status = "used";
    response.explanations = [
      {
        resource_id: "cooling-1",
        text: "This result matches the requested service category.",
        reason_codes: ["category_match"],
        citations: [provenance],
      },
    ];
    expect(isTokyoAgentApiResponse(response)).toBe(true);
    if (!isTokyoAgentApiResponse(response)) {
      throw new Error("fixture should validate");
    }
    expect(explanationFor(response, "cooling-1")).toBe(
      "This result matches the requested service category.",
    );
    expect(explanationFor(response, "missing")).toBeNull();
  });
});

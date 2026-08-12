import { describe, expect, test } from "@jest/globals";

import { CarePathApiClient, type ApiFetcher } from "../api/client";
import {
  explanationFor,
  firstSourcePublisher,
  hardConstraintSummary,
  isTokyoAgentApiResponse,
  responseHasModelFallback,
  responseHasPartialResourceData,
  searchTokyoAgent,
} from "./api";
import type { TokyoAgentResponse, TokyoSafetyBoundaryResponse } from "./types";

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

function successfulResponse(): TokyoAgentResponse {
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

function safetyResponse(): TokyoSafetyBoundaryResponse {
  return {
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
}

function clarificationResponse(
  status: "clarification_required" | "unsupported" = "clarification_required",
): TokyoAgentResponse {
  const response = successfulResponse();
  return {
    ...response,
    status,
    search: null,
    explanations: [],
    clarification: { reason: "need_detail", message: "Please clarify the service you need." },
  };
}

function cloneSuccessful(): TokyoAgentResponse {
  return structuredClone(successfulResponse());
}

describe("CP-206 Tokyo API boundary", () => {
  test("accepts a grounded resource response and exposes fallback/partial state", () => {
    const response = successfulResponse();
    expect(isTokyoAgentApiResponse(response)).toBe(true);
    expect(responseHasModelFallback(response)).toBe(true);
    expect(responseHasPartialResourceData(response)).toBe(true);
    expect(explanationFor(response, "cooling-1")).toBeNull();
    expect(firstSourcePublisher(response)).toBe("Tokyo public authority");
    expect(hardConstraintSummary(response)).toEqual([]);
  });

  test("accepts the CP-205 safety boundary and bypasses ordinary helpers", () => {
    const response = safetyResponse();
    expect(isTokyoAgentApiResponse(response)).toBe(true);
    expect(responseHasModelFallback(response)).toBe(false);
    expect(responseHasPartialResourceData(response)).toBe(false);
    expect(explanationFor(response, "cooling-1")).toBeNull();
    expect(firstSourcePublisher(response)).toBeNull();
    expect(hardConstraintSummary(response)).toEqual([]);
  });

  test("rejects malformed top-level, safety, model, search and clarification shapes", () => {
    const validSafety = safetyResponse();
    const valid = successfulResponse();
    const malformed: unknown[] = [
      null,
      {},
      { status: "unsupported-status" },
      { status: "safety_boundary", safety: null },
      { status: "safety_boundary", safety: { disposition: 3 } },
      {
        ...validSafety,
        safety: { ...validSafety.safety, message: 3 },
      },
      {
        ...validSafety,
        safety: { ...validSafety.safety, bypass_resource_navigation: "yes" },
      },
      {
        ...validSafety,
        safety: { ...validSafety.safety, references: {} },
      },
      {
        ...validSafety,
        safety: { ...validSafety.safety, privacy: null },
      },
      {
        ...validSafety,
        safety: {
          ...validSafety.safety,
          privacy: { ...validSafety.safety.privacy, precise_location_persisted: true },
        },
      },
      { ...valid, intent: null },
      { ...valid, intent_model_status: 7 },
      { ...valid, explanation_model_status: 7 },
      { ...valid, explanations: {} },
      { ...valid, search: null },
      { ...valid, search: { ...valid.search, status: "no_match" } },
      { ...valid, search: { ...valid.search, results: {} } },
      { ...valid, search: { ...valid.search, count: "one" } },
      { ...clarificationResponse(), clarification: null },
      {
        ...clarificationResponse("unsupported"),
        clarification: { reason: "bad", message: 7 },
      },
    ];

    for (const value of malformed) {
      expect(isTokyoAgentApiResponse(value)).toBe(false);
    }
    expect(isTokyoAgentApiResponse(clarificationResponse())).toBe(true);
    expect(isTokyoAgentApiResponse(clarificationResponse("unsupported"))).toBe(true);
  });

  test("accepts a valid no-match response", () => {
    const response = successfulResponse();
    response.status = "no_match";
    if (response.search === null) {
      throw new Error("fixture search should exist");
    }
    response.search.status = "no_match";
    response.search.count = 0;
    response.search.results = [];
    response.search.no_match = {
      code: "no_matching_resources",
      message: "No match",
      hard_constraints: ["category=cooling_shelter"],
    };

    expect(isTokyoAgentApiResponse(response)).toBe(true);
    expect(hardConstraintSummary(response)).toEqual(["category=cooling_shelter"]);
  });

  test("returns upstream API failures without rewriting them", async () => {
    const fetcher: ApiFetcher = () =>
      Promise.resolve({
        ok: false,
        status: 503,
        json: () =>
          Promise.resolve({
            error: { code: "service_unavailable", message: "Unavailable", request_id: "req-1" },
          }),
      });
    const client = new CarePathApiClient("https://example.test", fetcher);

    const result = await searchTokyoAgent(client, {
      query: "Find a cooling shelter",
      interface_language: "en",
      location: { mode: "municipality", municipality: "江東区" },
      radius_km: 10,
      limit: 5,
    });

    expect(result.ok).toBe(false);
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

  test("returns a validated grounded API payload unchanged", async () => {
    const payload = successfulResponse();
    const fetcher: ApiFetcher = () =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payload),
      });
    const client = new CarePathApiClient("https://example.test", fetcher);

    const result = await searchTokyoAgent(client, {
      query: "Find a cooling shelter",
      interface_language: "en",
      location: { mode: "municipality", municipality: "江東区" },
      radius_km: 10,
      limit: 5,
    });

    expect(result).toEqual({ ok: true, data: payload });
  });

  test("detects every model fallback position and the fully deterministic path", () => {
    const intentFallback = successfulResponse();
    intentFallback.intent_model_status = "invalid";
    intentFallback.explanation_model_status = "not_needed";
    expect(responseHasModelFallback(intentFallback)).toBe(true);

    const explanationFallback = successfulResponse();
    explanationFallback.intent_model_status = "used";
    explanationFallback.explanation_model_status = "unavailable";
    expect(responseHasModelFallback(explanationFallback)).toBe(true);

    const noFallback = successfulResponse();
    noFallback.intent_model_status = "not_needed";
    noFallback.explanation_model_status = "used";
    expect(responseHasModelFallback(noFallback)).toBe(false);
  });

  test("keeps each partial official-data reason explicit and recognizes complete records", () => {
    const complete = cloneSuccessful();
    if (complete.search === null) {
      throw new Error("fixture search should exist");
    }
    const resource = complete.search.results[0]?.resource;
    if (resource === undefined) {
      throw new Error("fixture resource should exist");
    }
    resource.languages = ["en"];
    resource.opening_hours = "09:00-17:00";
    expect(responseHasPartialResourceData(complete)).toBe(false);

    const missingAddress = structuredClone(complete);
    if (missingAddress.search?.results[0] !== undefined) {
      missingAddress.search.results[0].resource.address = null;
    }
    expect(responseHasPartialResourceData(missingAddress)).toBe(true);

    const missingLanguages = structuredClone(complete);
    if (missingLanguages.search?.results[0] !== undefined) {
      missingLanguages.search.results[0].resource.languages = [];
    }
    expect(responseHasPartialResourceData(missingLanguages)).toBe(true);

    const missingHours = structuredClone(complete);
    if (missingHours.search?.results[0] !== undefined) {
      missingHours.search.results[0].resource.opening_hours = null;
    }
    expect(responseHasPartialResourceData(missingHours)).toBe(true);

    const unknownFreshness = structuredClone(complete);
    if (unknownFreshness.search?.results[0] !== undefined) {
      unknownFreshness.search.results[0].resource.freshness = "unknown";
    }
    expect(responseHasPartialResourceData(unknownFreshness)).toBe(true);
    expect(responseHasPartialResourceData(clarificationResponse())).toBe(false);
  });

  test("renders only the grounded explanation that belongs to the requested resource", () => {
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

    expect(explanationFor(response, "cooling-1")).toBe(
      "This result matches the requested service category.",
    );
    expect(explanationFor(response, "missing")).toBeNull();
  });

  test("returns source publishers only when a source-backed result exists", () => {
    expect(firstSourcePublisher(clarificationResponse())).toBeNull();

    const empty = successfulResponse();
    if (empty.search !== null) {
      empty.search.results = [];
      empty.search.count = 0;
    }
    expect(firstSourcePublisher(empty)).toBeNull();
    expect(firstSourcePublisher(successfulResponse())).toBe("Tokyo public authority");
  });

  test("rejects non-string hard constraints instead of displaying them", () => {
    const invalidArray = successfulResponse();
    invalidArray.status = "no_match";
    if (invalidArray.search === null) {
      throw new Error("fixture search should exist");
    }
    invalidArray.search.status = "no_match";
    invalidArray.search.no_match = {
      code: "no_matching_resources",
      message: "No match",
      hard_constraints: ["valid"],
    };
    (invalidArray.search.no_match as unknown as { hard_constraints: unknown }).hard_constraints = [
      "valid",
      3,
    ];
    expect(hardConstraintSummary(invalidArray)).toEqual([]);

    const nonArray = structuredClone(invalidArray);
    if (nonArray.search?.no_match !== null && nonArray.search?.no_match !== undefined) {
      (nonArray.search.no_match as unknown as { hard_constraints: unknown }).hard_constraints =
        "bad";
    }
    expect(hardConstraintSummary(nonArray)).toEqual([]);
  });
});

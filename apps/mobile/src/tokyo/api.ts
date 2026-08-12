import type { ApiResult, ControlledApiError } from "../api/client";
import type { CarePathApiClient } from "../api/client";
import type { TokyoAgentApiResponse, TokyoAgentRequest } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function isTokyoAgentApiResponse(value: unknown): value is TokyoAgentApiResponse {
  if (!isRecord(value) || typeof value.status !== "string") {
    return false;
  }

  if (value.status === "safety_boundary") {
    const safety = value.safety;
    if (!isRecord(safety) || typeof safety.disposition !== "string") {
      return false;
    }
    const privacy = safety.privacy;
    return (
      typeof safety.message === "string" &&
      typeof safety.bypass_resource_navigation === "boolean" &&
      Array.isArray(safety.references) &&
      isRecord(privacy) &&
      privacy.precise_location_persisted === false
    );
  }

  if (!["ok", "no_match", "clarification_required", "unsupported"].includes(value.status)) {
    return false;
  }
  if (!isRecord(value.intent)) {
    return false;
  }
  if (
    typeof value.intent_model_status !== "string" ||
    typeof value.explanation_model_status !== "string" ||
    !Array.isArray(value.explanations)
  ) {
    return false;
  }
  if (value.status === "ok" || value.status === "no_match") {
    if (!isRecord(value.search) || value.search.status !== value.status) {
      return false;
    }
    if (!Array.isArray(value.search.results) || typeof value.search.count !== "number") {
      return false;
    }
  }
  if (value.status === "clarification_required" || value.status === "unsupported") {
    if (!isRecord(value.clarification) || typeof value.clarification.message !== "string") {
      return false;
    }
  }
  return true;
}

function invalidResponseError(): ControlledApiError {
  return {
    code: "invalid_tokyo_response",
    message: "CarePath Tokyo received an invalid API response.",
    requestId: null,
    status: null,
  };
}

export async function searchTokyoAgent(
  client: CarePathApiClient,
  request: TokyoAgentRequest,
): Promise<ApiResult<TokyoAgentApiResponse>> {
  const result = await client.post<unknown>("/tokyo/agent/search", request);
  if (!result.ok) {
    return result;
  }
  if (!isTokyoAgentApiResponse(result.data)) {
    return { ok: false, error: invalidResponseError() };
  }
  return { ok: true, data: result.data };
}

export function responseHasModelFallback(response: TokyoAgentApiResponse): boolean {
  if (response.status === "safety_boundary") {
    return false;
  }
  return [response.intent_model_status, response.explanation_model_status].some(
    (status) => status === "invalid" || status === "unavailable",
  );
}

export function responseHasPartialResourceData(response: TokyoAgentApiResponse): boolean {
  if (response.status === "safety_boundary" || response.search === null) {
    return false;
  }
  return response.search.results.some(({ resource }) => {
    return (
      resource.address === null ||
      resource.languages.length === 0 ||
      resource.opening_hours === null ||
      resource.freshness === "unknown"
    );
  });
}

export function explanationFor(response: TokyoAgentApiResponse, resourceId: string): string | null {
  if (response.status === "safety_boundary") {
    return null;
  }
  const explanation = response.explanations.find((item) => item.resource_id === resourceId);
  return explanation?.text ?? null;
}

export function firstSourcePublisher(response: TokyoAgentApiResponse): string | null {
  if (response.status === "safety_boundary" || response.search === null) {
    return null;
  }
  const first = response.search.results[0]?.resource.provenance[0];
  return first?.publisher ?? null;
}

export function hardConstraintSummary(response: TokyoAgentApiResponse): string[] {
  if (response.status === "safety_boundary" || response.search?.no_match === null) {
    return [];
  }
  return isStringArray(response.search.no_match.hard_constraints)
    ? response.search.no_match.hard_constraints
    : [];
}

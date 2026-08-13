import type { AppLocale } from "../i18n/resources";

export type TokyoInterfaceLanguage = AppLocale;

export type TokyoLocation =
  | {
      mode: "coordinates";
      latitude: number;
      longitude: number;
    }
  | {
      mode: "municipality";
      municipality: string;
    };

export type TokyoResourceCategory =
  | "healthcare"
  | "cooling_shelter"
  | "public_health"
  | "family_support"
  | "women_support"
  | "mental_health_support";

export type TokyoFreshness = "current" | "aging" | "stale" | "unknown";

export interface TokyoSourceProvenance {
  source_id: string;
  source_record_id: string;
  source_url: string;
  catalog_url: string;
  publisher: string;
  licence: string;
  source_as_of: string | null;
  retrieved_at: string;
  content_sha256: string;
}

export interface TokyoResource {
  resource_id: string;
  name: string;
  category: TokyoResourceCategory;
  address: string | null;
  municipality: string | null;
  latitude: number | null;
  longitude: number | null;
  languages: string[];
  opening_hours: string | null;
  access_notes: string | null;
  phone: string | null;
  website: string | null;
  freshness: TokyoFreshness;
  provenance: TokyoSourceProvenance[];
  data_quality_flags: string[];
}

export interface TokyoResourceSearchResult {
  rank: number;
  distance_km: number | null;
  resource: TokyoResource;
}

export interface TokyoNoMatchDetail {
  code: "no_matching_resources";
  message: string;
  hard_constraints: string[];
}

export interface TokyoSearchResponse {
  status: "ok" | "no_match";
  location: TokyoLocation;
  radius_km: number | null;
  applied_filters: {
    category: TokyoResourceCategory | null;
    required_languages: string[];
    require_known_opening_hours: boolean;
    require_access_notes: boolean;
    require_phone: boolean;
    require_website: boolean;
    allowed_freshness: TokyoFreshness[];
  };
  count: number;
  results: TokyoResourceSearchResult[];
  no_match: TokyoNoMatchDetail | null;
}

export type TokyoModelStatus = "not_needed" | "used" | "invalid" | "unavailable";
export type TokyoAgentStatus = "ok" | "no_match" | "clarification_required" | "unsupported";

export interface TokyoIntent {
  resolution: "resolved" | "clarification_required" | "unsupported";
  intent: string | null;
  category: string | null;
  interface_language: TokyoInterfaceLanguage;
  location_mode: "browser" | "manual";
  requested_languages: TokyoInterfaceLanguage[];
  language_constraint: "none" | "required" | "preferred";
  require_known_opening_hours: boolean;
  require_access_notes: boolean;
  require_phone: boolean;
  require_website: boolean;
  clarification_reason: string | null;
}

export interface TokyoGroundedExplanation {
  resource_id: string;
  text: string;
  reason_codes: string[];
  citations: TokyoSourceProvenance[];
}

export interface TokyoClarification {
  reason: string;
  message: string;
}

export interface TokyoAgentResponse {
  status: TokyoAgentStatus;
  intent: TokyoIntent;
  intent_source: "deterministic" | "model";
  intent_model_status: TokyoModelStatus;
  explanation_model_status: TokyoModelStatus;
  search: TokyoSearchResponse | null;
  explanations: TokyoGroundedExplanation[];
  clarification: TokyoClarification | null;
}

export type TokyoSafetyDisposition =
  | "routine_navigation"
  | "insufficient_information"
  | "urgent_professional_help"
  | "emergency_escalation";

export interface TokyoSafetyReference {
  source_id: string;
  title: string;
  publisher: string;
  canonical_url: string;
  retrieved_at: string;
  source_as_of: string | null;
}

export interface TokyoSafetyDecision {
  disposition: TokyoSafetyDisposition;
  bypass_resource_navigation: boolean;
  message: string;
  matched_rule_ids: string[];
  policy_flags: string[];
  references: TokyoSafetyReference[];
  privacy: {
    precise_location_use: "current_request_only";
    precise_location_persisted: false;
    free_text_persisted_by_tokyo_route: false;
    longitudinal_health_history_required: false;
  };
}

export interface TokyoSafetyBoundaryResponse {
  status: "safety_boundary";
  safety: TokyoSafetyDecision;
}

export type TokyoAgentApiResponse = TokyoAgentResponse | TokyoSafetyBoundaryResponse;

export interface TokyoAgentRequest {
  query: string;
  interface_language: TokyoInterfaceLanguage;
  location: TokyoLocation;
  radius_km: number;
  limit: number;
}

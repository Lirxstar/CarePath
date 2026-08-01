export interface ImportIssue {
  code: string;
  message: string;
  record_index: number | null;
  resource_type: string | null;
  original_value: string | null;
}

export interface ImportReport {
  import_id: string;
  status: "success" | "partial" | "failed";
  source_format: "csv" | "json" | "fhir";
  source_hash: string;
  imported_at: string;
  received_records: number;
  inserted_records: number;
  fixed_issues: ImportIssue[];
  skipped_records: ImportIssue[];
  blocking_errors: ImportIssue[];
}

export interface ApiHealthResponse {
  status?: string;
  provider?: string;
  [key: string]: unknown;
}

export interface UserProfileResponse {
  user_id: string;
  age_band: string;
  preferred_language: string;
  timezone: string;
  schedule_constraints: Record<string, unknown> | null;
  health_goals: string[];
  activity_constraints: string[] | null;
  coaching_preferences: Record<string, unknown> | null;
  consent_flags: Record<string, boolean>;
}

export interface ObservationRecord {
  observation_id: string;
  user_id: string;
  metric_type: string;
  value_numeric: number | null;
  value_boolean: boolean | null;
  unit: string | null;
  observed_at: string;
  source_type: string;
  quality_flag: string;
  confidence: number | null;
  metadata: Record<string, unknown> | null;
}

export interface ObservationPage {
  items: ObservationRecord[];
  limit: number;
  offset: number;
  returned_count: number;
}

export interface TrendSummary {
  metric: string;
  unit: string | null;
  start_date: string;
  end_date: string;
  mean: number | null;
  slope_per_day: number | null;
  percentage_change: number | null;
  coverage: number;
  reliability: string | AnalysisReliability;
  warnings: string[];
}

export interface PeriodComparison {
  current_mean: number | null;
  baseline_mean: number | null;
  absolute_change: number | null;
  percentage_change: number | null;
  baseline_start_date: string;
  baseline_end_date: string;
  reliability: string | AnalysisReliability;
}

export interface RecordTrendsResponse {
  user_id: string;
  metric_type: string;
  trend: TrendSummary;
  comparison: PeriodComparison;
}

export interface ResponseStatement {
  statement_id: string;
  text: string;
  citation_ids: string[];
}

export interface ResponsePlanAction {
  action_id: string;
  scheduled_date: string;
  description: string;
  frequency: string;
  difficulty: string;
  rationale: string;
  citation_ids: string[];
}

export interface ResponseCitation {
  citation_id: string;
  source_type: "user_record" | "external_guideline";
  evidence_id: string;
  source_ids: string[];
  source_id: string | null;
  chunk_id: string | null;
  display_citation: string | null;
  supports: string[];
}

export interface StructuredCoachResponse {
  language: string;
  risk_level: "routine" | "caution" | "urgent";
  what_i_noticed: ResponseStatement[];
  what_the_evidence_suggests: ResponseStatement[];
  realistic_plan_for_this_week: ResponsePlanAction[];
  when_to_seek_professional_help: string[];
  sources: ResponseCitation[];
  what_i_am_uncertain_about: string[];
  rendered_text: string;
}

export interface CoachMessageResponse {
  interaction_id: string;
  request_id: string;
  risk_level: "routine" | "caution" | "urgent";
  status: "in_progress" | "completed" | "blocked" | "failed";
  response_text: string;
  evidence_ids: string[];
  verification_disposition: string | null;
  structured_response: StructuredCoachResponse;
}

export interface AnalysisReliability {
  level: "high" | "medium" | "low";
  reason_codes: string[];
}

export interface PatientEvidenceItem {
  evidence_id: string;
  kind: "structured_fact" | "subjective_description" | "context_record";
  fact: string;
  source_record_ids: string[];
  start_date: string | null;
  end_date: string | null;
  reliability: AnalysisReliability;
  metadata: Record<string, string | number | boolean | null>;
}

export interface PatientEvidenceResponse {
  user_id: string;
  start_at: string;
  end_at: string;
  items: PatientEvidenceItem[];
}

export interface ExternalEvidenceMetadata {
  chunk_id: string;
  source_id: string;
  title: string;
  section_title: string | null;
  section_path: string[];
  canonical_url: string;
  published_at: string | null;
  updated_at: string | null;
  retrieved_at: string;
  language: string;
  topics: string[];
  organisation: string;
  license: string;
  source_content_hash: string;
  content_hash: string;
  ingestion_version: string;
  index_version: string;
  embedding_model: string;
}

export interface ExternalEvidenceHit {
  chunk_id: string;
  score: number;
  content: string;
  metadata: ExternalEvidenceMetadata;
  citation: string;
}

export interface InterventionPlan {
  plan_id: string;
  user_id: string;
  goal_id: string;
  version: number;
  start_date: string;
  end_date: string;
  status: string;
  generation_interaction_id: string;
  supersedes_plan_id: string | null;
}

export interface PlanAction {
  action_id: string;
  plan_id: string;
  domain: string;
  description: string;
  frequency: string;
  difficulty: string;
  rationale: string;
  status: string;
}

export interface CurrentPlanResponse {
  plan: InterventionPlan;
  actions: PlanAction[];
}

export interface PlanFeedbackResponse {
  plan_id: string;
  feedback: {
    feedback_id: string;
    action_id: string;
    user_id: string;
    response: string;
    completion_ratio: number | null;
    reason_text: string | null;
    created_at: string;
  };
}

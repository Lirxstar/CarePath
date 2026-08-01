import type { ApiResult, CarePathApiClient, ControlledApiError } from "../api/client";
import type {
  ApiHealthResponse,
  CoachMessageResponse,
  CurrentPlanResponse,
  ExternalEvidenceHit,
  ImportReport,
  ObservationPage,
  PatientEvidenceResponse,
  PlanFeedbackResponse,
  RecordTrendsResponse,
  UserProfileResponse,
} from "./apiTypes";
import type { DemoScenario } from "./demoScenario";

export const PRIMARY_METRICS = [
  "sleep_duration",
  "resting_heart_rate",
  "steps",
  "stress_score",
] as const;

export const HEALTH_RANGES = [7, 30, 60] as const;

export type PrimaryMetric = (typeof PRIMARY_METRICS)[number];
export type HealthRange = (typeof HEALTH_RANGES)[number];
export type ImportFormat = "csv" | "json";

export interface JourneyService {
  loadHealth: () => Promise<ApiResult<ApiHealthResponse>>;
  importDemo: () => Promise<ApiResult<ImportReport>>;
  importContent: (format: ImportFormat, content: string) => Promise<ApiResult<ImportReport>>;
  loadProfile: () => Promise<ApiResult<UserProfileResponse>>;
  loadTrend: (metric: PrimaryMetric, days?: number) => Promise<ApiResult<RecordTrendsResponse>>;
  loadObservations: (
    metric: PrimaryMetric,
    days: HealthRange,
  ) => Promise<ApiResult<ObservationPage>>;
  loadPatientEvidence: () => Promise<ApiResult<PatientEvidenceResponse>>;
  loadExternalEvidence: (query: string) => Promise<ApiResult<ExternalEvidenceHit[]>>;
  askQuestion: (message: string) => Promise<ApiResult<CoachMessageResponse>>;
  loadPlan: () => Promise<ApiResult<CurrentPlanResponse>>;
  submitFeedback: (
    planId: string,
    actionId: string,
    response: "accepted" | "rejected" | "completed",
  ) => Promise<ApiResult<PlanFeedbackResponse>>;
}

function localImportError(code: string, message: string): ApiResult<never> {
  const error: ControlledApiError = {
    code,
    message,
    requestId: null,
    status: null,
  };
  return { ok: false, error };
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function observationWindow(endDate: string, days: HealthRange): { startAt: string; endAt: string } {
  const end = new Date(`${endDate}T23:59:59.999Z`);
  const start = new Date(`${endDate}T00:00:00.000Z`);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return { startAt: start.toISOString(), endAt: end.toISOString() };
}

export class PrimaryJourneyService implements JourneyService {
  constructor(
    private readonly client: CarePathApiClient,
    readonly scenario: DemoScenario,
  ) {}

  loadHealth(): Promise<ApiResult<ApiHealthResponse>> {
    return this.client.get<ApiHealthResponse>("/health");
  }

  importDemo(): Promise<ApiResult<ImportReport>> {
    return this.client.post<ImportReport>("/records/import", {
      source_format: "json",
      content: this.scenario.importContent,
    });
  }

  importContent(format: ImportFormat, content: string): Promise<ApiResult<ImportReport>> {
    if (format === "csv") {
      return this.client.post<ImportReport>("/records/import", {
        source_format: "csv",
        content,
      });
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(content);
    } catch {
      return Promise.resolve(localImportError("invalid_json", "The JSON import is not valid JSON"));
    }
    if (!isObject(parsed)) {
      return Promise.resolve(
        localImportError("invalid_json_package", "The JSON import must contain one object package"),
      );
    }
    return this.client.post<ImportReport>("/records/import", {
      source_format: "json",
      content: parsed,
    });
  }

  loadProfile(): Promise<ApiResult<UserProfileResponse>> {
    return this.client.get<UserProfileResponse>(`/profiles/${this.scenario.userId}`);
  }

  loadTrend(metric: PrimaryMetric, days = 7): Promise<ApiResult<RecordTrendsResponse>> {
    const query = new URLSearchParams({
      user_id: this.scenario.userId,
      metric_type: metric,
      days: String(days),
      end_date: this.scenario.endDate,
    });
    return this.client.get<RecordTrendsResponse>(`/records/trends?${query.toString()}`);
  }

  loadObservations(metric: PrimaryMetric, days: HealthRange): Promise<ApiResult<ObservationPage>> {
    const { startAt, endAt } = observationWindow(this.scenario.endDate, days);
    const query = new URLSearchParams({
      user_id: this.scenario.userId,
      metric_type: metric,
      start_at: startAt,
      end_at: endAt,
      limit: "100",
      offset: "0",
    });
    return this.client.get<ObservationPage>(`/observations?${query.toString()}`);
  }

  loadPatientEvidence(): Promise<ApiResult<PatientEvidenceResponse>> {
    const query = new URLSearchParams({
      user_id: this.scenario.userId,
      window_days: "30",
      end_at: `${this.scenario.endDate}T23:59:59Z`,
    });
    return this.client.get<PatientEvidenceResponse>(`/evidence/patient/search?${query.toString()}`);
  }

  loadExternalEvidence(queryText: string): Promise<ApiResult<ExternalEvidenceHit[]>> {
    const query = new URLSearchParams({ query: queryText, top_k: "5" });
    return this.client.get<ExternalEvidenceHit[]>(`/evidence/external/search?${query.toString()}`);
  }

  async askQuestion(message: string): Promise<ApiResult<CoachMessageResponse>> {
    await this.loadExternalEvidence(message);
    return this.client.post<CoachMessageResponse>("/coach/message", {
      user_id: this.scenario.userId,
      message,
      language: "en",
    });
  }

  loadPlan(): Promise<ApiResult<CurrentPlanResponse>> {
    const query = new URLSearchParams({ user_id: this.scenario.userId });
    return this.client.get<CurrentPlanResponse>(`/plans/current?${query.toString()}`);
  }

  submitFeedback(
    planId: string,
    actionId: string,
    response: "accepted" | "rejected" | "completed",
  ): Promise<ApiResult<PlanFeedbackResponse>> {
    return this.client.post<PlanFeedbackResponse>(`/plans/${planId}/feedback`, {
      user_id: this.scenario.userId,
      action_id: actionId,
      response,
      completion_ratio: response === "completed" ? 1 : response === "rejected" ? 0 : null,
      reason_text: response === "rejected" ? "Not feasible for this demo week" : null,
    });
  }
}

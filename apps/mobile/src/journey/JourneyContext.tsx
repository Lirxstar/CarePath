import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import type { ApiLoadState, ApiResult, ControlledApiError } from "../api/client";
import { createRuntimeApiClient } from "../api/runtime";
import type {
  ApiHealthResponse,
  CoachMessageResponse,
  CurrentPlanResponse,
  ExternalEvidenceHit,
  ImportIssue,
  ImportReport,
  ObservationPage,
  ObservationRecord,
  PatientEvidenceResponse,
  PlanFeedbackResponse,
  RecordTrendsResponse,
  UserProfileResponse,
} from "./apiTypes";
import { buildCustomScenario } from "./customImport";
import { buildDemoScenarios, type DemoPersonaKey, type DemoScenario } from "./demoScenario";
import {
  PRIMARY_METRICS,
  PrimaryJourneyService,
  type HealthRange,
  type ImportFormat,
  type JourneyService,
  type PrimaryMetric,
} from "./service";

export interface JourneyProgress {
  imported: boolean;
  dashboard: boolean;
  healthData: boolean;
  question: boolean;
  evidence: boolean;
  plan: boolean;
  feedback: boolean;
}

export type TrendStates = Record<PrimaryMetric, ApiLoadState<RecordTrendsResponse>>;
export type SeriesStates = Record<PrimaryMetric, ApiLoadState<ObservationPage>>;

interface JourneyContextValue {
  scenarios: DemoScenario[];
  scenario: DemoScenario;
  mockMode: boolean;
  healthState: ApiLoadState<ApiHealthResponse>;
  profileState: ApiLoadState<UserProfileResponse>;
  importState: ApiLoadState<ImportReport>;
  customImportState: ApiLoadState<ImportReport>;
  recent7States: TrendStates;
  baseline30States: TrendStates;
  seriesStates: SeriesStates;
  healthRange: HealthRange;
  question: string;
  setQuestion: (value: string) => void;
  coachState: ApiLoadState<CoachMessageResponse>;
  patientEvidenceState: ApiLoadState<PatientEvidenceResponse>;
  externalEvidenceState: ApiLoadState<ExternalEvidenceHit[]>;
  planState: ApiLoadState<CurrentPlanResponse>;
  feedbackState: ApiLoadState<PlanFeedbackResponse>;
  progress: JourneyProgress;
  selectPersona: (key: DemoPersonaKey) => void;
  refreshHealthStatus: () => Promise<void>;
  importDemo: () => Promise<void>;
  importCustom: (format: ImportFormat, content: string) => Promise<void>;
  refreshDashboard: () => Promise<void>;
  refreshHealthData: (days?: HealthRange) => Promise<void>;
  askQuestion: () => Promise<void>;
  refreshPlan: () => Promise<void>;
  submitFeedback: (
    actionId: string,
    response: "accepted" | "rejected" | "completed",
  ) => Promise<void>;
}

interface JourneyProviderProps extends PropsWithChildren {
  apiBaseUrl?: string;
}

const JourneyContext = createContext<JourneyContextValue | null>(null);

function idleTrendStates(): TrendStates {
  return {
    sleep_duration: { status: "idle" },
    resting_heart_rate: { status: "idle" },
    steps: { status: "idle" },
    stress_score: { status: "idle" },
  };
}

function loadingTrendStates(): TrendStates {
  return {
    sleep_duration: { status: "loading" },
    resting_heart_rate: { status: "loading" },
    steps: { status: "loading" },
    stress_score: { status: "loading" },
  };
}

function idleSeriesStates(): SeriesStates {
  return {
    sleep_duration: { status: "idle" },
    resting_heart_rate: { status: "idle" },
    steps: { status: "idle" },
    stress_score: { status: "idle" },
  };
}

function loadingSeriesStates(): SeriesStates {
  return {
    sleep_duration: { status: "loading" },
    resting_heart_rate: { status: "loading" },
    steps: { status: "loading" },
    stress_score: { status: "loading" },
  };
}

function success<T>(data: T): ApiResult<T> {
  return { ok: true, data };
}

function failure<T>(code: string, message: string): ApiResult<T> {
  const error: ControlledApiError = { code, message, requestId: null, status: null };
  return { ok: false, error };
}

function mockIssue(code: string, message: string): ImportIssue {
  return {
    code,
    message,
    record_index: null,
    resource_type: null,
    original_value: null,
  };
}

function mockReport(
  format: "csv" | "json",
  status: "success" | "partial" | "failed",
  received: number,
  inserted: number,
  blockingErrors: ImportIssue[] = [],
): ImportReport {
  return {
    import_id: `mock-${format}-import`,
    status,
    source_format: format,
    source_hash: "0".repeat(64),
    imported_at: "2026-07-30T12:00:00Z",
    received_records: received,
    inserted_records: inserted,
    fixed_issues: [],
    skipped_records: [],
    blocking_errors: blockingErrors,
  };
}

function dateOrdinal(value: string): number {
  return new Date(value).getTime();
}

function mean(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function safeString(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

class MockJourneyService implements JourneyService {
  constructor(readonly scenario: DemoScenario) {}

  loadHealth(): Promise<ApiResult<ApiHealthResponse>> {
    return Promise.resolve(success({ status: "ok", provider: "frontend-mock" }));
  }

  importDemo(): Promise<ApiResult<ImportReport>> {
    const received = this.scenario.importContent.observations.length;
    return Promise.resolve(success(mockReport("json", "success", received, received)));
  }

  importContent(format: ImportFormat, content: string): Promise<ApiResult<ImportReport>> {
    if (!content.trim()) {
      return Promise.resolve(
        success(
          mockReport("csv", "failed", 0, 0, [
            mockIssue("empty_import", "The selected import contains no data."),
          ]),
        ),
      );
    }
    return Promise.resolve(success(mockReport(format, "success", 1, 1)));
  }

  loadProfile(): Promise<ApiResult<UserProfileResponse>> {
    const profile = this.scenario.importContent.profile;
    return Promise.resolve(
      success({
        user_id: this.scenario.userId,
        age_band: safeString(profile.age_band, "18-29"),
        preferred_language: safeString(profile.preferred_language, "en"),
        timezone: safeString(profile.timezone, "Asia/Tokyo"),
        schedule_constraints: { demo: true },
        health_goals: ["sleep", "physical_activity", "stress_mood"],
        activity_constraints: [],
        coaching_preferences: { plan_size: "small", tone: "practical" },
        consent_flags: { synthetic_demo: true },
      }),
    );
  }

  loadTrend(metric: PrimaryMetric, days = 7): Promise<ApiResult<RecordTrendsResponse>> {
    const end = dateOrdinal(`${this.scenario.endDate}T23:59:59Z`);
    const dayMs = 86_400_000;
    const currentStart = end - (days - 1) * dayMs;
    const baselineEnd = currentStart - 1;
    const baselineStart = baselineEnd - (days - 1) * dayMs;
    const relevant = this.scenario.importContent.observations.filter(
      (item) => item.metric_type === metric && item.quality_flag === "valid",
    );
    const current = relevant.filter((item) => {
      const timestamp = dateOrdinal(item.observed_at);
      return timestamp >= currentStart && timestamp <= end;
    });
    const baseline = relevant.filter((item) => {
      const timestamp = dateOrdinal(item.observed_at);
      return timestamp >= baselineStart && timestamp <= baselineEnd;
    });
    const currentMean = mean(current.map((item) => item.value_numeric));
    const baselineMean = mean(baseline.map((item) => item.value_numeric));
    const absoluteChange =
      currentMean === null || baselineMean === null ? null : currentMean - baselineMean;
    const percentageChange =
      absoluteChange === null || baselineMean === null || baselineMean === 0
        ? null
        : (absoluteChange / Math.abs(baselineMean)) * 100;
    const unit = relevant[0]?.unit ?? null;
    const currentStartDate = new Date(currentStart).toISOString().slice(0, 10);
    const baselineStartDate = new Date(baselineStart).toISOString().slice(0, 10);
    const baselineEndDate = new Date(baselineEnd).toISOString().slice(0, 10);
    const coverage = Math.min(1, current.length / days);
    const reliability = coverage >= 0.8 ? "high" : coverage >= 0.5 ? "medium" : "low";
    return Promise.resolve(
      success({
        user_id: this.scenario.userId,
        metric_type: metric,
        trend: {
          metric,
          unit,
          start_date: currentStartDate,
          end_date: this.scenario.endDate,
          mean: currentMean,
          slope_per_day: null,
          percentage_change: percentageChange,
          coverage,
          reliability,
          warnings: coverage < 0.8 ? ["incomplete_coverage"] : [],
        },
        comparison: {
          current_mean: currentMean,
          baseline_mean: baselineMean,
          absolute_change: absoluteChange,
          percentage_change: percentageChange,
          baseline_start_date: baselineStartDate,
          baseline_end_date: baselineEndDate,
          reliability,
        },
      }),
    );
  }

  loadObservations(metric: PrimaryMetric, days: HealthRange): Promise<ApiResult<ObservationPage>> {
    const end = dateOrdinal(`${this.scenario.endDate}T23:59:59Z`);
    const start = end - (days - 1) * 86_400_000;
    const items: ObservationRecord[] = this.scenario.importContent.observations
      .filter(
        (item) =>
          item.metric_type === metric &&
          dateOrdinal(item.observed_at) >= start &&
          dateOrdinal(item.observed_at) <= end,
      )
      .map((item) => ({
        observation_id: item.observation_id,
        user_id: item.user_id,
        metric_type: item.metric_type,
        value_numeric: item.value_numeric,
        value_boolean: null,
        unit: item.unit,
        observed_at: item.observed_at,
        source_type: item.source_type,
        quality_flag: item.quality_flag,
        confidence: item.confidence,
        metadata: item.metadata,
      }));
    return Promise.resolve(success({ items, limit: 100, offset: 0, returned_count: items.length }));
  }

  async loadPatientEvidence(): Promise<ApiResult<PatientEvidenceResponse>> {
    const trend = await this.loadTrend("sleep_duration", 7);
    const sourceIds = this.scenario.importContent.observations
      .filter((item) => item.metric_type === "sleep_duration")
      .slice(-7)
      .map((item) => item.observation_id);
    const fact = trend.ok
      ? `Recent sleep mean is ${String(Math.round((trend.data.trend.mean ?? 0) * 10) / 10)} ${trend.data.trend.unit ?? ""}.`
      : "Recent sleep data are unavailable.";
    return success({
      user_id: this.scenario.userId,
      start_at: "2026-06-29T23:59:59Z",
      end_at: `${this.scenario.endDate}T23:59:59Z`,
      items: [
        {
          evidence_id: "mock-patient-sleep",
          kind: "structured_fact",
          fact,
          source_record_ids: sourceIds,
          start_date: "2026-07-22",
          end_date: this.scenario.endDate,
          reliability: { level: "high", reason_codes: [] },
          metadata: { metric_type: "sleep_duration" },
        },
        {
          evidence_id: "mock-user-report",
          kind: "subjective_description",
          fact: safeString(
            this.scenario.importContent.journal_entries[0]?.text,
            "Synthetic journal entry",
          ),
          source_record_ids: [],
          start_date: "2026-07-27",
          end_date: "2026-07-27",
          reliability: { level: "medium", reason_codes: ["user_report"] },
          metadata: {},
        },
      ],
    });
  }

  loadExternalEvidence(queryText: string): Promise<ApiResult<ExternalEvidenceHit[]>> {
    void queryText;
    return Promise.resolve(
      success([
        {
          chunk_id: "mock-guideline-chunk",
          score: 0.91,
          content:
            "Regular daily routines and manageable physical activity can support healthy behaviour patterns. Plans should be adjusted to the person's circumstances and available data.",
          metadata: {
            chunk_id: "mock-guideline-chunk",
            source_id: "mock-guideline-source",
            title: "Synthetic demo behaviour-support guidance",
            section_title: "Daily routines",
            section_path: ["Daily routines"],
            canonical_url: "https://example.invalid/carepath-demo-guidance",
            published_at: "2025-01-01",
            updated_at: "2026-01-15",
            retrieved_at: "2026-07-30",
            language: "en",
            topics: ["sleep", "physical_activity"],
            organisation: "CarePath synthetic demo",
            license: "demo-only",
            source_content_hash: "1".repeat(64),
            content_hash: "2".repeat(64),
            ingestion_version: "demo-v1",
            index_version: "demo-v1",
            embedding_model: "frontend-mock",
          },
          citation: "CarePath synthetic demo — Daily routines",
        },
      ]),
    );
  }

  async askQuestion(message: string): Promise<ApiResult<CoachMessageResponse>> {
    if (!message.trim()) {
      return failure("empty_question", "Enter a health-behaviour question before sending.");
    }
    const sleep = await this.loadTrend("sleep_duration", 7);
    const sleepText = sleep.ok
      ? `Recent sleep summary: ${String(Math.round((sleep.data.trend.mean ?? 0) * 10) / 10)} ${sleep.data.trend.unit ?? ""}.`
      : "Recent sleep summary is unavailable.";
    const actions = this.scenario.importContent.intervention_history.actions.slice(0, 3);
    return success({
      interaction_id: "mock-interaction",
      request_id: "mock-request",
      risk_level: "routine",
      status: "completed",
      response_text: "Synthetic structured coaching response.",
      evidence_ids: ["mock-patient-sleep", "external:mock-guideline-chunk"],
      verification_disposition: "pass",
      structured_response: {
        language: "en",
        risk_level: "routine",
        what_i_noticed: [
          {
            statement_id: "noticed-1",
            text: sleepText,
            citation_ids: ["user-records:sleep"],
          },
        ],
        what_the_evidence_suggests: [
          {
            statement_id: "evidence-1",
            text: "The demo guidance supports small, context-aware routine changes.",
            citation_ids: ["guideline:mock-guideline-chunk"],
          },
        ],
        realistic_plan_for_this_week: actions.map((action, index) => ({
          action_id: `mock-plan-${String(index + 1)}`,
          scheduled_date: action.frequency.replace("once on ", ""),
          description: action.description,
          frequency: action.frequency,
          difficulty: action.difficulty,
          rationale: action.rationale,
          citation_ids: ["guideline:mock-guideline-chunk"],
        })),
        when_to_seek_professional_help: [
          "Seek professional assessment if symptoms persist or worsen, or if an action conflicts with an existing professional restriction.",
        ],
        sources: [
          {
            citation_id: "user-records:sleep",
            source_type: "user_record",
            evidence_id: "mock-patient-sleep",
            source_ids: this.scenario.importContent.observations
              .filter((item) => item.metric_type === "sleep_duration")
              .slice(-7)
              .map((item) => item.observation_id),
            source_id: null,
            chunk_id: null,
            display_citation: null,
            supports: ["noticed-1"],
          },
          {
            citation_id: "guideline:mock-guideline-chunk",
            source_type: "external_guideline",
            evidence_id: "external:mock-guideline-chunk",
            source_ids: ["mock-guideline-source", "mock-guideline-chunk"],
            source_id: "mock-guideline-source",
            chunk_id: "mock-guideline-chunk",
            display_citation: "CarePath synthetic demo — Daily routines",
            supports: [
              "evidence-1",
              ...actions.map((_action, index) => `mock-plan-${String(index + 1)}`),
            ],
          },
        ],
        what_i_am_uncertain_about: [
          "This synthetic demo cannot determine a medical cause or diagnosis from the records.",
        ],
        rendered_text: "Synthetic structured coaching response.",
      },
    });
  }

  loadPlan(): Promise<ApiResult<CurrentPlanResponse>> {
    const plan = this.scenario.importContent.intervention_history.plans[0];
    if (plan === undefined) {
      return Promise.resolve(failure("plan_not_found", "No demo plan is available."));
    }
    return Promise.resolve(
      success({
        plan: { ...plan, supersedes_plan_id: null },
        actions: this.scenario.importContent.intervention_history.actions,
      }),
    );
  }

  submitFeedback(
    planId: string,
    actionId: string,
    response: "accepted" | "rejected" | "completed",
  ): Promise<ApiResult<PlanFeedbackResponse>> {
    return Promise.resolve(
      success({
        plan_id: planId,
        feedback: {
          feedback_id: "mock-feedback",
          action_id: actionId,
          user_id: this.scenario.userId,
          response,
          completion_ratio: response === "completed" ? 1 : response === "rejected" ? 0 : null,
          reason_text: response === "rejected" ? "Not feasible for this demo week" : null,
          created_at: "2026-07-30T12:00:00Z",
        },
      }),
    );
  }
}

function resultState<T>(result: ApiResult<T>): ApiLoadState<T> {
  return result.ok
    ? { status: "success", data: result.data }
    : { status: "error", error: result.error };
}

export function JourneyProvider({ children, apiBaseUrl }: JourneyProviderProps) {
  const [initial] = useState(() => {
    const scenarios = buildDemoScenarios();
    const scenario = scenarios[0];
    if (scenario === undefined) {
      throw new Error("At least one demo persona is required");
    }
    return { scenarios, scenario };
  });
  const [scenario, setScenario] = useState(initial.scenario);
  const [question, setQuestion] = useState(initial.scenario.question);
  const [customDataActive, setCustomDataActive] = useState(false);
  const mockMode = process.env.EXPO_PUBLIC_CAREPATH_MOCK_MODE === "true";
  const service = useMemo<JourneyService>(
    () =>
      mockMode
        ? new MockJourneyService(scenario)
        : new PrimaryJourneyService(createRuntimeApiClient(apiBaseUrl), scenario),
    [apiBaseUrl, mockMode, scenario],
  );

  const [healthState, setHealthState] = useState<ApiLoadState<ApiHealthResponse>>({
    status: "idle",
  });
  const [profileState, setProfileState] = useState<ApiLoadState<UserProfileResponse>>({
    status: "idle",
  });
  const [importState, setImportState] = useState<ApiLoadState<ImportReport>>({ status: "idle" });
  const [customImportState, setCustomImportState] = useState<ApiLoadState<ImportReport>>({
    status: "idle",
  });
  const [recent7States, setRecent7States] = useState<TrendStates>(idleTrendStates);
  const [baseline30States, setBaseline30States] = useState<TrendStates>(idleTrendStates);
  const [seriesStates, setSeriesStates] = useState<SeriesStates>(idleSeriesStates);
  const [healthRange, setHealthRange] = useState<HealthRange>(30);
  const [coachState, setCoachState] = useState<ApiLoadState<CoachMessageResponse>>({
    status: "idle",
  });
  const [patientEvidenceState, setPatientEvidenceState] = useState<
    ApiLoadState<PatientEvidenceResponse>
  >({
    status: "idle",
  });
  const [externalEvidenceState, setExternalEvidenceState] = useState<
    ApiLoadState<ExternalEvidenceHit[]>
  >({
    status: "idle",
  });
  const [planState, setPlanState] = useState<ApiLoadState<CurrentPlanResponse>>({ status: "idle" });
  const [feedbackState, setFeedbackState] = useState<ApiLoadState<PlanFeedbackResponse>>({
    status: "idle",
  });

  const refreshHealthStatus = useCallback(async () => {
    setHealthState({ status: "loading" });
    setHealthState(resultState(await service.loadHealth()));
  }, [service]);

  useEffect(() => {
    void refreshHealthStatus();
  }, [refreshHealthStatus]);

  const refreshPlan = useCallback(async () => {
    setPlanState({ status: "loading" });
    setPlanState(resultState(await service.loadPlan()));
  }, [service]);

  const refreshDashboard = useCallback(async () => {
    setProfileState({ status: "loading" });
    setRecent7States(loadingTrendStates());
    setBaseline30States(loadingTrendStates());
    setPlanState({ status: "loading" });
    const [profile, recentEntries, baselineEntries, plan] = await Promise.all([
      service.loadProfile(),
      Promise.all(
        PRIMARY_METRICS.map(
          async (metric) => [metric, await service.loadTrend(metric, 7)] as const,
        ),
      ),
      Promise.all(
        PRIMARY_METRICS.map(
          async (metric) => [metric, await service.loadTrend(metric, 30)] as const,
        ),
      ),
      service.loadPlan(),
    ]);
    setProfileState(resultState(profile));
    const recent = idleTrendStates();
    const baseline = idleTrendStates();
    for (const [metric, result] of recentEntries) {
      recent[metric] = resultState(result);
    }
    for (const [metric, result] of baselineEntries) {
      baseline[metric] = resultState(result);
    }
    setRecent7States(recent);
    setBaseline30States(baseline);
    setPlanState(resultState(plan));
  }, [service]);

  const refreshHealthData = useCallback(
    async (days: HealthRange = healthRange) => {
      setHealthRange(days);
      setSeriesStates(loadingSeriesStates());
      const entries = await Promise.all(
        PRIMARY_METRICS.map(
          async (metric) => [metric, await service.loadObservations(metric, days)] as const,
        ),
      );
      const next = idleSeriesStates();
      for (const [metric, result] of entries) {
        next[metric] = resultState(result);
      }
      setSeriesStates(next);
    },
    [healthRange, service],
  );

  const importDemo = useCallback(async () => {
    setCustomDataActive(false);
    setImportState({ status: "loading" });
    setFeedbackState({ status: "idle" });
    const result = await service.importDemo();
    setImportState(resultState(result));
    if (result.ok) {
      await Promise.all([refreshDashboard(), refreshHealthData(healthRange)]);
    }
  }, [healthRange, refreshDashboard, refreshHealthData, service]);

  const importCustom = useCallback(
    async (format: ImportFormat, content: string) => {
      const nextScenario = buildCustomScenario(format, content, scenario);
      if (nextScenario === null) {
        setCustomImportState(
          resultState(
            failure<ImportReport>(
              "custom_import_subject_missing",
              "The import must include a user_id and at least one valid observed_at timestamp so CarePath can switch the demo to your data.",
            ),
          ),
        );
        return;
      }

      setCustomImportState({ status: "loading" });
      const result = await service.importContent(format, content);
      setCustomImportState(resultState(result));
      if (result.ok && result.data.status !== "failed") {
        setScenario(nextScenario);
        setQuestion(nextScenario.question);
        setImportState(resultState(result));
        setCustomDataActive(true);
        setProfileState({ status: "idle" });
        setRecent7States(idleTrendStates());
        setBaseline30States(idleTrendStates());
        setSeriesStates(idleSeriesStates());
        setCoachState({ status: "idle" });
        setPatientEvidenceState({ status: "idle" });
        setExternalEvidenceState({ status: "idle" });
        setPlanState({ status: "idle" });
        setFeedbackState({ status: "idle" });
      }
    },
    [scenario, service],
  );

  useEffect(() => {
    if (
      !customDataActive ||
      importState.status !== "success" ||
      importState.data.status === "failed"
    ) {
      return;
    }
    void Promise.all([refreshDashboard(), refreshHealthData(healthRange)]);
  }, [
    customDataActive,
    healthRange,
    importState,
    refreshDashboard,
    refreshHealthData,
    scenario.userId,
  ]);

  const askQuestion = useCallback(async () => {
    setCoachState({ status: "loading" });
    setPatientEvidenceState({ status: "loading" });
    setExternalEvidenceState({ status: "loading" });
    const [coach, patientEvidence, externalEvidence] = await Promise.all([
      service.askQuestion(question),
      service.loadPatientEvidence(),
      service.loadExternalEvidence(question),
    ]);
    setCoachState(resultState(coach));
    setPatientEvidenceState(resultState(patientEvidence));
    setExternalEvidenceState(resultState(externalEvidence));
  }, [question, service]);

  const submitFeedback = useCallback(
    async (actionId: string, response: "accepted" | "rejected" | "completed") => {
      if (planState.status !== "success") {
        setFeedbackState({
          status: "error",
          error: {
            code: "plan_not_loaded",
            message: "Load the current plan before submitting feedback",
            requestId: null,
            status: null,
          },
        });
        return;
      }
      setFeedbackState({ status: "loading" });
      const result = await service.submitFeedback(planState.data.plan.plan_id, actionId, response);
      setFeedbackState(resultState(result));
      if (result.ok) {
        await refreshPlan();
      }
    },
    [planState, refreshPlan, service],
  );

  const selectPersona = useCallback(
    (key: DemoPersonaKey) => {
      const next = initial.scenarios.find((item) => item.key === key);
      if (next === undefined || next.userId === scenario.userId) {
        return;
      }
      setCustomDataActive(false);
      setScenario(next);
      setQuestion(next.question);
      setProfileState({ status: "idle" });
      setImportState({ status: "idle" });
      setCustomImportState({ status: "idle" });
      setRecent7States(idleTrendStates());
      setBaseline30States(idleTrendStates());
      setSeriesStates(idleSeriesStates());
      setCoachState({ status: "idle" });
      setPatientEvidenceState({ status: "idle" });
      setExternalEvidenceState({ status: "idle" });
      setPlanState({ status: "idle" });
      setFeedbackState({ status: "idle" });
    },
    [initial.scenarios, scenario.userId],
  );

  const progress = useMemo<JourneyProgress>(
    () => ({
      imported: importState.status === "success" && importState.data.status !== "failed",
      dashboard:
        profileState.status === "success" &&
        PRIMARY_METRICS.every((metric) => recent7States[metric].status === "success"),
      healthData: PRIMARY_METRICS.every((metric) => seriesStates[metric].status === "success"),
      question: coachState.status === "success",
      evidence:
        patientEvidenceState.status === "success" ||
        externalEvidenceState.status === "success" ||
        (coachState.status === "success" && coachState.data.structured_response.sources.length > 0),
      plan: planState.status === "success" && planState.data.actions.length > 0,
      feedback: feedbackState.status === "success",
    }),
    [
      coachState,
      externalEvidenceState.status,
      feedbackState.status,
      importState,
      patientEvidenceState.status,
      planState,
      profileState.status,
      recent7States,
      seriesStates,
    ],
  );

  const value = useMemo<JourneyContextValue>(
    () => ({
      scenarios: initial.scenarios,
      scenario,
      mockMode,
      healthState,
      profileState,
      importState,
      customImportState,
      recent7States,
      baseline30States,
      seriesStates,
      healthRange,
      question,
      setQuestion,
      coachState,
      patientEvidenceState,
      externalEvidenceState,
      planState,
      feedbackState,
      progress,
      selectPersona,
      refreshHealthStatus,
      importDemo,
      importCustom,
      refreshDashboard,
      refreshHealthData,
      askQuestion,
      refreshPlan,
      submitFeedback,
    }),
    [
      askQuestion,
      baseline30States,
      coachState,
      customImportState,
      externalEvidenceState,
      feedbackState,
      healthRange,
      healthState,
      importCustom,
      importDemo,
      importState,
      initial.scenarios,
      mockMode,
      patientEvidenceState,
      planState,
      profileState,
      progress,
      question,
      recent7States,
      refreshDashboard,
      refreshHealthData,
      refreshHealthStatus,
      refreshPlan,
      scenario,
      selectPersona,
      seriesStates,
      submitFeedback,
    ],
  );

  return <JourneyContext.Provider value={value}>{children}</JourneyContext.Provider>;
}

export function useJourney(): JourneyContextValue {
  const value = useContext(JourneyContext);
  if (value === null) {
    throw new Error("useJourney must be used inside JourneyProvider");
  }
  return value;
}

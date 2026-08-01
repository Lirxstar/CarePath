import { describe, expect, test } from "@jest/globals";

import {
  CarePathApiClient,
  type ApiFetcher,
  type ApiRequestInit,
  type ApiResponse,
} from "../api/client";
import { buildDemoScenario } from "./demoScenario";
import { PRIMARY_METRICS, PrimaryJourneyService } from "./service";

interface RecordedCall {
  url: string;
  init: ApiRequestInit;
}

function response(payload: unknown, status = 200): ApiResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
  };
}

function parseBody(body: string | undefined): Record<string, unknown> {
  const parsed: unknown = JSON.parse(body ?? "{}");
  if (typeof parsed !== "object" || parsed === null) {
    throw new Error("Expected a JSON object request body");
  }
  return parsed as Record<string, unknown>;
}

function importReport(format: "csv" | "json") {
  return {
    import_id: "import-1",
    status: "success",
    source_format: format,
    source_hash: "a".repeat(64),
    imported_at: "2026-07-30T08:00:00Z",
    received_records: 12,
    inserted_records: 12,
    fixed_issues: [],
    skipped_records: [],
    blocking_errors: [],
  };
}

function coachResponse() {
  return {
    interaction_id: "interaction-1",
    request_id: "request-1",
    risk_level: "routine",
    status: "completed",
    response_text: "Six verified sections.",
    evidence_ids: ["external:chunk-sleep"],
    verification_disposition: "pass",
    structured_response: {
      language: "en",
      risk_level: "routine",
      what_i_noticed: [],
      what_the_evidence_suggests: [],
      realistic_plan_for_this_week: [],
      when_to_seek_professional_help: ["Seek professional assessment if symptoms persist."],
      sources: [
        {
          citation_id: "external:chunk-sleep",
          source_type: "external_guideline",
          evidence_id: "external:chunk-sleep",
          source_ids: ["src-sleep", "chunk-sleep"],
          source_id: "src-sleep",
          chunk_id: "chunk-sleep",
          display_citation: "CDC — About Sleep",
          supports: ["plan-action-1"],
        },
      ],
      what_i_am_uncertain_about: ["CarePath cannot determine a diagnosis."],
      rendered_text: "Six verified sections.",
    },
  };
}

describe("PrimaryJourneyService", () => {
  test("connects dashboard, raw data, evidence, coach, plan and import endpoints", async () => {
    const calls: RecordedCall[] = [];
    const scenario = buildDemoScenario();
    const actionId = "action-1";
    const fetcher: ApiFetcher = (url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/health")) {
        return Promise.resolve(response({ status: "ok", provider: "mock" }));
      }
      if (url.endsWith("/records/import")) {
        const body = parseBody(init.body);
        return Promise.resolve(
          response(importReport(body.source_format === "csv" ? "csv" : "json")),
        );
      }
      if (url.includes(`/profiles/${scenario.userId}`)) {
        return Promise.resolve(
          response({
            user_id: scenario.userId,
            age_band: "18-29",
            preferred_language: "en",
            timezone: "Asia/Tokyo",
            schedule_constraints: {},
            health_goals: ["sleep"],
            activity_constraints: {},
            coaching_preferences: {},
            consent_flags: { synthetic_demo: true },
          }),
        );
      }
      if (url.includes("/records/trends?")) {
        const metric = new URL(url).searchParams.get("metric_type") ?? "sleep_duration";
        return Promise.resolve(
          response({
            user_id: scenario.userId,
            metric_type: metric,
            trend: {
              metric,
              unit: metric === "steps" ? "steps" : "hours",
              start_date: "2026-07-22",
              end_date: "2026-07-28",
              mean: 6.6,
              slope_per_day: 0,
              percentage_change: -15.4,
              coverage: 1,
              reliability: "high",
              warnings: [],
            },
            comparison: {
              current_mean: 6.6,
              baseline_mean: 7.8,
              absolute_change: -1.2,
              percentage_change: -15.4,
              baseline_start_date: "2026-07-15",
              baseline_end_date: "2026-07-21",
              reliability: "high",
            },
          }),
        );
      }
      if (url.includes("/observations?")) {
        return Promise.resolve(
          response({
            items: [
              {
                observation_id: "observation-1",
                user_id: scenario.userId,
                metric_type: "sleep_duration",
                value_numeric: 6.5,
                value_boolean: null,
                unit: "hours",
                observed_at: "2026-07-28T08:00:00Z",
                source_type: "synthetic_wearable",
                quality_flag: "valid",
                confidence: 1,
                metadata: {},
              },
            ],
            limit: 100,
            offset: 0,
            returned_count: 1,
          }),
        );
      }
      if (url.includes("/evidence/patient/search?")) {
        return Promise.resolve(
          response({
            user_id: scenario.userId,
            start_at: "2026-06-29T23:59:59Z",
            end_at: "2026-07-28T23:59:59Z",
            items: [],
          }),
        );
      }
      if (url.includes("/evidence/external/search?")) {
        return Promise.resolve(
          response([
            {
              chunk_id: "chunk-sleep",
              score: 0.9,
              content: "Keep a regular sleep schedule.",
              metadata: {
                chunk_id: "chunk-sleep",
                source_id: "src-sleep",
                title: "About Sleep",
                section_title: "Sleep habits",
                section_path: ["Sleep habits"],
                canonical_url: "https://example.test/sleep",
                published_at: "2025-01-01",
                updated_at: "2026-01-01",
                retrieved_at: "2026-07-30",
                language: "en",
                topics: ["sleep"],
                organisation: "Example Health",
                license: "public",
                source_content_hash: "b".repeat(64),
                content_hash: "c".repeat(64),
                ingestion_version: "v1",
                index_version: "v1",
                embedding_model: "test",
              },
              citation: "Example Health — About Sleep",
            },
          ]),
        );
      }
      if (url.endsWith("/coach/message")) {
        return Promise.resolve(response(coachResponse()));
      }
      if (url.includes("/plans/current?")) {
        return Promise.resolve(
          response({
            plan: {
              plan_id: scenario.planId,
              user_id: scenario.userId,
              goal_id: scenario.goalId,
              version: 1,
              start_date: "2026-07-30",
              end_date: "2026-08-05",
              status: "active",
              generation_interaction_id: "interaction-import",
              supersedes_plan_id: null,
            },
            actions: [
              {
                action_id: actionId,
                plan_id: scenario.planId,
                domain: "sleep",
                description: "Keep a regular wind-down time.",
                frequency: "once on 2026-07-30",
                difficulty: "low",
                rationale: "A small routine action.",
                status: "proposed",
              },
            ],
          }),
        );
      }
      if (url.includes(`/plans/${scenario.planId}/feedback`)) {
        return Promise.resolve(
          response(
            {
              plan_id: scenario.planId,
              feedback: {
                feedback_id: "feedback-1",
                action_id: actionId,
                user_id: scenario.userId,
                response: "accepted",
                completion_ratio: null,
                reason_text: null,
                created_at: "2026-07-30T08:00:00Z",
              },
            },
            201,
          ),
        );
      }
      return Promise.resolve(
        response({ error: { code: "unexpected", message: "unexpected", request_id: "test" } }, 500),
      );
    };
    const service = new PrimaryJourneyService(
      new CarePathApiClient("http://carepath.test", fetcher),
      scenario,
    );

    await expect(service.loadHealth()).resolves.toMatchObject({ ok: true });
    await expect(service.importDemo()).resolves.toMatchObject({ ok: true });
    await expect(service.importContent("csv", "metric_type,value")).resolves.toMatchObject({
      ok: true,
    });
    await expect(service.importContent("json", '{"profile":{}}')).resolves.toMatchObject({
      ok: true,
    });
    await expect(service.loadProfile()).resolves.toMatchObject({ ok: true });
    await expect(service.loadTrend("sleep_duration")).resolves.toMatchObject({ ok: true });
    await expect(service.loadTrend("steps", 30)).resolves.toMatchObject({ ok: true });
    await expect(service.loadObservations("sleep_duration", 60)).resolves.toMatchObject({
      ok: true,
      data: { returned_count: 1 },
    });
    await expect(service.loadPatientEvidence()).resolves.toMatchObject({ ok: true });
    await expect(service.loadExternalEvidence("sleep routine")).resolves.toMatchObject({
      ok: true,
    });
    await expect(service.askQuestion(scenario.question)).resolves.toMatchObject({
      ok: true,
      data: { verification_disposition: "pass" },
    });
    await expect(service.loadPlan()).resolves.toMatchObject({ ok: true });
    await expect(
      service.submitFeedback(scenario.planId, actionId, "accepted"),
    ).resolves.toMatchObject({ ok: true });

    expect(calls.some((call) => call.url === "http://carepath.test/health")).toBe(true);
    const trendCalls = calls.filter((call) => call.url.includes("/records/trends?"));
    expect(new URL(trendCalls[0]?.url ?? "http://invalid").searchParams.get("days")).toBe("7");
    expect(new URL(trendCalls[1]?.url ?? "http://invalid").searchParams.get("days")).toBe("30");
    const observationCall = calls.find((call) => call.url.includes("/observations?"));
    const observationQuery = new URL(observationCall?.url ?? "http://invalid").searchParams;
    expect(observationQuery.get("start_at")).toBe("2026-05-30T00:00:00.000Z");
    expect(observationQuery.get("end_at")).toBe("2026-07-28T23:59:59.999Z");
    expect(calls.filter((call) => call.url.includes("/evidence/external/search?"))).toHaveLength(2);
  });

  test("rejects malformed or non-object JSON before transport", async () => {
    const scenario = buildDemoScenario();
    let calls = 0;
    const fetcher: ApiFetcher = () => {
      calls += 1;
      return Promise.resolve(response(importReport("json")));
    };
    const service = new PrimaryJourneyService(
      new CarePathApiClient("http://carepath.test", fetcher),
      scenario,
    );

    await expect(service.importContent("json", "{")).resolves.toMatchObject({
      ok: false,
      error: { code: "invalid_json" },
    });
    await expect(service.importContent("json", "[]")).resolves.toMatchObject({
      ok: false,
      error: { code: "invalid_json_package" },
    });
    await expect(service.importContent("json", "null")).resolves.toMatchObject({
      ok: false,
      error: { code: "invalid_json_package" },
    });
    await expect(service.importContent("json", '"text"')).resolves.toMatchObject({
      ok: false,
      error: { code: "invalid_json_package" },
    });
    expect(calls).toBe(0);
  });

  test("maps rejected and completed feedback to canonical ratios", async () => {
    const bodies: Record<string, unknown>[] = [];
    const scenario = buildDemoScenario();
    const fetcher: ApiFetcher = (_url, init) => {
      bodies.push(parseBody(init.body));
      return Promise.resolve(
        response({
          plan_id: scenario.planId,
          feedback: {
            feedback_id: "feedback",
            action_id: "action",
            user_id: scenario.userId,
            response: "accepted",
            completion_ratio: null,
            reason_text: null,
            created_at: "2026-07-30T08:00:00Z",
          },
        }),
      );
    };
    const service = new PrimaryJourneyService(
      new CarePathApiClient("http://carepath.test", fetcher),
      scenario,
    );

    await service.submitFeedback(scenario.planId, "action", "rejected");
    await service.submitFeedback(scenario.planId, "action", "completed");

    expect(bodies[0]).toMatchObject({
      response: "rejected",
      completion_ratio: 0,
      reason_text: "Not feasible for this demo week",
    });
    expect(bodies[1]).toMatchObject({
      response: "completed",
      completion_ratio: 1,
      reason_text: null,
    });
  });

  test("retains all four primary metrics", () => {
    expect(PRIMARY_METRICS).toEqual([
      "sleep_duration",
      "resting_heart_rate",
      "steps",
      "stress_score",
    ]);
  });
});

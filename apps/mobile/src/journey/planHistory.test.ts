import { describe, expect, test } from "@jest/globals";

import { CarePathApiClient, type ApiRequestInit, type ApiResponse } from "../api/client";
import type { InterventionPlan, PlanAction } from "./apiTypes";
import {
  comparePlanVersions,
  feedbackPayload,
  lighterAlternative,
  PlanHistoryApi,
  type PlanHistoryItem,
} from "./planHistory";

function action(overrides: Partial<PlanAction> = {}): PlanAction {
  return {
    action_id: "action-1",
    plan_id: "plan-1",
    domain: "physical_activity",
    description: "Walk for 20 minutes.",
    frequency: "once daily",
    difficulty: "high",
    rationale: "Build activity gradually.",
    status: "proposed",
    ...overrides,
  };
}

function plan(overrides: Partial<InterventionPlan> = {}): InterventionPlan {
  return {
    plan_id: "plan-1",
    user_id: "user-1",
    goal_id: "goal-1",
    version: 1,
    start_date: "2026-07-30",
    end_date: "2026-08-05",
    status: "active",
    generation_interaction_id: "interaction-1",
    supersedes_plan_id: null,
    ...overrides,
  };
}

function item(
  actions: PlanAction[] = [action()],
  overrides: Partial<InterventionPlan> = {},
): PlanHistoryItem {
  return { plan: plan(overrides), actions };
}

function response(payload: unknown, status = 200): ApiResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
  };
}

interface RecordedCall {
  url: string;
  init: ApiRequestInit;
}

describe("plan history feedback", () => {
  test("maps the full feedback loop to canonical ratios and reasons", () => {
    expect(feedbackPayload({ response: "accepted" })).toEqual({
      response: "accepted",
      completion_ratio: null,
      reason_text: null,
    });
    expect(feedbackPayload({ response: "accepted", reasonText: "   " })).toEqual({
      response: "accepted",
      completion_ratio: null,
      reason_text: null,
    });
    expect(feedbackPayload({ response: "rejected", reasonText: "Too difficult" })).toEqual({
      response: "rejected",
      completion_ratio: 0,
      reason_text: "Too difficult",
    });
    expect(feedbackPayload({ response: "modified", reasonText: "  shorter version  " })).toEqual({
      response: "modified",
      completion_ratio: 0.5,
      reason_text: "shorter version",
    });
    expect(feedbackPayload({ response: "partially_completed", completionRatio: 0.25 })).toEqual({
      response: "partially_completed",
      completion_ratio: 0.25,
      reason_text: null,
    });
    expect(feedbackPayload({ response: "completed" }).completion_ratio).toBe(1);
    expect(feedbackPayload({ response: "not_completed" }).completion_ratio).toBe(0);
  });

  test("builds a visibly easier alternative", () => {
    expect(lighterAlternative(action())).toContain("medium-effort");
    expect(lighterAlternative(action({ difficulty: "medium" }))).toContain("low-effort");
    expect(lighterAlternative(action({ difficulty: "low" }))).toContain("easiest safe part");
  });

  test("summarises differences between traceable plan versions", () => {
    const previous = item([action()], { status: "superseded" });
    const current = item(
      [
        action({
          action_id: "action-2",
          plan_id: "plan-2",
          description: "Walk for 8 minutes.",
          difficulty: "low",
          status: "accepted",
        }),
      ],
      { plan_id: "plan-2", version: 2 },
    );
    expect(comparePlanVersions(current, previous)).toEqual({
      difficultyChanges: 1,
      descriptionChanges: 1,
      statusChanges: 1,
    });
  });

  test("covers unchanged, absent and added actions across versions", () => {
    const previous = item([action()]);
    expect(comparePlanVersions(previous, undefined)).toEqual({
      difficultyChanges: 0,
      descriptionChanges: 0,
      statusChanges: 0,
    });
    expect(comparePlanVersions(previous, item([action()]))).toEqual({
      difficultyChanges: 0,
      descriptionChanges: 0,
      statusChanges: 0,
    });
    expect(comparePlanVersions(item([], { version: 2 }), previous)).toEqual({
      difficultyChanges: 0,
      descriptionChanges: 1,
      statusChanges: 0,
    });
    expect(
      comparePlanVersions(
        item([action(), action({ action_id: "action-2" })], { version: 2 }),
        previous,
      ),
    ).toEqual({
      difficultyChanges: 0,
      descriptionChanges: 1,
      statusChanges: 0,
    });
  });

  test("calls current, history and feedback endpoints with canonical parameters", async () => {
    const calls: RecordedCall[] = [];
    const current = { plan: plan(), actions: [action()] };
    const history = { items: [current], limit: 50, offset: 0, returned_count: 1 };
    const feedback = {
      plan_id: "plan-1",
      feedback: {
        feedback_id: "feedback-1",
        action_id: "action-1",
        user_id: "user-1",
        response: "modified",
        completion_ratio: 0.5,
        reason_text: "Use a shorter action.",
        created_at: "2026-08-01T08:00:00Z",
      },
    };
    const client = new CarePathApiClient("http://carepath.test", (url, init) => {
      calls.push({ url, init });
      if (url.includes("/plans/current?")) {
        return Promise.resolve(response(current));
      }
      if (url.includes("/plans/history?")) {
        return Promise.resolve(response(history));
      }
      return Promise.resolve(response(feedback, 201));
    });
    const api = new PlanHistoryApi(client, "user-1");

    await expect(api.loadCurrent()).resolves.toMatchObject({ ok: true, data: current });
    await expect(api.loadHistory()).resolves.toMatchObject({ ok: true, data: history });
    await expect(
      api.submitFeedback("plan-1", "action-1", {
        response: "modified",
        completionRatio: 0.5,
        reasonText: " Use a shorter action. ",
      }),
    ).resolves.toMatchObject({ ok: true, data: feedback });

    expect(calls[0]?.url).toBe("http://carepath.test/plans/current?user_id=user-1");
    expect(calls[1]?.url).toBe(
      "http://carepath.test/plans/history?user_id=user-1&limit=50&offset=0",
    );
    expect(calls[2]?.url).toBe("http://carepath.test/plans/plan-1/feedback");
    expect(JSON.parse(calls[2]?.init.body ?? "{}")).toEqual({
      user_id: "user-1",
      action_id: "action-1",
      response: "modified",
      completion_ratio: 0.5,
      reason_text: "Use a shorter action.",
    });
  });
});

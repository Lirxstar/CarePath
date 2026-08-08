import type { ApiResult, CarePathApiClient } from "../api/client";
import type {
  CurrentPlanResponse,
  InterventionPlan,
  PlanAction,
  PlanFeedbackResponse,
} from "./apiTypes";

export type PlanFeedbackKind =
  "accepted" | "rejected" | "modified" | "completed" | "partially_completed" | "not_completed";

export interface PlanHistoryItem {
  plan: InterventionPlan;
  actions: PlanAction[];
}

export interface PlanHistoryResponse {
  items: PlanHistoryItem[];
  limit: number;
  offset: number;
  returned_count: number;
}

export interface PlanFeedbackInput {
  response: PlanFeedbackKind;
  completionRatio?: number | null;
  reasonText?: string | null;
}

export interface PlanChangeSummary {
  difficultyChanges: number;
  descriptionChanges: number;
  statusChanges: number;
}

interface CanonicalFeedbackPayload {
  response: PlanFeedbackKind;
  completion_ratio: number | null;
  reason_text: string | null;
}

export function lighterAlternative(action: PlanAction): string {
  if (action.difficulty === "high") {
    return `Lighter option: do a shorter, medium-effort version of “${action.description}”.`;
  }
  if (action.difficulty === "medium") {
    return `Lighter option: do a brief, low-effort version of “${action.description}”.`;
  }
  return `Lighter option: do only the easiest safe part of “${action.description}” today.`;
}

export function feedbackPayload(input: PlanFeedbackInput): CanonicalFeedbackPayload {
  const completionRatio =
    input.completionRatio ??
    (input.response === "completed"
      ? 1
      : input.response === "rejected" || input.response === "not_completed"
        ? 0
        : input.response === "partially_completed" || input.response === "modified"
          ? 0.5
          : null);
  const reason = input.reasonText?.trim();
  let reasonText: string | null = null;
  if (reason !== undefined && reason.length > 0) {
    reasonText = reason;
  }
  return {
    response: input.response,
    completion_ratio: completionRatio,
    reason_text: reasonText,
  };
}

function stableHash(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function feedbackSubmissionKey(
  planId: string,
  actionId: string,
  payload: CanonicalFeedbackPayload,
): string {
  const canonical = JSON.stringify({
    planId,
    actionId,
    response: payload.response,
    completionRatio: payload.completion_ratio,
    reasonText: payload.reason_text,
  });
  const actionToken = actionId.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 40);
  return `mobile-${actionToken}-${stableHash(canonical)}`.slice(0, 64);
}

export function comparePlanVersions(
  current: PlanHistoryItem,
  previous: PlanHistoryItem | undefined,
): PlanChangeSummary {
  if (previous === undefined) {
    return { difficultyChanges: 0, descriptionChanges: 0, statusChanges: 0 };
  }

  let difficultyChanges = 0;
  let descriptionChanges = 0;
  let statusChanges = 0;
  const comparableLength = Math.max(current.actions.length, previous.actions.length);
  for (let index = 0; index < comparableLength; index += 1) {
    const action = current.actions[index];
    const prior = previous.actions[index];
    if (action === undefined || prior === undefined) {
      descriptionChanges += 1;
      continue;
    }
    if (prior.difficulty !== action.difficulty) {
      difficultyChanges += 1;
    }
    if (prior.description !== action.description) {
      descriptionChanges += 1;
    }
    if (prior.status !== action.status) {
      statusChanges += 1;
    }
  }
  return { difficultyChanges, descriptionChanges, statusChanges };
}

function difficultyRank(difficulty: PlanAction["difficulty"]): number {
  if (difficulty === "low") {
    return 0;
  }
  if (difficulty === "medium") {
    return 1;
  }
  return 2;
}

export function explainPlanChanges(
  current: PlanHistoryItem,
  previous: PlanHistoryItem | undefined,
): string[] {
  if (previous === undefined) {
    return ["Earliest retained plan version; there is no earlier version to compare."];
  }

  const explanations: string[] = [];
  const comparableLength = Math.max(current.actions.length, previous.actions.length);
  for (let index = 0; index < comparableLength; index += 1) {
    const action = current.actions[index];
    const prior = previous.actions[index];
    if (action === undefined || prior === undefined) {
      explanations.push("The number of retained actions changed between these plan versions.");
      continue;
    }
    if (prior.difficulty !== action.difficulty) {
      const direction =
        difficultyRank(action.difficulty) < difficultyRank(prior.difficulty)
          ? "reduced"
          : "increased";
      explanations.push(`Difficulty ${direction}: ${action.rationale}`);
    } else if (prior.description !== action.description) {
      explanations.push(
        `Action changed while difficulty stayed ${action.difficulty}: ${action.rationale}`,
      );
    }
    if (prior.status !== action.status) {
      explanations.push(
        `Action status changed from ${prior.status} to ${action.status} after recorded feedback.`,
      );
    }
  }

  return explanations.length > 0
    ? [...new Set(explanations)]
    : ["No material action, difficulty or feedback-status change from the previous version."];
}

export class PlanHistoryApi {
  private readonly pendingFeedback = new Map<string, Promise<ApiResult<PlanFeedbackResponse>>>();

  constructor(
    private readonly client: CarePathApiClient,
    private readonly userId: string,
  ) {}

  loadCurrent(): Promise<ApiResult<CurrentPlanResponse>> {
    const query = new URLSearchParams({ user_id: this.userId });
    return this.client.get<CurrentPlanResponse>(`/plans/current?${query.toString()}`);
  }

  loadHistory(): Promise<ApiResult<PlanHistoryResponse>> {
    const query = new URLSearchParams({ user_id: this.userId, limit: "50", offset: "0" });
    return this.client.get<PlanHistoryResponse>(`/plans/history?${query.toString()}`);
  }

  submitFeedback(
    planId: string,
    actionId: string,
    input: PlanFeedbackInput,
  ): Promise<ApiResult<PlanFeedbackResponse>> {
    const payload = feedbackPayload(input);
    const submissionKey = feedbackSubmissionKey(planId, actionId, payload);
    const existing = this.pendingFeedback.get(submissionKey);
    if (existing !== undefined) {
      return existing;
    }

    const request = this.client.post<PlanFeedbackResponse>(`/plans/${planId}/feedback`, {
      user_id: this.userId,
      action_id: actionId,
      submission_key: submissionKey,
      ...payload,
    });
    this.pendingFeedback.set(submissionKey, request);
    const cleanup = () => {
      if (this.pendingFeedback.get(submissionKey) === request) {
        this.pendingFeedback.delete(submissionKey);
      }
    };
    void request.then(cleanup, cleanup);
    return request;
  }
}

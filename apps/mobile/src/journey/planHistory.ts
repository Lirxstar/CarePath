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

export function lighterAlternative(action: PlanAction): string {
  if (action.difficulty === "high") {
    return `Lighter option: do a shorter, medium-effort version of “${action.description}”.`;
  }
  if (action.difficulty === "medium") {
    return `Lighter option: do a brief, low-effort version of “${action.description}”.`;
  }
  return `Lighter option: do only the easiest safe part of “${action.description}” today.`;
}

export function feedbackPayload(input: PlanFeedbackInput): {
  response: PlanFeedbackKind;
  completion_ratio: number | null;
  reason_text: string | null;
} {
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

export class PlanHistoryApi {
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
    return this.client.post<PlanFeedbackResponse>(`/plans/${planId}/feedback`, {
      user_id: this.userId,
      action_id: actionId,
      ...feedbackPayload(input),
    });
  }
}

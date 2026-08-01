import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import type { ApiLoadState } from "./api/client";
import { createRuntimeApiClient } from "./api/runtime";
import { useI18n } from "./i18n/I18nContext";
import type { CurrentPlanResponse, PlanAction, PlanFeedbackResponse } from "./journey/apiTypes";
import { useJourney } from "./journey/JourneyContext";
import {
  comparePlanVersions,
  feedbackPayload,
  lighterAlternative,
  PlanHistoryApi,
  type PlanFeedbackInput,
  type PlanHistoryItem,
  type PlanHistoryResponse,
} from "./journey/planHistory";

function Button({
  label,
  onPress,
  disabled = false,
  secondary = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary ? styles.secondaryButton : styles.primaryButton,
        disabled ? styles.disabled : null,
        pressed && !disabled ? styles.pressed : null,
      ]}
    >
      <Text style={secondary ? styles.secondaryButtonText : styles.primaryButtonText}>{label}</Text>
    </Pressable>
  );
}

function ErrorCard({
  state,
  retry,
}: {
  state: Extract<ApiLoadState<unknown>, { status: "error" }>;
  retry: () => void;
}) {
  const { strings } = useI18n();
  const offline = state.error.code === "network_error";
  return (
    <View accessibilityRole="alert" style={styles.errorCard}>
      <Text style={styles.cardTitle}>
        {offline ? strings.common.offline : strings.common.apiError}
      </Text>
      <Text style={styles.body}>{state.error.message}</Text>
      {state.error.requestId ? (
        <Text style={styles.meta}>Request {state.error.requestId}</Text>
      ) : null}
      <Button label={strings.common.retry} secondary onPress={retry} />
    </View>
  );
}

function mockHistory(scenario: ReturnType<typeof useJourney>["scenario"]): PlanHistoryResponse {
  const items: PlanHistoryItem[] = scenario.importContent.intervention_history.plans.map(
    (plan) => ({
      plan: { ...plan, supersedes_plan_id: null },
      actions: scenario.importContent.intervention_history.actions.filter(
        (action) => action.plan_id === plan.plan_id,
      ),
    }),
  );
  return { items, limit: 50, offset: 0, returned_count: items.length };
}

function updateActionStatus(
  actions: PlanAction[],
  actionId: string,
  response: PlanFeedbackInput["response"],
): PlanAction[] {
  return actions.map((item) =>
    item.action_id === actionId ? { ...item, status: response } : item,
  );
}

function ActionFeedbackCard({
  action,
  saving,
  submit,
}: {
  action: PlanAction;
  saving: boolean;
  submit: (input: PlanFeedbackInput) => void;
}) {
  const [reason, setReason] = useState("");
  const alternative = lighterAlternative(action);
  const reasonRequired = reason.trim().length === 0;

  return (
    <View style={styles.actionCard}>
      <View style={styles.rowBetween}>
        <Text style={styles.actionTitle}>{action.description}</Text>
        <Text accessibilityLabel={`Action status ${action.status}`} style={styles.statusChip}>
          {action.status}
        </Text>
      </View>
      <Text style={styles.body}>{action.rationale}</Text>
      <Text style={styles.meta}>
        {action.frequency} · difficulty {action.difficulty}
      </Text>
      <Text style={styles.alternative}>{alternative}</Text>
      <TextInput
        accessibilityLabel={`Reason for feedback on ${action.description}`}
        multiline
        onChangeText={setReason}
        placeholder="Reason, constraint or what made this difficult"
        style={styles.input}
        value={reason}
      />
      <View style={styles.buttonRow}>
        <Button
          label="Accept"
          secondary
          disabled={saving}
          onPress={() => {
            submit({ response: "accepted", reasonText: reason });
          }}
        />
        <Button
          label="Choose lighter option"
          secondary
          disabled={saving}
          onPress={() => {
            submit({
              response: "modified",
              completionRatio: 0.5,
              reasonText: `${alternative}${reason.trim() ? ` Reason: ${reason.trim()}` : ""}`,
            });
          }}
        />
        <Button
          label="Reject"
          secondary
          disabled={saving || reasonRequired}
          onPress={() => {
            submit({ response: "rejected", completionRatio: 0, reasonText: reason });
          }}
        />
        <Button
          label="Complete"
          disabled={saving}
          onPress={() => {
            submit({ response: "completed", completionRatio: 1, reasonText: reason });
          }}
        />
        <Button
          label="Partly done"
          secondary
          disabled={saving}
          onPress={() => {
            submit({
              response: "partially_completed",
              completionRatio: 0.5,
              reasonText: reason,
            });
          }}
        />
        <Button
          label="Not completed"
          secondary
          disabled={saving || reasonRequired}
          onPress={() => {
            submit({ response: "not_completed", completionRatio: 0, reasonText: reason });
          }}
        />
      </View>
      {reasonRequired ? (
        <Text style={styles.helper}>Add a reason before Reject or Not completed.</Text>
      ) : null}
    </View>
  );
}

function HistoryItem({
  item,
  previous,
}: {
  item: PlanHistoryItem;
  previous: PlanHistoryItem | undefined;
}) {
  const changes = comparePlanVersions(item, previous);
  return (
    <View style={styles.historyCard}>
      <View style={styles.rowBetween}>
        <Text style={styles.cardTitle}>Version {String(item.plan.version)}</Text>
        <Text style={styles.statusChip}>{item.plan.status}</Text>
      </View>
      <Text style={styles.body}>
        {item.plan.start_date} → {item.plan.end_date}
      </Text>
      <Text style={styles.meta}>Plan ID {item.plan.plan_id}</Text>
      {item.plan.supersedes_plan_id ? (
        <Text style={styles.meta}>Supersedes {item.plan.supersedes_plan_id}</Text>
      ) : null}
      {previous ? (
        <Text style={styles.helper}>
          Change from v{String(previous.plan.version)}: {String(changes.difficultyChanges)}{" "}
          difficulty, {String(changes.descriptionChanges)} action text,{" "}
          {String(changes.statusChanges)} status differences.
        </Text>
      ) : (
        <Text style={styles.helper}>Earliest retained plan version.</Text>
      )}
      <View style={styles.historyActions}>
        {item.actions.map((action) => (
          <View key={action.action_id} style={styles.historyActionRow}>
            <Text style={styles.body}>{action.description}</Text>
            <Text style={styles.meta}>
              {action.frequency} · {action.difficulty} · {action.status}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

export function PlanHistoryV08Screen() {
  const { scenario, mockMode, progress, refreshPlan } = useJourney();
  const { strings } = useI18n();
  const api = useMemo(
    () => new PlanHistoryApi(createRuntimeApiClient(), scenario.userId),
    [scenario.userId],
  );
  const [currentState, setCurrentState] = useState<ApiLoadState<CurrentPlanResponse>>({
    status: "idle",
  });
  const [historyState, setHistoryState] = useState<ApiLoadState<PlanHistoryResponse>>({
    status: "idle",
  });
  const [feedbackState, setFeedbackState] = useState<ApiLoadState<PlanFeedbackResponse>>({
    status: "idle",
  });

  const loadAll = useCallback(async () => {
    if (!progress.imported) {
      setCurrentState({ status: "idle" });
      setHistoryState({ status: "idle" });
      return;
    }
    setCurrentState({ status: "loading" });
    setHistoryState({ status: "loading" });
    if (mockMode) {
      const history = mockHistory(scenario);
      const first = history.items[0];
      if (first === undefined) {
        setCurrentState({
          status: "error",
          error: {
            code: "plan_not_found",
            message: "No demo plan is available.",
            requestId: null,
            status: 404,
          },
        });
      } else {
        setCurrentState({ status: "success", data: { plan: first.plan, actions: first.actions } });
      }
      setHistoryState({ status: "success", data: history });
      return;
    }
    const [current, history] = await Promise.all([api.loadCurrent(), api.loadHistory()]);
    setCurrentState(
      current.ok
        ? { status: "success", data: current.data }
        : { status: "error", error: current.error },
    );
    setHistoryState(
      history.ok
        ? { status: "success", data: history.data }
        : { status: "error", error: history.error },
    );
  }, [api, mockMode, progress.imported, scenario]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const submit = useCallback(
    async (action: PlanAction, input: PlanFeedbackInput) => {
      if (currentState.status !== "success") {
        return;
      }
      setFeedbackState({ status: "loading" });
      if (mockMode) {
        const normalized = feedbackPayload(input);
        const payload: PlanFeedbackResponse = {
          plan_id: currentState.data.plan.plan_id,
          feedback: {
            feedback_id: `mock-feedback-${action.action_id}`,
            action_id: action.action_id,
            user_id: scenario.userId,
            response: normalized.response,
            completion_ratio: normalized.completion_ratio,
            reason_text: normalized.reason_text,
            created_at: new Date().toISOString(),
          },
        };
        setFeedbackState({ status: "success", data: payload });
        setCurrentState({
          status: "success",
          data: {
            ...currentState.data,
            actions: updateActionStatus(
              currentState.data.actions,
              action.action_id,
              input.response,
            ),
          },
        });
        setHistoryState((state) => {
          if (state.status !== "success") {
            return state;
          }
          return {
            status: "success",
            data: {
              ...state.data,
              items: state.data.items.map((item) => ({
                ...item,
                actions: updateActionStatus(item.actions, action.action_id, input.response),
              })),
            },
          };
        });
        return;
      }
      const result = await api.submitFeedback(
        currentState.data.plan.plan_id,
        action.action_id,
        input,
      );
      setFeedbackState(
        result.ok
          ? { status: "success", data: result.data }
          : { status: "error", error: result.error },
      );
      if (result.ok) {
        await Promise.all([loadAll(), refreshPlan()]);
      }
    },
    [api, currentState, loadAll, mockMode, refreshPlan, scenario.userId],
  );

  const retry = useCallback(() => {
    void loadAll();
  }, [loadAll]);

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <View style={styles.header}>
        <Text style={styles.eyebrow}>Longitudinal adaptation</Text>
        <Text accessibilityRole="header" style={styles.title}>
          {strings.nav.planHistory}
        </Text>
        <Text style={styles.lead}>
          Review the active week, choose a lighter alternative when needed, record completion
          reasons, and trace how later plan versions change after feedback.
        </Text>
      </View>

      {!progress.imported ? (
        <View style={styles.emptyCard}>
          <Text style={styles.cardTitle}>No active demo data</Text>
          <Text style={styles.body}>Load a synthetic persona on Today or Health Data first.</Text>
        </View>
      ) : null}

      {currentState.status === "loading" || historyState.status === "loading" ? (
        <View accessibilityRole="progressbar" style={styles.loadingRow}>
          <ActivityIndicator />
          <Text style={styles.body}>{strings.common.loading}</Text>
        </View>
      ) : null}
      {currentState.status === "error" ? <ErrorCard state={currentState} retry={retry} /> : null}
      {historyState.status === "error" ? <ErrorCard state={historyState} retry={retry} /> : null}

      {feedbackState.status === "loading" ? (
        <View style={styles.loadingRow}>
          <ActivityIndicator />
          <Text style={styles.body}>Saving feedback…</Text>
        </View>
      ) : null}
      {feedbackState.status === "error" ? <ErrorCard state={feedbackState} retry={retry} /> : null}
      {feedbackState.status === "success" ? (
        <View accessibilityRole="summary" style={styles.successCard}>
          <Text style={styles.cardTitle}>Feedback saved</Text>
          <Text style={styles.body}>
            {feedbackState.data.feedback.response}
            {feedbackState.data.feedback.reason_text
              ? ` · ${feedbackState.data.feedback.reason_text}`
              : ""}
          </Text>
        </View>
      ) : null}

      {currentState.status === "success" ? (
        <View style={styles.section}>
          <View style={styles.rowBetween}>
            <View style={styles.flexText}>
              <Text style={styles.sectionTitle}>Current seven-day plan</Text>
              <Text style={styles.body}>
                Version {String(currentState.data.plan.version)} ·{" "}
                {currentState.data.plan.start_date} → {currentState.data.plan.end_date}
              </Text>
            </View>
            <Button label={strings.common.refresh} secondary onPress={retry} />
          </View>
          {currentState.data.actions.length === 0 ? (
            <Text style={styles.body}>{strings.common.empty}</Text>
          ) : (
            currentState.data.actions.map((action) => (
              <ActionFeedbackCard
                key={action.action_id}
                action={action}
                saving={feedbackState.status === "loading"}
                submit={(input) => void submit(action, input)}
              />
            ))
          )}
        </View>
      ) : null}

      {historyState.status === "success" ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Plan history and changes</Text>
          <Text style={styles.lead}>
            Versions are returned by the backend with stable plan IDs and supersession links. Action
            status changes remain traceable after feedback.
          </Text>
          {historyState.data.items.length === 0 ? (
            <Text style={styles.body}>{strings.common.empty}</Text>
          ) : (
            historyState.data.items.map((item, index) => (
              <HistoryItem
                key={item.plan.plan_id}
                item={item}
                previous={historyState.data.items[index + 1]}
              />
            ))
          )}
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingTop: 28,
    paddingBottom: 48,
    gap: 18,
    backgroundColor: "#F4F7F8",
  },
  header: { width: "100%", maxWidth: 1040, alignSelf: "center", gap: 8 },
  eyebrow: { fontSize: 12, fontWeight: "700", color: "#285C5C", textTransform: "uppercase" },
  title: { fontSize: 34, lineHeight: 40, fontWeight: "700", color: "#102A2A" },
  lead: { fontSize: 15, lineHeight: 23, color: "#526666", maxWidth: 840, flexShrink: 1 },
  section: { width: "100%", maxWidth: 1040, alignSelf: "center", gap: 12 },
  sectionTitle: { fontSize: 21, lineHeight: 28, fontWeight: "700", color: "#102A2A" },
  cardTitle: {
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "700",
    color: "#173B3B",
    flexShrink: 1,
  },
  actionTitle: {
    fontSize: 16,
    lineHeight: 23,
    fontWeight: "700",
    color: "#173B3B",
    flex: 1,
    minWidth: 200,
  },
  body: { fontSize: 14, lineHeight: 21, color: "#304C4C", flexShrink: 1 },
  meta: { fontSize: 11, lineHeight: 17, color: "#6A7D7D", flexShrink: 1 },
  helper: { fontSize: 12, lineHeight: 18, color: "#637777", flexShrink: 1 },
  alternative: { fontSize: 13, lineHeight: 20, color: "#285C5C", flexShrink: 1 },
  actionCard: {
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    padding: 18,
    gap: 9,
    borderWidth: 1,
    borderColor: "#DCE5E5",
  },
  historyCard: {
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    padding: 18,
    gap: 8,
    borderWidth: 1,
    borderColor: "#DCE5E5",
  },
  emptyCard: {
    width: "100%",
    maxWidth: 1040,
    alignSelf: "center",
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    padding: 18,
    gap: 6,
    borderWidth: 1,
    borderColor: "#DCE5E5",
  },
  successCard: {
    width: "100%",
    maxWidth: 1040,
    alignSelf: "center",
    borderRadius: 14,
    padding: 14,
    gap: 5,
    backgroundColor: "#EEF3F3",
    borderWidth: 1,
    borderColor: "#C9DADA",
  },
  errorCard: {
    width: "100%",
    maxWidth: 1040,
    alignSelf: "center",
    borderRadius: 14,
    padding: 14,
    gap: 8,
    backgroundColor: "#F5F7F7",
    borderWidth: 1,
    borderColor: "#8AA4A4",
  },
  loadingRow: {
    width: "100%",
    maxWidth: 1040,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    minHeight: 44,
  },
  rowBetween: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 10,
  },
  flexText: { flex: 1, minWidth: 220, gap: 4 },
  buttonRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  button: {
    minHeight: 44,
    minWidth: 44,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryButton: { backgroundColor: "#285C5C" },
  secondaryButton: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#8AA4A4" },
  primaryButtonText: { color: "#FFFFFF", fontSize: 13, fontWeight: "700" },
  secondaryButtonText: { color: "#285C5C", fontSize: 13, fontWeight: "700" },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.75 },
  statusChip: {
    fontSize: 11,
    fontWeight: "700",
    color: "#365858",
    backgroundColor: "#E5EEEE",
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 999,
    overflow: "hidden",
  },
  input: {
    minHeight: 72,
    borderWidth: 1,
    borderColor: "#B8CACA",
    borderRadius: 12,
    padding: 12,
    fontSize: 14,
    lineHeight: 21,
    color: "#173B3B",
    backgroundColor: "#FFFFFF",
    textAlignVertical: "top",
  },
  historyActions: { gap: 8, marginTop: 4 },
  historyActionRow: {
    borderTopWidth: 1,
    borderTopColor: "#E2E9E9",
    paddingTop: 8,
    gap: 3,
  },
});

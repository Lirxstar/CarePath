import { useCallback, type ReactNode } from "react";
import { useFocusEffect, useIsFocused } from "@react-navigation/native";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { ControlledApiError } from "./api/client";
import { PlanHistoryV08Screen } from "./PlanHistoryV08Screen";
import { CoachScreen, HealthDataScreen, TodayScreen } from "./screens";
import { useI18n } from "./i18n/I18nContext";
import { SUPPORTED_LOCALES } from "./i18n/resources";
import { PRIMARY_METRICS } from "./journey/service";
import { useJourney } from "./journey/JourneyContext";

interface StateLike {
  status: string;
  error?: ControlledApiError;
}

function firstError(states: StateLike[]): ControlledApiError | null {
  return states.find((state) => state.status === "error")?.error ?? null;
}

function LanguageSafetyChrome() {
  const { locale, setLocale, strings } = useI18n();
  return (
    <View style={styles.chrome}>
      <View accessibilityRole="radiogroup" style={styles.languageRow}>
        <Text style={styles.chromeLabel}>{strings.common.language}</Text>
        {SUPPORTED_LOCALES.map((candidate) => (
          <Pressable
            key={candidate}
            accessibilityRole="radio"
            accessibilityLabel={`Use ${candidate} interface safety text`}
            accessibilityState={{ checked: candidate === locale }}
            onPress={() => {
              setLocale(candidate);
            }}
            style={[styles.localeButton, candidate === locale ? styles.localeButtonSelected : null]}
          >
            <Text style={styles.localeButtonText}>{candidate.toUpperCase()}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.safetyCopy}>
        <Text style={styles.safetyTitle}>{strings.safety.title}</Text>
        <Text style={styles.safetyBody}>{strings.safety.body}</Text>
      </View>
    </View>
  );
}

function RouteFrame({
  error,
  retry,
  children,
}: {
  error: ControlledApiError | null;
  retry: () => void;
  children: ReactNode;
}) {
  const { strings } = useI18n();
  return (
    <View style={styles.route}>
      <LanguageSafetyChrome />
      {error ? (
        <View accessibilityRole="alert" style={styles.statusBanner}>
          <View style={styles.statusText}>
            <Text style={styles.statusTitle}>
              {error.code === "network_error" ? strings.common.offline : strings.common.apiError}
            </Text>
            <Text style={styles.statusBody}>{error.message}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={strings.common.retry}
            onPress={retry}
            style={styles.retryButton}
          >
            <Text style={styles.retryText}>{strings.common.retry}</Text>
          </Pressable>
        </View>
      ) : null}
      <View style={styles.content}>{children}</View>
    </View>
  );
}

export function TodayRoute() {
  const journey = useJourney();
  useFocusEffect(
    useCallback(() => {
      if (journey.progress.imported) {
        void Promise.all([journey.refreshHealthStatus(), journey.refreshDashboard()]);
      }
    }, [journey.progress.imported, journey.refreshDashboard, journey.refreshHealthStatus]),
  );
  const trendStates = PRIMARY_METRICS.flatMap((metric) => [
    journey.recent7States[metric],
    journey.baseline30States[metric],
  ]);
  const error = firstError([
    journey.healthState,
    journey.profileState,
    journey.planState,
    journey.importState,
    ...trendStates,
  ]);
  return (
    <RouteFrame
      error={error}
      retry={() => {
        if (journey.progress.imported) {
          void Promise.all([journey.refreshHealthStatus(), journey.refreshDashboard()]);
          return;
        }
        void journey.refreshHealthStatus();
      }}
    >
      <TodayScreen />
    </RouteFrame>
  );
}

export function CoachRoute() {
  const journey = useJourney();
  const error = firstError([journey.coachState]);
  return (
    <RouteFrame error={error} retry={() => void journey.askQuestion()}>
      <CoachScreen />
    </RouteFrame>
  );
}

export function HealthDataRoute() {
  const journey = useJourney();
  const error = firstError([
    journey.importState,
    journey.customImportState,
    ...PRIMARY_METRICS.map((metric) => journey.seriesStates[metric]),
  ]);
  return (
    <RouteFrame error={error} retry={() => void journey.refreshHealthData()}>
      <HealthDataScreen />
    </RouteFrame>
  );
}

export function PlanHistoryRoute() {
  const focused = useIsFocused();
  return (
    <RouteFrame error={null} retry={() => undefined}>
      {focused ? <PlanHistoryV08Screen key="focused-plan-history" /> : null}
    </RouteFrame>
  );
}

const styles = StyleSheet.create({
  route: { flex: 1, backgroundColor: "#F4F7F8" },
  content: { flex: 1, minHeight: 0 },
  chrome: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#DCE5E5",
    backgroundColor: "#FFFFFF",
    gap: 6,
  },
  languageRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 },
  chromeLabel: { fontSize: 12, fontWeight: "700", color: "#526666" },
  localeButton: {
    minWidth: 44,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#A9BBBB",
    backgroundColor: "#FFFFFF",
  },
  localeButtonSelected: { backgroundColor: "#DDEAEA", borderColor: "#527979" },
  localeButtonText: { fontSize: 12, fontWeight: "700", color: "#173B3B" },
  safetyCopy: { flexDirection: "row", flexWrap: "wrap", gap: 6, alignItems: "baseline" },
  safetyTitle: { fontSize: 12, fontWeight: "700", color: "#304C4C" },
  safetyBody: { fontSize: 11, lineHeight: 17, color: "#637777", flex: 1, minWidth: 240 },
  statusBanner: {
    marginHorizontal: 16,
    marginTop: 8,
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#8AA4A4",
    backgroundColor: "#F5F7F7",
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 10,
  },
  statusText: { flex: 1, minWidth: 220 },
  statusTitle: { fontSize: 13, fontWeight: "700", color: "#314A4A" },
  statusBody: { fontSize: 12, lineHeight: 18, color: "#526666" },
  retryButton: {
    minWidth: 44,
    minHeight: 44,
    paddingHorizontal: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#8AA4A4",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF",
  },
  retryText: { fontSize: 13, fontWeight: "700", color: "#285C5C" },
});

import { useState, type PropsWithChildren } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import type { ApiLoadState, ControlledApiError } from "./api/client";
import type {
  ExternalEvidenceHit,
  ImportIssue,
  ImportReport,
  ObservationPage,
  PatientEvidenceItem,
  RecordTrendsResponse,
  ResponseStatement,
} from "./journey/apiTypes";
import { useJourney } from "./journey/JourneyContext";
import { formatReliability } from "./journey/reliability";
import {
  HEALTH_RANGES,
  PRIMARY_METRICS,
  type HealthRange,
  type ImportFormat,
  type PrimaryMetric,
} from "./journey/service";

interface ScreenShellProps extends PropsWithChildren {
  title: string;
  eyebrow: string;
  description: string;
}

interface ActionButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}

const METRIC_LABELS: Record<PrimaryMetric, string> = {
  sleep_duration: "Sleep duration",
  resting_heart_rate: "Resting heart rate",
  steps: "Daily steps",
  stress_score: "Stress score",
};

const METRIC_SHORT_LABELS: Record<PrimaryMetric, string> = {
  sleep_duration: "Sleep",
  resting_heart_rate: "Resting HR",
  steps: "Steps",
  stress_score: "Stress",
};

function ScreenShell({ title, eyebrow, description, children }: ScreenShellProps) {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>{eyebrow}</Text>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.description}>{description}</Text>
        </View>
        <View style={styles.prototypeBadge}>
          <Text style={styles.prototypeBadgeText}>Research prototype</Text>
        </View>
      </View>
      <View style={styles.content}>{children}</View>
      <View style={styles.safetyNote}>
        <Text style={styles.safetyTitle}>Behaviour support, not medical care</Text>
        <Text style={styles.safetyText}>
          CarePath does not diagnose conditions or change medication. Demo personas and built-in
          records are synthetic. Data-quality labels describe the records, not a medical state.
        </Text>
      </View>
    </ScrollView>
  );
}

function ActionButton({ label, onPress, disabled = false, secondary = false }: ActionButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary ? styles.buttonSecondary : styles.buttonPrimary,
        disabled ? styles.buttonDisabled : null,
        pressed && !disabled ? styles.buttonPressed : null,
      ]}
    >
      <Text style={secondary ? styles.buttonSecondaryText : styles.buttonPrimaryText}>{label}</Text>
    </Pressable>
  );
}

function ChoiceButton({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={[styles.choiceButton, selected ? styles.choiceButtonSelected : null]}
    >
      <Text style={[styles.choiceButtonText, selected ? styles.choiceButtonTextSelected : null]}>
        {label}
      </Text>
    </Pressable>
  );
}

function ErrorPanel({ error }: { error: ControlledApiError }) {
  return (
    <View style={styles.errorPanel}>
      <Text style={styles.errorTitle}>{error.code}</Text>
      <Text style={styles.errorText}>{error.message}</Text>
      {error.requestId ? <Text style={styles.metaText}>Request {error.requestId}</Text> : null}
    </View>
  );
}

function LoadingLine({ label }: { label: string }) {
  return (
    <View style={styles.loadingRow}>
      <ActivityIndicator />
      <Text style={styles.cardText}>{label}</Text>
    </View>
  );
}

function formatValue(value: number | null, unit: string | null): string {
  if (value === null) {
    return "Not enough data";
  }
  const rounded = Math.round(value * 10) / 10;
  return `${String(rounded)}${unit ? ` ${unit}` : ""}`;
}

function formatPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "Comparison unavailable";
  }
  const rounded = Math.round(value * 10) / 10;
  const prefix = rounded > 0 ? "+" : "";
  return `${prefix}${String(rounded)}%`;
}

function apiComparison(current: number | null, baseline: number | null): number | null {
  if (current === null || baseline === null || baseline === 0) {
    return null;
  }
  return ((current - baseline) / Math.abs(baseline)) * 100;
}

function PersonaSelector() {
  const { scenarios, scenario, selectPersona, importState } = useJourney();
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Built-in demo persona</Text>
      <Text style={styles.cardText}>
        Switching persona resets this app journey so records cannot be accidentally mixed.
      </Text>
      <View style={styles.choiceRow}>
        {scenarios.map((item) => (
          <ChoiceButton
            key={item.key}
            label={item.displayName}
            selected={item.key === scenario.key}
            onPress={() => {
              selectPersona(item.key);
            }}
          />
        ))}
      </View>
      <Text style={styles.helperText}>{scenario.description}</Text>
      {importState.status === "success" ? (
        <Text style={styles.metaText}>Current persona data package is loaded.</Text>
      ) : null}
    </View>
  );
}

function ConnectionCard() {
  const { healthState, refreshHealthStatus, mockMode } = useJourney();
  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <View style={styles.flexOne}>
          <Text style={styles.cardTitle}>API connection</Text>
          {healthState.status === "loading" ? <LoadingLine label="Checking /health…" /> : null}
          {healthState.status === "idle" ? (
            <Text style={styles.mutedText}>Connection has not been checked.</Text>
          ) : null}
          {healthState.status === "success" ? (
            <Text style={styles.cardText}>
              Connected · {healthState.data.provider ?? healthState.data.status ?? "ready"}
              {mockMode ? " · frontend mock mode" : ""}
            </Text>
          ) : null}
          {healthState.status === "error" ? <ErrorPanel error={healthState.error} /> : null}
        </View>
        <ActionButton label="Check" secondary onPress={() => void refreshHealthStatus()} />
      </View>
    </View>
  );
}

function DashboardMetric({
  metric,
  recent,
  baseline,
}: {
  metric: PrimaryMetric;
  recent: ApiLoadState<RecordTrendsResponse>;
  baseline: ApiLoadState<RecordTrendsResponse>;
}) {
  if (recent.status === "loading" || baseline.status === "loading") {
    return (
      <View style={styles.metricCard}>
        <LoadingLine label={`Loading ${METRIC_SHORT_LABELS[metric]}…`} />
      </View>
    );
  }
  if (recent.status === "error") {
    return (
      <View style={styles.metricCard}>
        <Text style={styles.cardTitle}>{METRIC_LABELS[metric]}</Text>
        <ErrorPanel error={recent.error} />
      </View>
    );
  }
  if (baseline.status === "error") {
    return (
      <View style={styles.metricCard}>
        <Text style={styles.cardTitle}>{METRIC_LABELS[metric]}</Text>
        <ErrorPanel error={baseline.error} />
      </View>
    );
  }
  if (recent.status !== "success" || baseline.status !== "success") {
    return (
      <View style={styles.metricCard}>
        <Text style={styles.cardTitle}>{METRIC_LABELS[metric]}</Text>
        <Text style={styles.mutedText}>Load a demo persona to calculate this summary.</Text>
      </View>
    );
  }

  const recentMean = recent.data.trend.mean;
  const baselineMean = baseline.data.trend.mean;
  const comparison = apiComparison(recentMean, baselineMean);
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{METRIC_LABELS[metric]}</Text>
      <Text style={styles.metricValue}>{formatValue(recentMean, recent.data.trend.unit)}</Text>
      <Text style={styles.changeText}>
        {formatPercent(comparison)} vs 30-day mean{" "}
        {formatValue(baselineMean, baseline.data.trend.unit)}
      </Text>
      <Text style={styles.metaText}>
        7d {recent.data.trend.start_date} → {recent.data.trend.end_date}
      </Text>
      <Text style={styles.metaText}>
        Coverage {String(Math.round(recent.data.trend.coverage * 100))}% · reliability{" "}
        {formatReliability(recent.data.trend.reliability)}
      </Text>
      {recent.data.trend.warnings.map((warning) => (
        <Text key={warning} style={styles.helperText}>
          Data note: {warning.replaceAll("_", " ")}
        </Text>
      ))}
    </View>
  );
}

function ImportIssueList({ title, issues }: { title: string; issues: ImportIssue[] }) {
  if (issues.length === 0) {
    return null;
  }
  return (
    <View style={styles.issueGroup}>
      <Text style={styles.cardTitle}>
        {title} · {String(issues.length)}
      </Text>
      {issues.map((issue, index) => (
        <Text key={`${issue.code}-${String(index)}`} style={styles.cardText}>
          {issue.code}: {issue.message}
          {issue.record_index === null ? "" : ` · record ${String(issue.record_index)}`}
        </Text>
      ))}
    </View>
  );
}

function ImportReportPanel({ report }: { report: ImportReport }) {
  return (
    <View style={styles.reportPanel}>
      <Text style={styles.cardTitle}>Import validation report · {report.status}</Text>
      <Text style={styles.cardText}>
        {String(report.received_records)} received · {String(report.inserted_records)} persisted ·{" "}
        {report.source_format.toUpperCase()}
      </Text>
      <Text style={styles.metaText}>Imported {report.imported_at}</Text>
      <ImportIssueList title="Fixed issues" issues={report.fixed_issues} />
      <ImportIssueList title="Skipped records" issues={report.skipped_records} />
      <ImportIssueList title="Blocking errors" issues={report.blocking_errors} />
      {report.fixed_issues.length === 0 &&
      report.skipped_records.length === 0 &&
      report.blocking_errors.length === 0 ? (
        <Text style={styles.helperText}>No validation findings were reported.</Text>
      ) : null}
    </View>
  );
}

function rawChartDays(endDate: string, days: HealthRange): string[] {
  const end = new Date(`${endDate}T00:00:00Z`);
  return Array.from({ length: days }, (_unused, index) => {
    const current = new Date(end);
    current.setUTCDate(end.getUTCDate() - (days - 1 - index));
    return current.toISOString().slice(0, 10);
  });
}

function RawMetricChart({
  metric,
  state,
  days,
  endDate,
}: {
  metric: PrimaryMetric;
  state: ApiLoadState<ObservationPage>;
  days: HealthRange;
  endDate: string;
}) {
  if (state.status === "loading") {
    return (
      <LoadingLine label={`Loading ${String(days)} days of ${METRIC_SHORT_LABELS[metric]}…`} />
    );
  }
  if (state.status === "error") {
    return <ErrorPanel error={state.error} />;
  }
  if (state.status !== "success") {
    return <Text style={styles.mutedText}>Load demo data to view the raw series.</Text>;
  }

  const dates = rawChartDays(endDate, days);
  const byDate = new Map(
    state.data.items.map((item) => [item.observed_at.slice(0, 10), item] as const),
  );
  const numeric = state.data.items
    .map((item) => item.value_numeric)
    .filter((value): value is number => value !== null);
  const minimum = numeric.length > 0 ? Math.min(...numeric) : 0;
  const maximum = numeric.length > 0 ? Math.max(...numeric) : 1;
  const span = maximum - minimum || 1;
  const unit = state.data.items.find((item) => item.unit !== null)?.unit ?? "unit";
  const covered = dates.filter((date) => byDate.has(date)).length;
  const missing = dates.length - covered;

  return (
    <View style={styles.chartCard}>
      <View style={styles.rowBetween}>
        <View>
          <Text style={styles.cardTitle}>{METRIC_LABELS[metric]}</Text>
          <Text style={styles.metaText}>
            {String(days)} days · {unit} · {String(covered)} observed · {String(missing)} missing
          </Text>
        </View>
        <Text style={styles.statusChip}>
          {String(Math.round((covered / days) * 100))}% coverage
        </Text>
      </View>
      {numeric.length === 0 ? (
        <Text style={styles.mutedText}>No numeric observations are available in this range.</Text>
      ) : (
        <ScrollView
          horizontal
          contentContainerStyle={styles.chartRow}
          showsHorizontalScrollIndicator
        >
          {dates.map((date) => {
            const item = byDate.get(date);
            if (item?.value_numeric === null || item === undefined) {
              return (
                <View key={date} style={styles.chartSlot}>
                  <View style={styles.missingMark} />
                  <Text style={styles.chartDate}>{date.slice(5)}</Text>
                </View>
              );
            }
            const height = 20 + ((item.value_numeric - minimum) / span) * 82;
            return (
              <View key={date} style={styles.chartSlot}>
                <Text style={styles.chartValue}>
                  {String(Math.round(item.value_numeric * 10) / 10)}
                </Text>
                <View
                  accessibilityLabel={`${date} ${String(item.value_numeric)} ${unit}${item.quality_flag === "suspect" ? " suspect quality" : ""}`}
                  style={[
                    styles.rawBar,
                    { height },
                    item.quality_flag === "suspect" ? styles.suspectBar : null,
                  ]}
                />
                <Text style={styles.chartDate}>{date.slice(5)}</Text>
                {item.quality_flag === "suspect" ? (
                  <Text style={styles.suspectText}>check</Text>
                ) : null}
              </View>
            );
          })}
        </ScrollView>
      )}
      <Text style={styles.helperText}>
        Each mark is one raw daily observation. Missing days remain gaps; suspect records remain
        visible and are not smoothed away.
      </Text>
    </View>
  );
}

function StatementList({ items }: { items: ResponseStatement[] }) {
  if (items.length === 0) {
    return <Text style={styles.mutedText}>No statement was returned for this section.</Text>;
  }
  return (
    <View style={styles.stackSmall}>
      {items.map((item) => (
        <View key={item.statement_id} style={styles.statementRow}>
          <Text style={styles.cardText}>{item.text}</Text>
          {item.citation_ids.length > 0 ? (
            <Text style={styles.metaText}>Citations: {item.citation_ids.join(", ")}</Text>
          ) : null}
        </View>
      ))}
    </View>
  );
}

function PatientEvidenceCard({ item }: { item: PatientEvidenceItem }) {
  return (
    <View style={styles.evidenceCard}>
      <Text style={styles.cardTitle}>{item.kind.replaceAll("_", " ")}</Text>
      <Text style={styles.cardText}>{item.fact}</Text>
      <Text style={styles.metaText}>
        {item.start_date ?? "date unavailable"}
        {item.end_date && item.end_date !== item.start_date ? ` → ${item.end_date}` : ""} ·
        reliability {item.reliability.level}
      </Text>
      <Text style={styles.metaText}>Evidence ID: {item.evidence_id}</Text>
      {item.source_record_ids.length > 0 ? (
        <Text style={styles.metaText}>Record IDs: {item.source_record_ids.join(", ")}</Text>
      ) : null}
    </View>
  );
}

function ExternalEvidenceCard({ item }: { item: ExternalEvidenceHit }) {
  const [expanded, setExpanded] = useState(false);
  const sourceDate =
    item.metadata.updated_at ?? item.metadata.published_at ?? item.metadata.retrieved_at;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => {
        setExpanded((value) => !value);
      }}
      style={styles.evidenceCard}
    >
      <Text style={styles.cardTitle}>{item.citation}</Text>
      <Text style={styles.cardText}>
        {item.metadata.organisation} · {sourceDate}
      </Text>
      <Text style={styles.metaText}>
        Chunk {item.chunk_id} · score {String(Math.round(item.score * 1000) / 1000)}
      </Text>
      <Text style={styles.linkText}>{expanded ? "Hide exact chunk" : "Show exact chunk"}</Text>
      {expanded ? (
        <View style={styles.chunkPanel}>
          <Text style={styles.cardText}>{item.content}</Text>
          <Text style={styles.metaText}>Source ID: {item.metadata.source_id}</Text>
          <Text style={styles.metaText}>URL: {item.metadata.canonical_url}</Text>
          <Text style={styles.metaText}>Retrieved: {item.metadata.retrieved_at}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

function CoachProgress({ status }: { status: ApiLoadState<unknown>["status"] }) {
  const labels = [
    "Check safety",
    "Analyse recent trends",
    "Retrieve evidence",
    "Compose verified plan",
  ];
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Bounded Agent workflow</Text>
      <Text style={styles.helperText}>
        Only stage status is shown. Internal reasoning and raw chain-of-thought are never exposed.
      </Text>
      {labels.map((label) => (
        <View key={label} style={styles.progressRow}>
          {status === "loading" ? <ActivityIndicator size="small" /> : null}
          <Text style={styles.cardText}>
            {status === "success" ? "✓" : status === "error" ? "○" : "•"} {label}
          </Text>
        </View>
      ))}
    </View>
  );
}

export function TodayScreen() {
  const {
    scenario,
    profileState,
    recent7States,
    baseline30States,
    planState,
    importDemo,
    refreshDashboard,
    importState,
    progress,
  } = useJourney();
  const priorityAction = planState.status === "success" ? planState.data.actions[0] : undefined;

  return (
    <ScreenShell
      eyebrow="Today dashboard"
      title="Today"
      description="A neutral 7-day health-behaviour summary, a 30-day baseline and today's current plan action."
    >
      <ConnectionCard />
      <PersonaSelector />

      <View style={styles.heroCard}>
        <View style={styles.rowBetween}>
          <View style={styles.flexOne}>
            <Text style={styles.eyebrow}>Selected demo user</Text>
            <Text style={styles.heroTitle}>{scenario.displayName}</Text>
            <Text style={styles.cardText}>{scenario.goalLabel}</Text>
            {profileState.status === "success" ? (
              <Text style={styles.metaText}>
                API goals: {profileState.data.health_goals.join(", ")} · timezone{" "}
                {profileState.data.timezone}
              </Text>
            ) : null}
          </View>
          <View style={styles.buttonColumn}>
            <ActionButton
              label={progress.imported ? "Demo loaded" : "Load demo"}
              disabled={importState.status === "loading" || progress.imported}
              onPress={() => void importDemo()}
            />
            <ActionButton
              label="Refresh dashboard"
              secondary
              disabled={!progress.imported}
              onPress={() => void refreshDashboard()}
            />
          </View>
        </View>
        {importState.status === "loading" ? (
          <LoadingLine label="Validating synthetic records…" />
        ) : null}
        {importState.status === "error" ? <ErrorPanel error={importState.error} /> : null}
        {profileState.status === "error" ? <ErrorPanel error={profileState.error} /> : null}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Recent 7 days vs 30-day baseline</Text>
        <Text style={styles.sectionLead}>
          Values, units, date windows, coverage and reliability are returned by the API. Differences
          are descriptive, not diagnostic.
        </Text>
        <View style={styles.metricGrid}>
          {PRIMARY_METRICS.map((metric) => (
            <DashboardMetric
              key={metric}
              metric={metric}
              recent={recent7States[metric]}
              baseline={baseline30States[metric]}
            />
          ))}
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Today's action</Text>
        {planState.status === "loading" ? <LoadingLine label="Loading the current plan…" /> : null}
        {planState.status === "error" ? <ErrorPanel error={planState.error} /> : null}
        {priorityAction ? (
          <>
            <Text style={styles.actionTitle}>{priorityAction.description}</Text>
            <Text style={styles.cardText}>{priorityAction.rationale}</Text>
            <Text style={styles.metaText}>
              {priorityAction.frequency} · {priorityAction.difficulty}
            </Text>
          </>
        ) : planState.status !== "loading" && planState.status !== "error" ? (
          <Text style={styles.mutedText}>No current action is available yet.</Text>
        ) : null}
      </View>

      <View style={styles.noticeCard}>
        <Text style={styles.cardTitle}>Data and safety notes</Text>
        <Text style={styles.cardText}>
          "Not enough data", coverage and reliability labels indicate data sufficiency only.
          CarePath does not use dashboard colour to label a person as healthy or unhealthy.
        </Text>
      </View>
    </ScreenShell>
  );
}

export function HealthDataScreen() {
  const {
    scenario,
    importState,
    customImportState,
    importDemo,
    importCustom,
    seriesStates,
    healthRange,
    refreshHealthData,
    progress,
  } = useJourney();
  const [metric, setMetric] = useState<PrimaryMetric>("sleep_duration");
  const [format, setFormat] = useState<ImportFormat>("csv");
  const [importText, setImportText] = useState("");

  return (
    <ScreenShell
      eyebrow="Longitudinal records"
      title="Health Data"
      description="Inspect unsmoothed 7/30/60-day observations, data coverage and auditable CSV/JSON import reports."
    >
      <PersonaSelector />

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Built-in synthetic package</Text>
        <Text style={styles.cardText}>
          60 days across sleep, resting heart rate, steps and stress. The package contains
          structured missing periods and explicit suspect observations so the chart cannot hide
          them.
        </Text>
        <ActionButton
          label={progress.imported ? "Synthetic package loaded" : "Import selected persona"}
          disabled={importState.status === "loading" || progress.imported}
          onPress={() => void importDemo()}
        />
        {importState.status === "loading" ? (
          <LoadingLine label="Validating and importing…" />
        ) : null}
        {importState.status === "error" ? <ErrorPanel error={importState.error} /> : null}
        {importState.status === "success" ? <ImportReportPanel report={importState.data} /> : null}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>CSV / JSON import</Text>
        <Text style={styles.cardText}>
          Paste a standard CarePath CSV or project JSON package. The backend performs the same
          validation used by the API import endpoint and returns explicit repair, skip and blocking
          findings.
        </Text>
        <View style={styles.choiceRow}>
          <ChoiceButton
            label="CSV"
            selected={format === "csv"}
            onPress={() => {
              setFormat("csv");
            }}
          />
          <ChoiceButton
            label="JSON"
            selected={format === "json"}
            onPress={() => {
              setFormat("json");
            }}
          />
        </View>
        <TextInput
          accessibilityLabel={`${format.toUpperCase()} import content`}
          multiline
          onChangeText={setImportText}
          placeholder={
            format === "csv"
              ? "observation_id,user_id,metric_type,value_numeric,unit,observed_at,..."
              : '{"profile": {...}, "observations": [...]}'
          }
          style={styles.importInput}
          value={importText}
        />
        <ActionButton
          label={`Validate and import ${format.toUpperCase()}`}
          disabled={customImportState.status === "loading"}
          onPress={() => void importCustom(format, importText)}
        />
        {customImportState.status === "loading" ? <LoadingLine label="Checking import…" /> : null}
        {customImportState.status === "error" ? (
          <ErrorPanel error={customImportState.error} />
        ) : null}
        {customImportState.status === "success" ? (
          <ImportReportPanel report={customImportState.data} />
        ) : null}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Raw longitudinal chart</Text>
        <Text style={styles.sectionLead}>
          Choose one metric and time range. No interpolation is applied between missing days.
        </Text>
        <View style={styles.choiceRow}>
          {PRIMARY_METRICS.map((item) => (
            <ChoiceButton
              key={item}
              label={METRIC_SHORT_LABELS[item]}
              selected={item === metric}
              onPress={() => {
                setMetric(item);
              }}
            />
          ))}
        </View>
        <View style={styles.choiceRow}>
          {HEALTH_RANGES.map((days) => (
            <ChoiceButton
              key={days}
              label={`${String(days)} days`}
              selected={days === healthRange}
              onPress={() => void refreshHealthData(days)}
            />
          ))}
        </View>
        {!progress.imported ? (
          <Text style={styles.mutedText}>Import a persona before requesting raw observations.</Text>
        ) : null}
        <RawMetricChart
          metric={metric}
          state={seriesStates[metric]}
          days={healthRange}
          endDate={scenario.endDate}
        />
      </View>
    </ScreenShell>
  );
}

export function CoachScreen() {
  const {
    question,
    setQuestion,
    askQuestion,
    coachState,
    patientEvidenceState,
    externalEvidenceState,
    progress,
  } = useJourney();
  const structured = coachState.status === "success" ? coachState.data.structured_response : null;

  return (
    <ScreenShell
      eyebrow="Evidence-grounded coach"
      title="Coach"
      description="Ask a health-behaviour question, inspect the bounded workflow and expand the exact evidence used around the answer."
    >
      <PersonaSelector />
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Ask CarePath</Text>
        <TextInput
          accessibilityLabel="Health behaviour coaching question"
          multiline
          onChangeText={setQuestion}
          placeholder="Ask about recent changes and a realistic plan"
          style={styles.input}
          value={question}
        />
        <ActionButton
          label="Analyse and answer"
          disabled={!progress.imported || coachState.status === "loading" || !question.trim()}
          onPress={() => void askQuestion()}
        />
        {!progress.imported ? (
          <Text style={styles.helperText}>Load the selected synthetic persona first.</Text>
        ) : null}
        {coachState.status === "error" ? <ErrorPanel error={coachState.error} /> : null}
      </View>

      <CoachProgress status={coachState.status} />

      {structured ? (
        <>
          <View style={styles.card}>
            <View style={styles.statusRow}>
              <Text style={styles.statusChip}>Safety: {structured.risk_level}</Text>
              <Text style={styles.statusChip}>
                Verifier:{" "}
                {coachState.status === "success"
                  ? (coachState.data.verification_disposition ?? "not reported")
                  : "pending"}
              </Text>
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>What I noticed</Text>
            <StatementList items={structured.what_i_noticed} />
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>What the evidence suggests</Text>
            <StatementList items={structured.what_the_evidence_suggests} />
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>A realistic plan for this week</Text>
            {structured.realistic_plan_for_this_week.length === 0 ? (
              <Text style={styles.mutedText}>No ordinary action plan was returned.</Text>
            ) : (
              structured.realistic_plan_for_this_week.map((action) => (
                <View key={action.action_id} style={styles.actionCard}>
                  <Text style={styles.actionTitle}>{action.scheduled_date}</Text>
                  <Text style={styles.cardText}>{action.description}</Text>
                  <Text style={styles.cardText}>{action.rationale}</Text>
                  <Text style={styles.metaText}>
                    {action.frequency} · {action.difficulty}
                  </Text>
                  {action.citation_ids.length > 0 ? (
                    <Text style={styles.metaText}>Citations: {action.citation_ids.join(", ")}</Text>
                  ) : null}
                </View>
              ))
            )}
          </View>

          <View style={styles.noticeCard}>
            <Text style={styles.sectionTitle}>When to seek professional help</Text>
            {structured.when_to_seek_professional_help.map((item, index) => (
              <Text key={`${item}-${String(index)}`} style={styles.cardText}>
                • {item}
              </Text>
            ))}
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>What I am uncertain about</Text>
            {structured.what_i_am_uncertain_about.map((item, index) => (
              <Text key={`${item}-${String(index)}`} style={styles.cardText}>
                • {item}
              </Text>
            ))}
          </View>
        </>
      ) : coachState.status === "idle" ? (
        <Text style={styles.mutedText}>No coaching answer has been requested yet.</Text>
      ) : null}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Patient Evidence</Text>
        <Text style={styles.sectionLead}>
          User-scoped measurements, tool facts and user-reported context remain separate from
          general guidance.
        </Text>
        {patientEvidenceState.status === "loading" ? (
          <LoadingLine label="Retrieving Patient Evidence…" />
        ) : null}
        {patientEvidenceState.status === "error" ? (
          <ErrorPanel error={patientEvidenceState.error} />
        ) : null}
        {patientEvidenceState.status === "success" &&
        patientEvidenceState.data.items.length === 0 ? (
          <Text style={styles.mutedText}>No Patient Evidence matched this bounded window.</Text>
        ) : null}
        {patientEvidenceState.status === "success"
          ? patientEvidenceState.data.items.map((item) => (
              <PatientEvidenceCard key={item.evidence_id} item={item} />
            ))
          : null}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>External Evidence</Text>
        <Text style={styles.sectionLead}>
          Expand a result to inspect the exact guideline chunk, organisation, source date and
          retrieval date.
        </Text>
        {externalEvidenceState.status === "loading" ? (
          <LoadingLine label="Retrieving guideline evidence…" />
        ) : null}
        {externalEvidenceState.status === "error" ? (
          <ErrorPanel error={externalEvidenceState.error} />
        ) : null}
        {externalEvidenceState.status === "success" && externalEvidenceState.data.length === 0 ? (
          <Text style={styles.mutedText}>No external guideline chunk matched this question.</Text>
        ) : null}
        {externalEvidenceState.status === "success"
          ? externalEvidenceState.data.map((item) => (
              <ExternalEvidenceCard key={item.chunk_id} item={item} />
            ))
          : null}
      </View>

      {structured && structured.sources.length > 0 ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Final response citation map</Text>
          {structured.sources.map((source) => (
            <View key={source.citation_id} style={styles.evidenceCard}>
              <Text style={styles.cardTitle}>{source.display_citation ?? source.citation_id}</Text>
              <Text style={styles.cardText}>{source.source_type.replaceAll("_", " ")}</Text>
              <Text style={styles.metaText}>Evidence ID: {source.evidence_id}</Text>
              {source.chunk_id ? (
                <Text style={styles.metaText}>Chunk ID: {source.chunk_id}</Text>
              ) : null}
              {source.source_ids.length > 0 ? (
                <Text style={styles.metaText}>
                  Record/source IDs: {source.source_ids.join(", ")}
                </Text>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}
    </ScreenShell>
  );
}

export function PlanHistoryScreen() {
  const { planState, feedbackState, progress, refreshPlan, submitFeedback } = useJourney();

  return (
    <ScreenShell
      eyebrow="Actions and feedback"
      title="Plan & History"
      description="Review the active seven-day plan and record accept, reject or completion feedback."
    >
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <Text style={styles.cardTitle}>Current plan</Text>
          <ActionButton
            label="Refresh"
            secondary
            disabled={!progress.imported || planState.status === "loading"}
            onPress={() => void refreshPlan()}
          />
        </View>
        {planState.status === "loading" ? <LoadingLine label="Loading current plan…" /> : null}
        {planState.status === "error" ? <ErrorPanel error={planState.error} /> : null}
        {planState.status === "idle" ? (
          <Text style={styles.mutedText}>Load a synthetic demo to create the reviewer plan.</Text>
        ) : null}
        {planState.status === "success" ? (
          <Text style={styles.cardText}>
            Version {String(planState.data.plan.version)} · {planState.data.plan.start_date} →{" "}
            {planState.data.plan.end_date}
          </Text>
        ) : null}
      </View>

      {feedbackState.status === "loading" ? <LoadingLine label="Saving feedback…" /> : null}
      {feedbackState.status === "error" ? <ErrorPanel error={feedbackState.error} /> : null}
      {feedbackState.status === "success" ? (
        <View style={styles.reportPanel}>
          <Text style={styles.cardText}>
            Feedback recorded: {feedbackState.data.feedback.response}.
          </Text>
        </View>
      ) : null}

      {planState.status === "success" ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Seven-day actions</Text>
          {planState.data.actions.map((action, index) => (
            <View key={action.action_id} style={styles.actionCard}>
              <View style={styles.rowBetween}>
                <Text style={styles.actionIndex}>Day {String(index + 1)}</Text>
                <Text style={styles.statusChip}>{action.status}</Text>
              </View>
              <Text style={styles.actionTitle}>{action.description}</Text>
              <Text style={styles.cardText}>{action.rationale}</Text>
              <Text style={styles.metaText}>
                {action.frequency} · {action.difficulty}
              </Text>
              <View style={styles.feedbackRow}>
                <ActionButton
                  label="Accept"
                  secondary
                  onPress={() => void submitFeedback(action.action_id, "accepted")}
                />
                <ActionButton
                  label="Reject"
                  secondary
                  onPress={() => void submitFeedback(action.action_id, "rejected")}
                />
                <ActionButton
                  label="Complete"
                  onPress={() => void submitFeedback(action.action_id, "completed")}
                />
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  page: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingTop: 40,
    paddingBottom: 40,
    backgroundColor: "#F4F7F8",
  },
  headerRow: {
    width: "100%",
    maxWidth: 1040,
    alignSelf: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    gap: 20,
  },
  headerCopy: { flex: 1, minWidth: 260 },
  content: { width: "100%", maxWidth: 1040, alignSelf: "center", gap: 18, marginTop: 24 },
  eyebrow: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase",
    color: "#285C5C",
  },
  title: { marginTop: 8, fontSize: 34, lineHeight: 40, fontWeight: "700", color: "#102A2A" },
  description: { marginTop: 10, maxWidth: 760, fontSize: 16, lineHeight: 24, color: "#526666" },
  prototypeBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: "#E2ECEC",
  },
  prototypeBadgeText: { color: "#285C5C", fontSize: 12, fontWeight: "700" },
  card: {
    borderRadius: 18,
    backgroundColor: "#FFFFFF",
    padding: 18,
    gap: 10,
    borderWidth: 1,
    borderColor: "#DCE5E5",
  },
  heroCard: {
    borderRadius: 22,
    backgroundColor: "#FFFFFF",
    padding: 22,
    gap: 14,
    borderWidth: 1,
    borderColor: "#C9DADA",
  },
  metricCard: {
    flexGrow: 1,
    flexBasis: 220,
    minWidth: 210,
    borderRadius: 18,
    backgroundColor: "#FFFFFF",
    padding: 18,
    gap: 7,
    borderWidth: 1,
    borderColor: "#DCE5E5",
  },
  chartCard: {
    borderRadius: 18,
    backgroundColor: "#FFFFFF",
    padding: 18,
    gap: 14,
    borderWidth: 1,
    borderColor: "#DCE5E5",
  },
  evidenceCard: {
    borderRadius: 14,
    backgroundColor: "#FFFFFF",
    padding: 16,
    gap: 7,
    borderWidth: 1,
    borderColor: "#DCE5E5",
    marginTop: 8,
  },
  actionCard: {
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    padding: 18,
    gap: 8,
    borderWidth: 1,
    borderColor: "#DCE5E5",
    marginTop: 10,
  },
  noticeCard: {
    borderRadius: 18,
    backgroundColor: "#EEF3F3",
    padding: 18,
    gap: 8,
    borderWidth: 1,
    borderColor: "#C9DADA",
  },
  reportPanel: {
    marginTop: 8,
    borderRadius: 14,
    padding: 14,
    gap: 8,
    backgroundColor: "#F6F9F9",
    borderWidth: 1,
    borderColor: "#DCE5E5",
  },
  issueGroup: { marginTop: 8, gap: 4 },
  section: { gap: 10 },
  sectionTitle: { fontSize: 20, lineHeight: 26, fontWeight: "700", color: "#102A2A" },
  sectionLead: { fontSize: 14, lineHeight: 21, color: "#526666", maxWidth: 820 },
  cardTitle: { fontSize: 15, lineHeight: 21, fontWeight: "700", color: "#173B3B" },
  cardText: { fontSize: 14, lineHeight: 21, color: "#304C4C" },
  mutedText: { fontSize: 14, lineHeight: 21, color: "#6A7D7D" },
  helperText: { fontSize: 12, lineHeight: 18, color: "#637777" },
  metaText: { fontSize: 11, lineHeight: 17, color: "#6A7D7D" },
  linkText: { fontSize: 13, fontWeight: "700", color: "#285C5C" },
  heroTitle: { fontSize: 26, lineHeight: 32, fontWeight: "700", color: "#102A2A" },
  metricLabel: { fontSize: 12, fontWeight: "700", color: "#526666", textTransform: "uppercase" },
  metricValue: { fontSize: 25, fontWeight: "700", color: "#102A2A" },
  changeText: { fontSize: 13, lineHeight: 18, color: "#304C4C" },
  actionTitle: { fontSize: 16, lineHeight: 22, fontWeight: "700", color: "#173B3B" },
  actionIndex: { fontSize: 12, fontWeight: "700", color: "#285C5C" },
  rowBetween: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  flexOne: { flex: 1, minWidth: 220 },
  buttonColumn: { gap: 8, alignItems: "stretch" },
  choiceRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  button: {
    minHeight: 42,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonPrimary: { backgroundColor: "#285C5C" },
  buttonSecondary: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#8AA4A4" },
  buttonDisabled: { opacity: 0.45 },
  buttonPressed: { opacity: 0.75 },
  buttonPrimaryText: { color: "#FFFFFF", fontSize: 13, fontWeight: "700" },
  buttonSecondaryText: { color: "#285C5C", fontSize: 13, fontWeight: "700" },
  choiceButton: {
    paddingHorizontal: 13,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#A9BBBB",
    backgroundColor: "#FFFFFF",
  },
  choiceButtonSelected: { backgroundColor: "#DDEAEA", borderColor: "#527979" },
  choiceButtonText: { fontSize: 12, fontWeight: "600", color: "#526666" },
  choiceButtonTextSelected: { color: "#173B3B" },
  loadingRow: { flexDirection: "row", alignItems: "center", gap: 9, paddingVertical: 5 },
  errorPanel: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#A9BBBB",
    padding: 12,
    backgroundColor: "#F5F7F7",
    gap: 4,
  },
  errorTitle: { fontSize: 13, fontWeight: "700", color: "#314A4A" },
  errorText: { fontSize: 13, lineHeight: 19, color: "#526666" },
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
  statusRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  feedbackRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 5 },
  input: {
    minHeight: 112,
    borderWidth: 1,
    borderColor: "#B8CACA",
    borderRadius: 12,
    padding: 12,
    fontSize: 15,
    lineHeight: 21,
    color: "#173B3B",
    backgroundColor: "#FFFFFF",
    textAlignVertical: "top",
  },
  importInput: {
    minHeight: 150,
    borderWidth: 1,
    borderColor: "#B8CACA",
    borderRadius: 12,
    padding: 12,
    fontSize: 13,
    lineHeight: 19,
    color: "#173B3B",
    backgroundColor: "#FBFCFC",
    textAlignVertical: "top",
  },
  chartRow: { minHeight: 155, alignItems: "flex-end", paddingTop: 20, paddingBottom: 4, gap: 5 },
  chartSlot: { width: 34, alignItems: "center", justifyContent: "flex-end", minHeight: 140 },
  rawBar: { width: 20, minHeight: 20, borderRadius: 5, backgroundColor: "#709494" },
  suspectBar: { borderWidth: 2, borderColor: "#304C4C", backgroundColor: "#B2C5C5" },
  missingMark: {
    width: 20,
    height: 4,
    marginBottom: 48,
    borderRadius: 2,
    backgroundColor: "#C6D2D2",
  },
  chartValue: { fontSize: 9, color: "#526666", marginBottom: 3 },
  chartDate: { fontSize: 9, color: "#6A7D7D", marginTop: 4, transform: [{ rotate: "-55deg" }] },
  suspectText: { fontSize: 8, fontWeight: "700", color: "#304C4C", marginTop: 2 },
  chunkPanel: { marginTop: 6, gap: 6, padding: 12, borderRadius: 10, backgroundColor: "#F5F8F8" },
  statementRow: { gap: 4, paddingVertical: 5 },
  stackSmall: { gap: 5 },
  progressRow: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 26 },
  safetyNote: {
    width: "100%",
    maxWidth: 1040,
    alignSelf: "center",
    marginTop: 24,
    paddingTop: 18,
    borderTopWidth: 1,
    borderTopColor: "#C9DADA",
    gap: 4,
  },
  safetyTitle: { fontSize: 13, fontWeight: "700", color: "#304C4C" },
  safetyText: { fontSize: 12, lineHeight: 18, color: "#637777", maxWidth: 800 },
});

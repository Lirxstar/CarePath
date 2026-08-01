export interface DemoObservation {
  observation_id: string;
  user_id: string;
  metric_type: string;
  value_numeric: number;
  unit: string;
  observed_at: string;
  source_type: "synthetic_wearable";
  quality_flag: "valid" | "suspect";
  confidence: number;
  metadata: { scenario: string; anomaly?: boolean };
}

export interface DemoPlanAction {
  action_id: string;
  plan_id: string;
  domain: "sleep" | "physical_activity" | "stress_mood";
  description: string;
  frequency: string;
  difficulty: "low";
  rationale: string;
  status: "proposed";
}

export interface DemoPlan {
  plan_id: string;
  user_id: string;
  goal_id: string;
  version: number;
  start_date: string;
  end_date: string;
  status: "active";
  generation_interaction_id: string;
}

export interface DemoImportContent {
  profile: Record<string, unknown>;
  observations: DemoObservation[];
  journal_entries: Record<string, unknown>[];
  goals: Record<string, unknown>[];
  intervention_history: {
    plans: DemoPlan[];
    actions: DemoPlanAction[];
    plan_feedback: never[];
  };
}

export type DemoPersonaKey = "irregular-sleep" | "sedentary-remote";

export interface DemoScenario {
  key: DemoPersonaKey;
  displayName: string;
  description: string;
  goalLabel: string;
  userId: string;
  goalId: string;
  planId: string;
  endDate: string;
  question: string;
  importContent: DemoImportContent;
}

interface PersonaDefinition {
  key: DemoPersonaKey;
  displayName: string;
  description: string;
  ageBand: "18-29" | "30-44";
  goalLabel: string;
  question: string;
  recentShift: {
    sleep: number;
    heartRate: number;
    steps: number;
    stress: number;
  };
  baseline: {
    sleep: number;
    heartRate: number;
    steps: number;
    stress: number;
  };
  actions: readonly string[];
}

const PERSONAS = [
  {
    key: "irregular-sleep",
    displayName: "Maya Chen",
    description: "Graduate student with a recent sleep and workload disruption.",
    ageBand: "18-29",
    goalLabel: "Restore a regular evening routine while keeping activity manageable.",
    question: "I have felt more tired recently. What changed, and what is realistic this week?",
    baseline: { sleep: 7.6, heartRate: 61, steps: 7900, stress: 4.1 },
    recentShift: { sleep: -1.25, heartRate: 5.5, steps: -1900, stress: 2.1 },
    actions: [
      "Start winding down at the same time tonight.",
      "Take a 10-minute easy walk after dinner.",
      "Protect a 30-minute screen-free period before bed.",
      "Take a short movement break during the workday.",
      "Write down tomorrow's top three tasks before winding down.",
      "Repeat the 10-minute easy walk after dinner.",
      "Review which small routine felt easiest to keep.",
    ],
  },
  {
    key: "sedentary-remote",
    displayName: "Jordan Lee",
    description: "Remote worker with stable sleep but a recent drop in daily movement.",
    ageBand: "30-44",
    goalLabel: "Rebuild regular movement breaks without making the workday harder.",
    question: "My activity has dropped while working from home. What changed and what can I try?",
    baseline: { sleep: 7.15, heartRate: 64, steps: 6900, stress: 5.0 },
    recentShift: { sleep: 0.05, heartRate: 1.5, steps: -2800, stress: 0.7 },
    actions: [
      "Take a five-minute movement break after the first work block.",
      "Walk for 10 minutes after lunch.",
      "Stand and stretch once during the afternoon.",
      "Place the next movement break on the calendar before work starts.",
      "Take a short walk before the final work block.",
      "Repeat the easiest movement break from earlier in the week.",
      "Review which cue made movement easiest to remember.",
    ],
  },
] as const satisfies readonly PersonaDefinition[];

function hex(length: number): string {
  return Array.from({ length }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}

function demoUuid(): string {
  return `${hex(8)}-${hex(4)}-4${hex(3)}-8${hex(3)}-${hex(12)}`;
}

function isoDate(offset: number): string {
  const date = new Date(Date.UTC(2026, 4, 30 + offset));
  return date.toISOString().slice(0, 10);
}

function rounded(value: number, digits = 1): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function observations(userId: string, persona: PersonaDefinition): DemoObservation[] {
  const records: DemoObservation[] = [];
  for (let index = 0; index < 60; index += 1) {
    const recent = index >= 53;
    const weekdayWave = (index % 7) - 3;
    const timestamp = `${isoDate(index)}T08:00:00+00:00`;
    const values = {
      sleep: persona.baseline.sleep + weekdayWave * 0.04 + (recent ? persona.recentShift.sleep : 0),
      heartRate:
        persona.baseline.heartRate +
        weekdayWave * 0.12 +
        (recent ? persona.recentShift.heartRate : 0),
      steps: persona.baseline.steps + weekdayWave * 110 + (recent ? persona.recentShift.steps : 0),
      stress:
        persona.baseline.stress - weekdayWave * 0.05 + (recent ? persona.recentShift.stress : 0),
    };
    const metrics = [
      ["sleep_duration", rounded(values.sleep), "hours"],
      ["resting_heart_rate", rounded(values.heartRate), "bpm"],
      ["steps", Math.round(values.steps), "steps"],
      ["stress_score", rounded(values.stress), "score_1_10"],
    ] as const;

    for (const [metricType, baseValue, unit] of metrics) {
      const structuredMissing =
        (metricType === "sleep_duration" && index >= 31 && index <= 33) ||
        (metricType === "steps" && index === 46) ||
        (persona.key === "sedentary-remote" && metricType === "stress_score" && index === 55);
      if (structuredMissing) {
        continue;
      }
      const anomaly =
        (persona.key === "irregular-sleep" && metricType === "sleep_duration" && index === 56) ||
        (persona.key === "sedentary-remote" && metricType === "steps" && index === 48);
      const anomalyValue =
        metricType === "sleep_duration" ? 4.4 : metricType === "steps" ? 14800 : baseValue;
      records.push({
        observation_id: demoUuid(),
        user_id: userId,
        metric_type: metricType,
        value_numeric: anomaly ? anomalyValue : baseValue,
        unit,
        observed_at: timestamp,
        source_type: "synthetic_wearable",
        quality_flag: anomaly ? "suspect" : "valid",
        confidence: anomaly ? 0.65 : 1,
        metadata: anomaly
          ? { scenario: `mobile-${persona.key}`, anomaly: true }
          : { scenario: `mobile-${persona.key}` },
      });
    }
  }
  return records;
}

function buildScenario(persona: PersonaDefinition): DemoScenario {
  const userId = demoUuid();
  const goalId = demoUuid();
  const planId = demoUuid();
  const generationInteractionId = demoUuid();
  const actionDates = [
    "2026-07-30",
    "2026-07-31",
    "2026-08-01",
    "2026-08-02",
    "2026-08-03",
    "2026-08-04",
    "2026-08-05",
  ] as const;
  const actions: DemoPlanAction[] = persona.actions.map((description, index) => ({
    action_id: demoUuid(),
    plan_id: planId,
    domain:
      persona.key === "sedentary-remote"
        ? "physical_activity"
        : index === 1 || index === 3 || index === 5
          ? "physical_activity"
          : "sleep",
    description,
    frequency: `once on ${String(actionDates[index])}`,
    difficulty: "low",
    rationale:
      "A deliberately small behaviour-support action grounded in the selected synthetic demo context.",
    status: "proposed",
  }));

  return {
    key: persona.key,
    displayName: persona.displayName,
    description: persona.description,
    goalLabel: persona.goalLabel,
    userId,
    goalId,
    planId,
    endDate: "2026-07-28",
    question: persona.question,
    importContent: {
      profile: {
        user_id: userId,
        age_band: persona.ageBand,
        preferred_language: "en",
        timezone: "Asia/Tokyo",
        schedule_constraints: { workdays: "09:00-18:00" },
        health_goals: ["sleep", "physical_activity", "stress_mood"],
        activity_constraints: [],
        coaching_preferences: { plan_size: "small", tone: "practical" },
        consent_flags: { synthetic_demo: true },
      },
      observations: observations(userId, persona),
      journal_entries: [
        {
          entry_id: demoUuid(),
          user_id: userId,
          created_at: "2026-07-27T20:00:00+09:00",
          text:
            persona.key === "irregular-sleep"
              ? "Workload has been heavier and my bedtime has moved around this week."
              : "Remote work has kept me at my desk for long blocks and I am moving less.",
          language: "en",
          user_tags:
            persona.key === "irregular-sleep" ? ["workload", "sleep"] : ["remote-work", "activity"],
        },
      ],
      goals: [
        {
          goal_id: goalId,
          user_id: userId,
          domain: persona.key === "sedentary-remote" ? "physical_activity" : "sleep",
          description: persona.goalLabel,
          status: "active",
          created_at: "2026-07-30T08:00:00+09:00",
        },
      ],
      intervention_history: {
        plans: [
          {
            plan_id: planId,
            user_id: userId,
            goal_id: goalId,
            version: 1,
            start_date: "2026-07-30",
            end_date: "2026-08-05",
            status: "active",
            generation_interaction_id: generationInteractionId,
          },
        ],
        actions,
        plan_feedback: [],
      },
    },
  };
}

export function buildDemoScenarios(): DemoScenario[] {
  return PERSONAS.map(buildScenario);
}

export function buildDemoScenario(): DemoScenario {
  return buildScenario(PERSONAS[0]);
}

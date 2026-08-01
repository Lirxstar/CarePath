import { describe, expect, test } from "@jest/globals";

import { buildDemoScenario, buildDemoScenarios } from "./demoScenario";

describe("mobile demo scenarios", () => {
  test("builds two distinct 60-day personas with explicit missingness and raw anomalies", () => {
    const scenarios = buildDemoScenarios();
    expect(scenarios).toHaveLength(2);

    const irregular = scenarios[0];
    const sedentary = scenarios[1];
    expect(irregular?.key).toBe("irregular-sleep");
    expect(sedentary?.key).toBe("sedentary-remote");
    expect(irregular?.displayName).not.toBe(sedentary?.displayName);
    expect(irregular?.question).not.toBe(sedentary?.question);

    const irregularObservations = irregular?.importContent.observations ?? [];
    const sedentaryObservations = sedentary?.importContent.observations ?? [];
    expect(irregularObservations).toHaveLength(236);
    expect(sedentaryObservations).toHaveLength(235);

    expect(irregularObservations[0]?.observed_at.slice(0, 10)).toBe("2026-05-30");
    expect(irregularObservations.at(-1)?.observed_at.slice(0, 10)).toBe("2026-07-28");

    const irregularSleep = irregularObservations.filter(
      (item) => item.metric_type === "sleep_duration",
    );
    expect(irregularSleep).toHaveLength(57);
    expect(irregularSleep.some((item) => item.value_numeric === 4.4)).toBe(true);
    expect(irregularSleep.some((item) => item.quality_flag === "suspect")).toBe(true);

    const sedentaryStress = sedentaryObservations.filter(
      (item) => item.metric_type === "stress_score",
    );
    expect(sedentaryStress).toHaveLength(59);
    const sedentarySteps = sedentaryObservations.filter((item) => item.metric_type === "steps");
    expect(sedentarySteps.some((item) => item.value_numeric === 14800)).toBe(true);

    expect(irregular?.importContent.intervention_history.actions).toHaveLength(7);
    expect(sedentary?.importContent.intervention_history.actions).toHaveLength(7);
    expect(irregular?.importContent.intervention_history.actions[0]?.description).not.toBe(
      sedentary?.importContent.intervention_history.actions[0]?.description,
    );
  });

  test("keeps the original primary-scenario helper on the irregular-sleep persona", () => {
    const scenario = buildDemoScenario();
    expect(scenario.key).toBe("irregular-sleep");
    expect(scenario.endDate).toBe("2026-07-28");
    expect(scenario.importContent.profile).toMatchObject({
      user_id: scenario.userId,
      timezone: "Asia/Tokyo",
    });
  });
});

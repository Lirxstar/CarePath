import { buildDemoScenario } from "./demoScenario";
import { buildCustomScenario, extractCustomImportSubject } from "./customImport";

describe("custom import subject adoption", () => {
  test("extracts user and latest observation date from JSON", () => {
    const subject = extractCustomImportSubject(
      "json",
      JSON.stringify({
        profile: { user_id: "11111111-1111-4111-8111-111111111111" },
        observations: [
          { observed_at: "2026-08-01T08:00:00Z" },
          { observed_at: "2026-08-07T08:00:00Z" },
        ],
      }),
    );

    expect(subject).toEqual({
      userId: "11111111-1111-4111-8111-111111111111",
      endDate: "2026-08-07",
    });
  });

  test("extracts user and latest observation date from standard CSV", () => {
    const subject = extractCustomImportSubject(
      "csv",
      [
        "observation_id,user_id,metric_type,value_numeric,unit,observed_at",
        "a,22222222-2222-4222-8222-222222222222,steps,5000,steps,2026-08-02T08:00:00Z",
        "b,22222222-2222-4222-8222-222222222222,steps,6500,steps,2026-08-08T08:00:00Z",
      ].join("\n"),
    );

    expect(subject).toEqual({
      userId: "22222222-2222-4222-8222-222222222222",
      endDate: "2026-08-08",
    });
  });

  test("builds a reviewer-facing scenario using imported subject identifiers", () => {
    const base = buildDemoScenario();
    const scenario = buildCustomScenario(
      "json",
      JSON.stringify({
        profile: { user_id: "33333333-3333-4333-8333-333333333333" },
        observations: [{ observed_at: "2026-08-08T10:00:00+09:00" }],
      }),
      base,
    );

    expect(scenario?.userId).toBe("33333333-3333-4333-8333-333333333333");
    expect(scenario?.endDate).toBe("2026-08-08");
    expect(scenario?.displayName).toBe("Your imported data");
  });

  test("rejects imports that cannot identify a user and observation window", () => {
    expect(extractCustomImportSubject("json", JSON.stringify({ observations: [] }))).toBeNull();
    expect(extractCustomImportSubject("csv", "metric_type,value_numeric\nsteps,5000")).toBeNull();
  });
});

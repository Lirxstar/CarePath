import { describe, expect, test } from "@jest/globals";

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

  test("falls back to an observation user and ignores unusable JSON observation entries", () => {
    const subject = extractCustomImportSubject(
      "json",
      JSON.stringify({
        profile: null,
        observations: [
          null,
          {
            user_id: "44444444-4444-4444-8444-444444444444",
            observed_at: null,
          },
          { observed_at: "not-a-date" },
          { observed_at: "2026-08-06T08:00:00Z" },
        ],
      }),
    );

    expect(subject).toEqual({
      userId: "44444444-4444-4444-8444-444444444444",
      endDate: "2026-08-06",
    });
  });

  test("rejects malformed and non-object JSON roots", () => {
    expect(extractCustomImportSubject("json", "{")) .toBeNull();
    expect(extractCustomImportSubject("json", "42")).toBeNull();
    expect(extractCustomImportSubject("json", "null")).toBeNull();
    expect(extractCustomImportSubject("json", "[]")).toBeNull();
  });

  test("rejects JSON without a usable user or observation window", () => {
    expect(extractCustomImportSubject("json", JSON.stringify({ observations: [] }))).toBeNull();
    expect(
      extractCustomImportSubject(
        "json",
        JSON.stringify({
          profile: { user_id: "   " },
          observations: [{ observed_at: "2026-08-08T08:00:00Z" }],
        }),
      ),
    ).toBeNull();
    expect(
      extractCustomImportSubject(
        "json",
        JSON.stringify({
          profile: { user_id: "55555555-5555-4555-8555-555555555555" },
          observations: [{ observed_at: "invalid" }],
        }),
      ),
    ).toBeNull();
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

  test("accepts quoted CSV cells and skips rows without a user", () => {
    const subject = extractCustomImportSubject(
      "csv",
      [
        "observation_id,user_id,observed_at",
        "incomplete",
        "a,,2026-08-01T08:00:00Z",
        'b,"66666666-6666-4666-8666-666666666666","2026-08-05T08:00:00Z"',
      ].join("\n"),
    );

    expect(subject).toEqual({
      userId: "66666666-6666-4666-8666-666666666666",
      endDate: "2026-08-05",
    });
  });

  test("rejects empty CSV, missing columns, missing users and missing dates", () => {
    expect(extractCustomImportSubject("csv", "\n\r\n")).toBeNull();
    expect(extractCustomImportSubject("csv", "metric_type,observed_at\nsteps,2026-08-08")).toBeNull();
    expect(extractCustomImportSubject("csv", "user_id,metric_type\na,steps")).toBeNull();
    expect(
      extractCustomImportSubject(
        "csv",
        "user_id,observed_at\n,2026-08-08T08:00:00Z",
      ),
    ).toBeNull();
    expect(
      extractCustomImportSubject(
        "csv",
        "user_id,observed_at\n77777777-7777-4777-8777-777777777777,invalid",
      ),
    ).toBeNull();
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

  test("does not build a custom scenario when subject metadata is missing", () => {
    expect(buildCustomScenario("json", JSON.stringify({ observations: [] }), buildDemoScenario())).toBeNull();
  });
});

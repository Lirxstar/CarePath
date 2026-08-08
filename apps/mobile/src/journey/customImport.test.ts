import { afterEach, describe, expect, test } from "@jest/globals";

import {
  resetRuntimeAuthState,
  setRuntimeAccountUserId,
  setRuntimePrivateSession,
} from "../auth/runtimeState";
import { buildDemoScenario } from "./demoScenario";
import {
  buildCustomScenario,
  extractCustomImportSubject,
  type CustomImportFormat,
} from "./customImport";

function expectSubjectNull(format: CustomImportFormat, content: string): void {
  expect(extractCustomImportSubject(format, content)).toBeNull();
}

function validCustomContent(userId = "33333333-3333-4333-8333-333333333333"): string {
  return JSON.stringify({
    profile: { user_id: userId },
    observations: [{ observed_at: "2026-08-08T10:00:00+09:00" }],
  });
}

afterEach(() => {
  resetRuntimeAuthState();
});

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

  test("falls back to an observation user and ignores unusable JSON entries", () => {
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
    expectSubjectNull("json", "{");
    expectSubjectNull("json", "42");
    expectSubjectNull("json", "null");
    expectSubjectNull("json", "[]");
  });

  test("rejects JSON without a usable user or observation window", () => {
    expectSubjectNull("json", JSON.stringify({ observations: [] }));
    expectSubjectNull(
      "json",
      JSON.stringify({
        profile: { user_id: "   " },
        observations: [{ observed_at: "2026-08-08T08:00:00Z" }],
      }),
    );
    expectSubjectNull(
      "json",
      JSON.stringify({
        profile: { user_id: "55555555-5555-4555-8555-555555555555" },
        observations: [{ observed_at: "invalid" }],
      }),
    );
    expectSubjectNull(
      "json",
      JSON.stringify({
        profile: { user_id: "88888888-8888-4888-8888-888888888888" },
        observations: { observed_at: "2026-08-08T08:00:00Z" },
      }),
    );
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
    expectSubjectNull("csv", "\n\r\n");
    expectSubjectNull("csv", "metric_type,observed_at\nsteps,2026-08-08");
    expectSubjectNull("csv", "user_id,metric_type\na,steps");
    expectSubjectNull("csv", "user_id,observed_at\n,2026-08-08T08:00:00Z");
    expectSubjectNull("csv", "user_id,observed_at\n77777777-7777-4777-8777-777777777777,invalid");
  });

  test("builds a standard reviewer scenario using imported subject identifiers", () => {
    const scenario = buildCustomScenario("json", validCustomContent(), buildDemoScenario());

    expect(scenario?.userId).toBe("33333333-3333-4333-8333-333333333333");
    expect(scenario?.endDate).toBe("2026-08-08");
    expect(scenario?.displayName).toBe("Your imported data");
    expect(scenario?.description).toMatch(/may be retained/u);
  });

  test("binds signed-in imports to the stable account user", () => {
    setRuntimeAccountUserId("99999999-9999-4999-8999-999999999999");
    const scenario = buildCustomScenario("json", validCustomContent(), buildDemoScenario());

    expect(scenario?.userId).toBe("99999999-9999-4999-8999-999999999999");
    expect(scenario?.description).toMatch(/signed-in CarePath account/u);
  });

  test("describes private imports as non-persistent", () => {
    setRuntimePrivateSession("private-session");
    const scenario = buildCustomScenario("json", validCustomContent(), buildDemoScenario());

    expect(scenario?.userId).toBe("33333333-3333-4333-8333-333333333333");
    expect(scenario?.description).toMatch(/temporary server memory/u);
    expect(scenario?.description).toMatch(/not written to persistent storage/u);
  });

  test("private signed-in imports keep account identity inside the isolated workspace", () => {
    setRuntimeAccountUserId("99999999-9999-4999-8999-999999999999");
    setRuntimePrivateSession("private-session");
    const scenario = buildCustomScenario("json", validCustomContent(), buildDemoScenario());

    expect(scenario?.userId).toBe("99999999-9999-4999-8999-999999999999");
    expect(scenario?.description).toMatch(/Private mode/u);
  });

  test("does not build a custom scenario when subject metadata is missing", () => {
    const scenario = buildCustomScenario(
      "json",
      JSON.stringify({ observations: [] }),
      buildDemoScenario(),
    );
    expect(scenario).toBeNull();
  });
});

import type { DemoScenario } from "./demoScenario";

export type CustomImportFormat = "csv" | "json";

export interface CustomImportSubject {
  userId: string;
  endDate: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function datePart(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString().slice(0, 10);
}

function latestDate(values: unknown[]): string | null {
  const dates = values.flatMap((value) => {
    const parsed = datePart(value);
    return parsed === null ? [] : [parsed];
  });
  return dates.sort().at(-1) ?? null;
}

function jsonSubject(content: string): CustomImportSubject | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    return null;
  }
  const root = asRecord(parsed);
  if (root === null) {
    return null;
  }
  const profile = asRecord(root.profile);
  const observations = Array.isArray(root.observations) ? root.observations : [];
  const observationRecords = observations.flatMap((item) => {
    const record = asRecord(item);
    return record === null ? [] : [record];
  });
  const profileUserId = profile?.user_id;
  const observationUserId = observationRecords[0]?.user_id;
  const userId =
    typeof profileUserId === "string"
      ? profileUserId
      : typeof observationUserId === "string"
        ? observationUserId
        : null;
  if (userId === null || userId.trim().length === 0) {
    return null;
  }
  const endDate = latestDate(observationRecords.map((item) => item.observed_at));
  if (endDate === null) {
    return null;
  }
  return { userId: userId.trim(), endDate };
}

function csvCells(line: string): string[] {
  return line.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""));
}

function csvSubject(content: string): CustomImportSubject | null {
  const lines = content
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean);
  const header = lines[0];
  if (header === undefined) {
    return null;
  }
  const columns = csvCells(header);
  const userIndex = columns.indexOf("user_id");
  const observedIndex = columns.indexOf("observed_at");
  if (userIndex < 0 || observedIndex < 0) {
    return null;
  }
  const rows = lines.slice(1).map(csvCells);
  const userId = rows.find((row) => (row[userIndex] ?? "").length > 0)?.[userIndex] ?? null;
  const endDate = latestDate(rows.map((row) => row[observedIndex]));
  if (userId === null || endDate === null) {
    return null;
  }
  return { userId, endDate };
}

export function extractCustomImportSubject(
  format: CustomImportFormat,
  content: string,
): CustomImportSubject | null {
  return format === "json" ? jsonSubject(content) : csvSubject(content);
}

export function buildCustomScenario(
  format: CustomImportFormat,
  content: string,
  base: DemoScenario,
): DemoScenario | null {
  const subject = extractCustomImportSubject(format, content);
  if (subject === null) {
    return null;
  }
  return {
    ...base,
    displayName: "Your imported data",
    description:
      "User-supplied health data loaded through the public demo. Submitted data may be retained on the demo server.",
    goalLabel: "Explore recent patterns and a realistic health-behaviour plan.",
    userId: subject.userId,
    endDate: subject.endDate,
    question: "What patterns do you notice in my recent data, and what is realistic this week?",
  };
}

export interface HealthResponse {
  provider: string;
  status: "ok";
}

export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return candidate.status === "ok" && typeof candidate.provider === "string";
}

export interface PublicRuntimeConfig {
  auth_enabled: boolean;
  supabase_url: string | null;
  supabase_publishable_key: string | null;
  private_mode_available: boolean;
  private_session_ttl_minutes: number;
}

export interface SupabaseSession {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  tokenType: string;
}

export interface AuthMeResponse {
  authenticated: true;
  carepath_user_id: string;
  email: string | null;
  profile_exists: boolean;
  latest_observation_at: string | null;
}

export interface SignUpResult {
  session: SupabaseSession | null;
  confirmationRequired: boolean;
}

interface SupabaseSessionPayload {
  access_token?: unknown;
  refresh_token?: unknown;
  expires_in?: unknown;
  expires_at?: unknown;
  token_type?: unknown;
}

interface StringStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
}

const SESSION_STORAGE_KEY = "carepath.auth.session.v1";
let memorySession: SupabaseSession | null = null;

export class AuthClientError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "AuthClientError";
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function configured(config: PublicRuntimeConfig): { url: string; key: string } {
  if (!config.auth_enabled || !config.supabase_url || !config.supabase_publishable_key) {
    throw new AuthClientError(
      "auth_not_configured",
      "Account sign-in is not configured for this deployment.",
    );
  }
  return { url: config.supabase_url.replace(/\/+$/, ""), key: config.supabase_publishable_key };
}

function parseSessionPayload(value: unknown): SupabaseSession | null {
  const payload = asRecord(value) as SupabaseSessionPayload | null;
  if (payload === null) {
    return null;
  }
  if (
    typeof payload.access_token !== "string" ||
    typeof payload.refresh_token !== "string" ||
    typeof payload.token_type !== "string"
  ) {
    return null;
  }
  const now = Math.floor(Date.now() / 1000);
  const expiresAt =
    typeof payload.expires_at === "number"
      ? payload.expires_at
      : typeof payload.expires_in === "number"
        ? now + payload.expires_in
        : now + 3600;
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    expiresAt,
    tokenType: payload.token_type,
  };
}

async function responsePayload(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  const record = asRecord(payload);
  if (record === null) {
    return fallback;
  }
  for (const key of ["msg", "message", "error_description", "error"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return fallback;
}

async function authPost(
  config: PublicRuntimeConfig,
  path: string,
  body: Record<string, unknown>,
  accessToken?: string,
): Promise<{ ok: boolean; status: number; payload: unknown }> {
  const { url, key } = configured(config);
  const headers: Record<string, string> = {
    Accept: "application/json",
    apikey: key,
    "Content-Type": "application/json",
  };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const response = await fetch(`${url}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  return { ok: response.ok, status: response.status, payload: await responsePayload(response) };
}

export async function signInWithPassword(
  config: PublicRuntimeConfig,
  email: string,
  password: string,
): Promise<SupabaseSession> {
  const result = await authPost(config, "/auth/v1/token?grant_type=password", { email, password });
  const session = parseSessionPayload(result.payload);
  if (!result.ok || session === null) {
    throw new AuthClientError(
      "sign_in_failed",
      errorMessage(result.payload, "Email sign-in failed."),
    );
  }
  return session;
}

export async function signUpWithPassword(
  config: PublicRuntimeConfig,
  email: string,
  password: string,
): Promise<SignUpResult> {
  const result = await authPost(config, "/auth/v1/signup", { email, password });
  if (!result.ok) {
    throw new AuthClientError(
      "sign_up_failed",
      errorMessage(result.payload, "Account registration failed."),
    );
  }
  const session = parseSessionPayload(result.payload);
  return { session, confirmationRequired: session === null };
}

export async function refreshSupabaseSession(
  config: PublicRuntimeConfig,
  refreshToken: string,
): Promise<SupabaseSession> {
  const result = await authPost(config, "/auth/v1/token?grant_type=refresh_token", {
    refresh_token: refreshToken,
  });
  const session = parseSessionPayload(result.payload);
  if (!result.ok || session === null) {
    throw new AuthClientError("refresh_failed", "The saved account session has expired.");
  }
  return session;
}

export async function signOutSupabase(
  config: PublicRuntimeConfig,
  accessToken: string,
): Promise<void> {
  try {
    await authPost(config, "/auth/v1/logout", {}, accessToken);
  } catch {
    // Local sign-out must still succeed if the auth service is temporarily unavailable.
  }
}

export function googleAuthorizeUrl(config: PublicRuntimeConfig, redirectTo: string): string {
  const { url } = configured(config);
  const query = new URLSearchParams({ provider: "google", redirect_to: redirectTo });
  return `${url}/auth/v1/authorize?${query.toString()}`;
}

export function parseOAuthFragment(fragment: string): SupabaseSession | null {
  const normalized = fragment.startsWith("#") ? fragment.slice(1) : fragment;
  if (!normalized) {
    return null;
  }
  const params = new URLSearchParams(normalized);
  const accessToken = params.get("access_token");
  const refreshToken = params.get("refresh_token");
  const tokenType = params.get("token_type") ?? "bearer";
  if (!accessToken || !refreshToken) {
    return null;
  }
  const expiresAtParam = Number(params.get("expires_at"));
  const expiresIn = Number(params.get("expires_in"));
  const now = Math.floor(Date.now() / 1000);
  return {
    accessToken,
    refreshToken,
    tokenType,
    expiresAt:
      Number.isFinite(expiresAtParam) && expiresAtParam > 0
        ? expiresAtParam
        : now + (Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn : 3600),
  };
}

function runtimeStorage(): StringStorage | null {
  const runtime = globalThis as typeof globalThis & { localStorage?: StringStorage };
  return runtime.localStorage ?? null;
}

export function loadStoredSession(): SupabaseSession | null {
  const storage = runtimeStorage();
  if (storage === null) {
    return memorySession;
  }
  const serialized = storage.getItem(SESSION_STORAGE_KEY);
  if (!serialized) {
    return null;
  }
  try {
    const parsed = asRecord(JSON.parse(serialized));
    if (
      parsed === null ||
      typeof parsed.accessToken !== "string" ||
      typeof parsed.refreshToken !== "string" ||
      typeof parsed.expiresAt !== "number" ||
      typeof parsed.tokenType !== "string"
    ) {
      storage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    return {
      accessToken: parsed.accessToken,
      refreshToken: parsed.refreshToken,
      expiresAt: parsed.expiresAt,
      tokenType: parsed.tokenType,
    };
  } catch {
    storage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

export function saveSession(session: SupabaseSession | null): void {
  memorySession = session;
  const storage = runtimeStorage();
  if (storage === null) {
    return;
  }
  if (session === null) {
    storage.removeItem(SESSION_STORAGE_KEY);
  } else {
    storage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  }
}

export function sessionNeedsRefresh(session: SupabaseSession): boolean {
  return session.expiresAt <= Math.floor(Date.now() / 1000) + 60;
}

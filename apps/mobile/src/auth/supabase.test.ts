import { afterEach, describe, expect, test } from "@jest/globals";

import {
  AuthClientError,
  googleAuthorizeUrl,
  loadStoredSession,
  parseOAuthFragment,
  refreshSupabaseSession,
  saveSession,
  sessionNeedsRefresh,
  signInWithPassword,
  signOutSupabase,
  signUpWithPassword,
  type PublicRuntimeConfig,
  type SupabaseSession,
} from "./supabase";

const originalFetch = globalThis.fetch;
const originalLocalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");

const CONFIG: PublicRuntimeConfig = {
  auth_enabled: true,
  supabase_url: "https://project.supabase.co",
  supabase_publishable_key: "sb_publishable_test",
  private_mode_available: true,
  private_session_ttl_minutes: 60,
};

const SESSION: SupabaseSession = {
  accessToken: "access",
  refreshToken: "refresh",
  expiresAt: Math.floor(Date.now() / 1000) + 3600,
  tokenType: "bearer",
};

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function setFetch(handler: (url: string, init?: RequestInit) => Promise<Response>): void {
  globalThis.fetch = ((input: string | URL | Request, init?: RequestInit) =>
    handler(
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url,
      init,
    )) as typeof fetch;
}

class MemoryStorage {
  readonly values = new Map<string, string>();
  readonly removed: string[] = [];

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.removed.push(key);
    this.values.delete(key);
  }
}

function setLocalStorage(storage: MemoryStorage | undefined): void {
  if (storage === undefined) {
    Reflect.deleteProperty(globalThis, "localStorage");
    return;
  }
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: storage,
  });
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalLocalStorage === undefined) {
    Reflect.deleteProperty(globalThis, "localStorage");
  } else {
    Object.defineProperty(globalThis, "localStorage", originalLocalStorage);
  }
  setLocalStorage(undefined);
  saveSession(null);
  if (originalLocalStorage !== undefined) {
    Object.defineProperty(globalThis, "localStorage", originalLocalStorage);
  }
});

describe("Supabase auth REST client", () => {
  test("builds Google OAuth URLs and rejects unconfigured auth", () => {
    expect(googleAuthorizeUrl(CONFIG, "https://carepath.example/")).toBe(
      "https://project.supabase.co/auth/v1/authorize?provider=google&redirect_to=https%3A%2F%2Fcarepath.example%2F",
    );
    expect(() =>
      googleAuthorizeUrl(
        { ...CONFIG, auth_enabled: false, supabase_url: null, supabase_publishable_key: null },
        "https://carepath.example/",
      ),
    ).toThrow(AuthClientError);
    expect(() =>
      googleAuthorizeUrl({ ...CONFIG, supabase_url: null }, "https://carepath.example/"),
    ).toThrow("Account sign-in is not configured");
    expect(() =>
      googleAuthorizeUrl({ ...CONFIG, supabase_publishable_key: null }, "https://carepath.example/"),
    ).toThrow("Account sign-in is not configured");
  });

  test("parses OAuth fragments with explicit, relative and fallback expiry", () => {
    expect(parseOAuthFragment("")).toBeNull();
    expect(parseOAuthFragment("#")).toBeNull();
    expect(parseOAuthFragment("#access_token=a")).toBeNull();
    expect(parseOAuthFragment("#refresh_token=r")).toBeNull();

    expect(
      parseOAuthFragment("#access_token=a&refresh_token=r&token_type=custom&expires_at=2000000000"),
    ).toEqual({ accessToken: "a", refreshToken: "r", tokenType: "custom", expiresAt: 2000000000 });

    const before = Math.floor(Date.now() / 1000);
    const relative = parseOAuthFragment("access_token=a&refresh_token=r&expires_in=120");
    expect(relative?.tokenType).toBe("bearer");
    expect(relative?.expiresAt).toBeGreaterThanOrEqual(before + 120);
    expect(relative?.expiresAt).toBeLessThanOrEqual(Math.floor(Date.now() / 1000) + 120);

    const fallback = parseOAuthFragment(
      "#access_token=a&refresh_token=r&expires_at=bad&expires_in=bad",
    );
    expect(fallback?.expiresAt).toBeGreaterThanOrEqual(before + 3599);
  });

  test("signs in with password and sends the publishable key", async () => {
    let seenUrl = "";
    let seenHeaders: HeadersInit | undefined;
    let seenBody = "";
    setFetch(async (url, init) => {
      seenUrl = url;
      seenHeaders = init?.headers;
      seenBody = String(init?.body ?? "");
      return jsonResponse({
        access_token: "access",
        refresh_token: "refresh",
        expires_at: 2000000000,
        token_type: "bearer",
      });
    });

    await expect(signInWithPassword(CONFIG, "person@example.com", "password1")).resolves.toEqual({
      accessToken: "access",
      refreshToken: "refresh",
      expiresAt: 2000000000,
      tokenType: "bearer",
    });
    expect(seenUrl).toContain("/auth/v1/token?grant_type=password");
    expect(new Headers(seenHeaders).get("apikey")).toBe("sb_publishable_test");
    expect(JSON.parse(seenBody)).toEqual({ email: "person@example.com", password: "password1" });
  });

  test("derives token expiry from expires_in and default fallback", async () => {
    const now = Math.floor(Date.now() / 1000);
    setFetch(async () =>
      jsonResponse({
        access_token: "a",
        refresh_token: "r",
        expires_in: 120,
        token_type: "bearer",
      }),
    );
    const relative = await signInWithPassword(CONFIG, "a@b.co", "password1");
    expect(relative.expiresAt).toBeGreaterThanOrEqual(now + 120);

    setFetch(async () =>
      jsonResponse({ access_token: "a", refresh_token: "r", token_type: "bearer" }),
    );
    const fallback = await signInWithPassword(CONFIG, "a@b.co", "password1");
    expect(fallback.expiresAt).toBeGreaterThanOrEqual(now + 3599);
  });

  test("returns controlled sign-in errors for every supported Supabase error field", async () => {
    for (const [payload, expected] of [
      [{ msg: "msg failure" }, "msg failure"],
      [{ message: "message failure" }, "message failure"],
      [{ error_description: "description failure" }, "description failure"],
      [{ error: "error failure" }, "error failure"],
      [null, "Email sign-in failed."],
    ] as const) {
      setFetch(async () => jsonResponse(payload, 400));
      await expect(signInWithPassword(CONFIG, "a@b.co", "password1")).rejects.toThrow(expected);
    }
  });

  test("rejects successful responses without complete session fields", async () => {
    for (const payload of [
      [],
      { refresh_token: "r", token_type: "bearer" },
      { access_token: "a", token_type: "bearer" },
      { access_token: "a", refresh_token: "r" },
    ]) {
      setFetch(async () => jsonResponse(payload));
      await expect(signInWithPassword(CONFIG, "a@b.co", "password1")).rejects.toThrow(
        "Email sign-in failed.",
      );
    }
  });

  test("registers accounts with immediate sessions or email confirmation", async () => {
    setFetch(async () =>
      jsonResponse({
        access_token: "a",
        refresh_token: "r",
        expires_in: 3600,
        token_type: "bearer",
      }),
    );
    const immediate = await signUpWithPassword(CONFIG, "a@b.co", "password1");
    expect(immediate.session?.accessToken).toBe("a");
    expect(immediate.confirmationRequired).toBe(false);

    setFetch(async () => jsonResponse({ id: "new-user" }));
    await expect(signUpWithPassword(CONFIG, "a@b.co", "password1")).resolves.toEqual({
      session: null,
      confirmationRequired: true,
    });

    setFetch(async () => jsonResponse({ message: "already registered" }, 400));
    await expect(signUpWithPassword(CONFIG, "a@b.co", "password1")).rejects.toThrow(
      "already registered",
    );
  });

  test("refreshes an account session and reports invalid refreshes", async () => {
    setFetch(async () =>
      jsonResponse({
        access_token: "new-access",
        refresh_token: "new-refresh",
        expires_in: 3600,
        token_type: "bearer",
      }),
    );
    await expect(refreshSupabaseSession(CONFIG, "old-refresh")).resolves.toMatchObject({
      accessToken: "new-access",
      refreshToken: "new-refresh",
    });

    setFetch(async () => jsonResponse({ message: "expired" }, 401));
    await expect(refreshSupabaseSession(CONFIG, "old-refresh")).rejects.toThrow(
      "saved account session has expired",
    );
  });

  test("signs out with bearer auth and tolerates service or JSON failures", async () => {
    let authorization: string | null = null;
    setFetch(async (_url, init) => {
      authorization = new Headers(init?.headers).get("Authorization");
      return jsonResponse({});
    });
    await expect(signOutSupabase(CONFIG, "access-token")).resolves.toBeUndefined();
    expect(authorization).toBe("Bearer access-token");

    globalThis.fetch = (() => Promise.reject(new Error("offline"))) as typeof fetch;
    await expect(signOutSupabase(CONFIG, "access-token")).resolves.toBeUndefined();

    globalThis.fetch = (() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.reject(new Error("bad json")),
      } as Response)) as typeof fetch;
    await expect(signOutSupabase(CONFIG, "access-token")).resolves.toBeUndefined();
  });

  test("stores sessions in memory when Web storage is unavailable", () => {
    setLocalStorage(undefined);
    saveSession(SESSION);
    expect(loadStoredSession()).toEqual(SESSION);
    saveSession(null);
    expect(loadStoredSession()).toBeNull();
  });

  test("stores, restores and clears valid Web sessions", () => {
    const storage = new MemoryStorage();
    setLocalStorage(storage);
    expect(loadStoredSession()).toBeNull();
    saveSession(SESSION);
    expect(loadStoredSession()).toEqual(SESSION);
    saveSession(null);
    expect(loadStoredSession()).toBeNull();
    expect(storage.removed.length).toBeGreaterThan(0);
  });

  test("removes malformed or structurally invalid stored sessions", () => {
    const storage = new MemoryStorage();
    setLocalStorage(storage);
    const key = "carepath.auth.session.v1";

    storage.values.set(key, "{");
    expect(loadStoredSession()).toBeNull();

    for (const payload of [
      null,
      [],
      { refreshToken: "r", expiresAt: 1, tokenType: "bearer" },
      { accessToken: "a", expiresAt: 1, tokenType: "bearer" },
      { accessToken: "a", refreshToken: "r", tokenType: "bearer" },
      { accessToken: "a", refreshToken: "r", expiresAt: 1 },
    ]) {
      storage.values.set(key, JSON.stringify(payload));
      expect(loadStoredSession()).toBeNull();
    }
    expect(storage.removed.length).toBeGreaterThanOrEqual(7);
  });

  test("detects sessions that need refresh", () => {
    const now = Math.floor(Date.now() / 1000);
    expect(sessionNeedsRefresh({ ...SESSION, expiresAt: now + 30 })).toBe(true);
    expect(sessionNeedsRefresh({ ...SESSION, expiresAt: now + 600 })).toBe(false);
  });
});

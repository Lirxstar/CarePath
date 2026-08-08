import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";
import { Platform } from "react-native";

import { createRuntimeApiClient } from "../api/runtime";
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
  type AuthMeResponse,
  type PublicRuntimeConfig,
  type SupabaseSession,
} from "./supabase";

const PRIVATE_SESSION_HEADER = "X-CarePath-Private-Session";

interface PrivateSessionResponse {
  session_id: string;
  ttl_minutes: number;
  persistent_storage: false;
}

interface AuthContextValue {
  runtimeConfig: PublicRuntimeConfig | null;
  authStatus: "loading" | "anonymous" | "authenticated" | "error";
  authBusy: boolean;
  authMessage: string | null;
  account: AuthMeResponse | null;
  privateMode: boolean;
  privateBusy: boolean;
  privateSessionId: string | null;
  privateTtlMinutes: number | null;
  requestHeaders: () => Record<string, string>;
  signInEmail: (email: string, password: string) => Promise<void>;
  signUpEmail: (email: string, password: string) => Promise<void>;
  signInGoogle: () => void;
  signOut: () => Promise<void>;
  setPrivateMode: (enabled: boolean) => Promise<void>;
}

interface AuthProviderProps extends PropsWithChildren {
  apiBaseUrl?: string;
}

interface WebRuntime {
  location?: {
    hash: string;
    origin: string;
    pathname: string;
    assign: (url: string) => void;
  };
  history?: {
    replaceState: (data: unknown, unused: string, url?: string | URL | null) => void;
  };
}

const AuthContext = createContext<AuthContextValue | null>(null);

function runtime(): WebRuntime {
  return globalThis as typeof globalThis & WebRuntime;
}

function errorText(error: unknown): string {
  if (error instanceof AuthClientError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Account operation failed.";
}

export function AuthProvider({ children, apiBaseUrl }: AuthProviderProps) {
  const [runtimeConfig, setRuntimeConfig] = useState<PublicRuntimeConfig | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthContextValue["authStatus"]>("loading");
  const [authBusy, setAuthBusy] = useState(false);
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const [session, setSession] = useState<SupabaseSession | null>(null);
  const [account, setAccount] = useState<AuthMeResponse | null>(null);
  const [privateSessionId, setPrivateSessionId] = useState<string | null>(null);
  const [privateBusy, setPrivateBusy] = useState(false);
  const [privateTtlMinutes, setPrivateTtlMinutes] = useState<number | null>(null);

  const loadAccount = useCallback(
    async (nextSession: SupabaseSession): Promise<boolean> => {
      const client = createRuntimeApiClient(apiBaseUrl, () => ({
        Authorization: `Bearer ${nextSession.accessToken}`,
      }));
      const result = await client.get<AuthMeResponse>("/auth/me");
      if (!result.ok) {
        setAuthMessage(result.error.message);
        setAuthStatus(result.error.status === 401 ? "anonymous" : "error");
        if (result.error.status === 401) {
          saveSession(null);
          setSession(null);
          setAccount(null);
        }
        return false;
      }
      saveSession(nextSession);
      setSession(nextSession);
      setAccount(result.data);
      setAuthStatus("authenticated");
      setAuthMessage(null);
      return true;
    },
    [apiBaseUrl],
  );

  useEffect(() => {
    let cancelled = false;
    const initialise = async () => {
      const client = createRuntimeApiClient(apiBaseUrl);
      const configResult = await client.get<PublicRuntimeConfig>("/config/public");
      if (cancelled) {
        return;
      }
      if (!configResult.ok) {
        setAuthStatus("error");
        setAuthMessage(configResult.error.message);
        return;
      }
      const config = configResult.data;
      setRuntimeConfig(config);
      setPrivateTtlMinutes(config.private_session_ttl_minutes);

      if (!config.auth_enabled) {
        saveSession(null);
        setAuthStatus("anonymous");
        return;
      }

      const webRuntime = runtime();
      const redirected =
        Platform.OS === "web" && webRuntime.location
          ? parseOAuthFragment(webRuntime.location.hash)
          : null;
      if (redirected && webRuntime.history && webRuntime.location) {
        saveSession(redirected);
        webRuntime.history.replaceState(
          null,
          "",
          `${webRuntime.location.origin}${webRuntime.location.pathname}`,
        );
      }

      let restored = redirected ?? loadStoredSession();
      if (restored === null) {
        setAuthStatus("anonymous");
        return;
      }
      if (sessionNeedsRefresh(restored)) {
        try {
          restored = await refreshSupabaseSession(config, restored.refreshToken);
        } catch (error) {
          saveSession(null);
          if (!cancelled) {
            setAuthStatus("anonymous");
            setAuthMessage(errorText(error));
          }
          return;
        }
      }
      if (!cancelled) {
        await loadAccount(restored);
      }
    };
    void initialise();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, loadAccount]);

  const requestHeaders = useCallback((): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (session !== null) {
      headers.Authorization = `Bearer ${session.accessToken}`;
    }
    if (privateSessionId !== null) {
      headers[PRIVATE_SESSION_HEADER] = privateSessionId;
    }
    return headers;
  }, [privateSessionId, session]);

  const signInEmail = useCallback(
    async (email: string, password: string) => {
      if (runtimeConfig === null) {
        setAuthMessage("Account configuration is still loading.");
        return;
      }
      setAuthBusy(true);
      setAuthMessage(null);
      try {
        const nextSession = await signInWithPassword(runtimeConfig, email.trim(), password);
        await loadAccount(nextSession);
      } catch (error) {
        setAuthStatus("anonymous");
        setAuthMessage(errorText(error));
      } finally {
        setAuthBusy(false);
      }
    },
    [loadAccount, runtimeConfig],
  );

  const signUpEmail = useCallback(
    async (email: string, password: string) => {
      if (runtimeConfig === null) {
        setAuthMessage("Account configuration is still loading.");
        return;
      }
      setAuthBusy(true);
      setAuthMessage(null);
      try {
        const result = await signUpWithPassword(runtimeConfig, email.trim(), password);
        if (result.session === null) {
          setAuthStatus("anonymous");
          setAuthMessage("Registration received. Check your email to confirm the account.");
        } else {
          await loadAccount(result.session);
        }
      } catch (error) {
        setAuthStatus("anonymous");
        setAuthMessage(errorText(error));
      } finally {
        setAuthBusy(false);
      }
    },
    [loadAccount, runtimeConfig],
  );

  const signInGoogle = useCallback(() => {
    if (runtimeConfig === null) {
      setAuthMessage("Account configuration is still loading.");
      return;
    }
    if (Platform.OS !== "web") {
      setAuthMessage(
        "Google sign-in is enabled for the Web demo. Native OAuth can be added with platform client IDs later.",
      );
      return;
    }
    const webRuntime = runtime();
    if (!webRuntime.location) {
      setAuthMessage("This runtime cannot open Google sign-in.");
      return;
    }
    const redirectTo = `${webRuntime.location.origin}${webRuntime.location.pathname}`;
    try {
      webRuntime.location.assign(googleAuthorizeUrl(runtimeConfig, redirectTo));
    } catch (error) {
      setAuthMessage(errorText(error));
    }
  }, [runtimeConfig]);

  const setPrivateMode = useCallback(
    async (enabled: boolean) => {
      if (enabled === (privateSessionId !== null)) {
        return;
      }
      setPrivateBusy(true);
      setAuthMessage(null);
      try {
        if (enabled) {
          const headers = (): Record<string, string> =>
            session === null ? {} : { Authorization: `Bearer ${session.accessToken}` };
          const client = createRuntimeApiClient(apiBaseUrl, headers);
          const result = await client.post<PrivateSessionResponse>("/privacy/session", {});
          if (!result.ok) {
            setAuthMessage(result.error.message);
            return;
          }
          setPrivateSessionId(result.data.session_id);
          setPrivateTtlMinutes(result.data.ttl_minutes);
          setAuthMessage(
            "Private mode is on. New health data and CarePath activity stay in temporary server memory only.",
          );
        } else {
          const activeId = privateSessionId;
          if (activeId !== null) {
            const client = createRuntimeApiClient(apiBaseUrl, () => {
              const headers: Record<string, string> = { [PRIVATE_SESSION_HEADER]: activeId };
              if (session !== null) {
                headers.Authorization = `Bearer ${session.accessToken}`;
              }
              return headers;
            });
            await client.post("/privacy/session/end", {});
          }
          setPrivateSessionId(null);
          setAuthMessage("Private mode is off. Standard demo storage rules apply to new activity.");
        }
      } finally {
        setPrivateBusy(false);
      }
    },
    [apiBaseUrl, privateSessionId, session],
  );

  const signOut = useCallback(async () => {
    setAuthBusy(true);
    try {
      if (privateSessionId !== null) {
        await setPrivateMode(false);
      }
      if (runtimeConfig !== null && session !== null) {
        await signOutSupabase(runtimeConfig, session.accessToken);
      }
      saveSession(null);
      setSession(null);
      setAccount(null);
      setAuthStatus("anonymous");
      setAuthMessage("Signed out. You can continue using CarePath without an account.");
    } finally {
      setAuthBusy(false);
    }
  }, [privateSessionId, runtimeConfig, session, setPrivateMode]);

  const value = useMemo<AuthContextValue>(
    () => ({
      runtimeConfig,
      authStatus,
      authBusy,
      authMessage,
      account,
      privateMode: privateSessionId !== null,
      privateBusy,
      privateSessionId,
      privateTtlMinutes,
      requestHeaders,
      signInEmail,
      signUpEmail,
      signInGoogle,
      signOut,
      setPrivateMode,
    }),
    [
      account,
      authBusy,
      authMessage,
      authStatus,
      privateBusy,
      privateSessionId,
      privateTtlMinutes,
      requestHeaders,
      runtimeConfig,
      setPrivateMode,
      signInEmail,
      signInGoogle,
      signOut,
      signUpEmail,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}

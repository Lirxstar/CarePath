let accessToken: string | null = null;
let privateSessionId: string | null = null;
let accountUserId: string | null = null;

const PRIVATE_SESSION_HEADER = "X-CarePath-Private-Session";

export function setRuntimeAccessToken(value: string | null): void {
  accessToken = value;
}

export function setRuntimePrivateSession(value: string | null): void {
  privateSessionId = value;
}

export function setRuntimeAccountUserId(value: string | null): void {
  accountUserId = value;
}

export function runtimeApiHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (accessToken !== null) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  if (privateSessionId !== null) {
    headers[PRIVATE_SESSION_HEADER] = privateSessionId;
  }
  return headers;
}

export function runtimeAccountUserId(): string | null {
  return accountUserId;
}

export function runtimePrivateMode(): boolean {
  return privateSessionId !== null;
}

export function resetRuntimeAuthState(): void {
  accessToken = null;
  privateSessionId = null;
  accountUserId = null;
}

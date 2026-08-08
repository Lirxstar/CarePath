export interface ControlledApiError {
  code: string;
  message: string;
  requestId: string | null;
  status: number | null;
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ControlledApiError };

export type ApiLoadState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: ControlledApiError };

export interface ApiResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

export interface ApiRequestInit {
  method: "GET" | "POST";
  headers: Record<string, string>;
  body?: string;
}

export type ApiFetcher = (url: string, init: ApiRequestInit) => Promise<ApiResponse>;
export type ApiHeaderProvider = () => Record<string, string>;

const ACCEPT_HEADERS = { Accept: "application/json" } as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parseControlledError(value: unknown, status: number): ControlledApiError {
  if (!isRecord(value)) {
    return fallbackHttpError(status);
  }
  const rawError = value.error;
  if (!isRecord(rawError)) {
    return fallbackHttpError(status);
  }
  if (
    typeof rawError.code !== "string" ||
    typeof rawError.message !== "string" ||
    typeof rawError.request_id !== "string"
  ) {
    return fallbackHttpError(status);
  }

  return {
    code: rawError.code,
    message: rawError.message,
    requestId: rawError.request_id,
    status,
  };
}

function fallbackHttpError(status: number): ControlledApiError {
  return {
    code: "http_error",
    message: `CarePath request failed with status ${String(status)}`,
    requestId: null,
    status,
  };
}

function networkError(): ControlledApiError {
  return {
    code: "network_error",
    message: "CarePath could not reach the API",
    requestId: null,
    status: null,
  };
}

function normalisePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

export class CarePathApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: ApiFetcher;
  private readonly headerProvider: ApiHeaderProvider;

  constructor(
    baseUrl: string,
    fetcher: ApiFetcher,
    headerProvider: ApiHeaderProvider = () => ({}),
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.fetcher = fetcher;
    this.headerProvider = headerProvider;
  }

  get<T>(path: string): Promise<ApiResult<T>> {
    return this.request<T>(path, {
      method: "GET",
      headers: { ...ACCEPT_HEADERS, ...this.headerProvider() },
    });
  }

  post<T>(path: string, body: unknown): Promise<ApiResult<T>> {
    return this.request<T>(path, {
      method: "POST",
      headers: {
        ...ACCEPT_HEADERS,
        ...this.headerProvider(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  }

  private async request<T>(path: string, init: ApiRequestInit): Promise<ApiResult<T>> {
    try {
      const response = await this.fetcher(`${this.baseUrl}${normalisePath(path)}`, init);
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }

      if (response.ok) {
        return { ok: true, data: payload as T };
      }
      return { ok: false, error: parseControlledError(payload, response.status) };
    } catch {
      return { ok: false, error: networkError() };
    }
  }
}

export async function loadApiResource<T>(
  operation: () => Promise<ApiResult<T>>,
  onState: (state: ApiLoadState<T>) => void,
): Promise<ApiLoadState<T>> {
  onState({ status: "loading" });
  const result = await operation();
  const nextState: ApiLoadState<T> = result.ok
    ? { status: "success", data: result.data }
    : { status: "error", error: result.error };
  onState(nextState);
  return nextState;
}

import {
  CarePathApiClient,
  type ApiFetcher,
  type ApiHeaderProvider,
  type ApiRequestInit,
} from "./client";

export const LOCAL_API_URL = "http://127.0.0.1:8000";
export const SAME_ORIGIN_API_URL = "__CAREPATH_SAME_ORIGIN__";

export interface RuntimeFetchResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

export type RuntimeFetch = (url: string, init: ApiRequestInit) => Promise<RuntimeFetchResponse>;

export function resolveApiBaseUrl(configuredUrl: string | undefined): string {
  const trimmed = configuredUrl?.trim();
  if (trimmed === SAME_ORIGIN_API_URL) {
    return "";
  }
  if (trimmed === undefined || trimmed.length === 0) {
    return LOCAL_API_URL;
  }
  return trimmed;
}

export function createRuntimeFetcher(fetchImpl: RuntimeFetch): ApiFetcher {
  return (url, init) => fetchImpl(url, init);
}

const expoFetch: RuntimeFetch = async (url, init) => {
  const response = await fetch(url, init);
  return {
    ok: response.ok,
    status: response.status,
    json: async () => {
      const payload: unknown = await response.json();
      return payload;
    },
  };
};

export function createRuntimeApiClient(
  baseUrl?: string,
  headerProvider: ApiHeaderProvider = () => ({}),
): CarePathApiClient {
  return new CarePathApiClient(
    baseUrl ?? resolveApiBaseUrl(process.env.EXPO_PUBLIC_CAREPATH_API_URL),
    createRuntimeFetcher(expoFetch),
    headerProvider,
  );
}

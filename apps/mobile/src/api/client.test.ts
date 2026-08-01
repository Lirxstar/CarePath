import { describe, expect, test } from "@jest/globals";

import {
  CarePathApiClient,
  loadApiResource,
  parseControlledError,
  type ApiFetcher,
  type ApiLoadState,
  type ApiRequestInit,
  type ApiResponse,
} from "./client";

function response(ok: boolean, status: number, payload: unknown): ApiResponse {
  return {
    ok,
    status,
    json: () => Promise.resolve(payload),
  };
}

describe("CarePathApiClient", () => {
  test("performs a GET request and normalises the base URL and path", async () => {
    let receivedUrl = "";
    let receivedInit: ApiRequestInit | undefined;
    const fetcher: ApiFetcher = (url, init) => {
      receivedUrl = url;
      receivedInit = init;
      return Promise.resolve(response(true, 200, { status: "ok", provider: "mock" }));
    };
    const client = new CarePathApiClient("http://localhost:8000///", fetcher);

    const result = await client.get<{ status: string }>("health");

    expect(result).toEqual({ ok: true, data: { status: "ok", provider: "mock" } });
    expect(receivedUrl).toBe("http://localhost:8000/health");
    expect(receivedInit).toEqual({ method: "GET", headers: { Accept: "application/json" } });
  });

  test("performs a JSON POST without changing an already-normalised path", async () => {
    let receivedUrl = "";
    let receivedInit: ApiRequestInit | undefined;
    const fetcher: ApiFetcher = (url, init) => {
      receivedUrl = url;
      receivedInit = init;
      return Promise.resolve(response(true, 200, { interaction_id: "demo" }));
    };
    const client = new CarePathApiClient("http://localhost:8000", fetcher);

    const result = await client.post<{ interaction_id: string }>("/coach/message", {
      message: "hello",
    });

    expect(result).toEqual({ ok: true, data: { interaction_id: "demo" } });
    expect(receivedUrl).toBe("http://localhost:8000/coach/message");
    expect(receivedInit).toEqual({
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: '{"message":"hello"}',
    });
  });

  test("preserves the backend controlled error contract", async () => {
    const fetcher: ApiFetcher = () =>
      Promise.resolve(
        response(false, 404, {
          error: {
            code: "profile_not_found",
            message: "The requested user profile does not exist",
            request_id: "req-123",
          },
        }),
      );
    const client = new CarePathApiClient("http://localhost:8000", fetcher);

    await expect(client.get("/plans/current")).resolves.toEqual({
      ok: false,
      error: {
        code: "profile_not_found",
        message: "The requested user profile does not exist",
        requestId: "req-123",
        status: 404,
      },
    });
  });

  test("returns a controlled HTTP error when the body is not JSON", async () => {
    const fetcher: ApiFetcher = () =>
      Promise.resolve({
        ok: false,
        status: 503,
        json: () => Promise.reject(new Error("not json")),
      });
    const client = new CarePathApiClient("http://localhost:8000", fetcher);

    await expect(client.get("/health")).resolves.toEqual({
      ok: false,
      error: {
        code: "http_error",
        message: "CarePath request failed with status 503",
        requestId: null,
        status: 503,
      },
    });
  });

  test("converts transport failures into a controlled network error", async () => {
    const fetcher: ApiFetcher = () => Promise.reject(new Error("socket closed"));
    const client = new CarePathApiClient("http://localhost:8000", fetcher);

    await expect(client.get("/health")).resolves.toEqual({
      ok: false,
      error: {
        code: "network_error",
        message: "CarePath could not reach the API",
        requestId: null,
        status: null,
      },
    });
  });
});

describe("parseControlledError", () => {
  test.each([
    null,
    {},
    { error: null },
    { error: { code: 42, message: "message", request_id: "request" } },
    { error: { code: "code", message: 42, request_id: "request" } },
    { error: { code: "code", message: "message", request_id: 42 } },
  ])("falls back for malformed error payload %p", (payload) => {
    expect(parseControlledError(payload, 400)).toEqual({
      code: "http_error",
      message: "CarePath request failed with status 400",
      requestId: null,
      status: 400,
    });
  });
});

describe("loadApiResource", () => {
  test("emits loading and success states", async () => {
    const states: ApiLoadState<number>[] = [];

    const finalState = await loadApiResource(
      () => Promise.resolve({ ok: true, data: 7 }),
      (state) => {
        states.push(state);
      },
    );

    expect(states).toEqual([{ status: "loading" }, { status: "success", data: 7 }]);
    expect(finalState).toEqual({ status: "success", data: 7 });
  });

  test("emits loading and controlled error states", async () => {
    const states: ApiLoadState<number>[] = [];
    const error = {
      code: "network_error",
      message: "CarePath could not reach the API",
      requestId: null,
      status: null,
    };

    const finalState = await loadApiResource<number>(
      () => Promise.resolve({ ok: false, error }),
      (state) => {
        states.push(state);
      },
    );

    expect(states).toEqual([{ status: "loading" }, { status: "error", error }]);
    expect(finalState).toEqual({ status: "error", error });
  });
});

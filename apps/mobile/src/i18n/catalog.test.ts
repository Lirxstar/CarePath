import { afterEach, describe, expect, it } from "@jest/globals";

import { CarePathApiClient, type ApiRequestInit } from "../api/client";
import { buildDemoScenario } from "../journey/demoScenario";
import { PrimaryJourneyService } from "../journey/service";
import { translateStaticText } from "./catalog";
import { setRuntimeLocale } from "./runtimeLocale";

describe("web locale catalog", () => {
  afterEach(() => {
    setRuntimeLocale("en");
  });

  it("translates app body content in both directions", () => {
    expect(translateStaticText("zh", "Today dashboard")).toBe("今日仪表板");
    expect(translateStaticText("ja", "今日仪表板")).toBe("今日のダッシュボード");
    expect(translateStaticText("en", "今日のダッシュボード")).toBe("Today dashboard");
    expect(translateStaticText("zh", "Account & privacy")).toBe("账户与隐私");
    expect(translateStaticText("ja", "Raw longitudinal chart")).toBe("生データの経時チャート");
  });

  it("translates dynamic presentation labels without changing identifiers", () => {
    expect(translateStaticText("zh", "Version 3")).toBe("版本 3");
    expect(translateStaticText("ja", "30 days")).toBe("30日間");
    expect(translateStaticText("zh", "87% coverage")).toBe("覆盖率 87%");
    expect(translateStaticText("ja", "Request req-123")).toBe("リクエスト req-123");
  });

  it("sends the selected locale to the real Coach API request", async () => {
    const requestBodies: unknown[] = [];
    const fetcher = (_url: string, init: ApiRequestInit) => {
      if (init.method === "POST" && init.body !== undefined) {
        requestBodies.push(JSON.parse(init.body) as unknown);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      });
    };
    const client = new CarePathApiClient("https://example.invalid", fetcher);
    const service = new PrimaryJourneyService(client, buildDemoScenario());

    setRuntimeLocale("zh");
    await service.askQuestion("test question");
    setRuntimeLocale("ja");
    await service.askQuestion("test question");

    expect(requestBodies).toHaveLength(2);
    expect(requestBodies[0]).toMatchObject({ language: "zh" });
    expect(requestBodies[1]).toMatchObject({ language: "ja" });
  });
});

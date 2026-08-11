export const SUPPORTED_LOCALES = ["en", "zh", "ja"] as const;

export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

export interface MobileStrings {
  localeName: string;
  nav: {
    today: string;
    coach: string;
    healthData: string;
    planHistory: string;
  };
  common: {
    retry: string;
    refresh: string;
    loading: string;
    empty: string;
    offline: string;
    apiError: string;
    language: string;
  };
  safety: {
    title: string;
    body: string;
    urgent: string;
  };
}

export const MOBILE_STRINGS: Record<AppLocale, MobileStrings> = {
  en: {
    localeName: "English",
    nav: {
      today: "Today",
      coach: "Coach",
      healthData: "Health Data",
      planHistory: "Plan & History",
    },
    common: {
      retry: "Retry",
      refresh: "Refresh",
      loading: "Loading…",
      empty: "No data is available yet.",
      offline: "Offline — CarePath cannot reach the API.",
      apiError: "CarePath could not load this page.",
      language: "Language",
    },
    safety: {
      title: "Behaviour support, not medical care",
      body: "CarePath supports low-risk health behaviours. It does not diagnose conditions or change medication. Built-in demo records are synthetic.",
      urgent:
        "For urgent or severe symptoms, use local emergency services or seek prompt professional medical help.",
    },
  },
  zh: {
    localeName: "中文",
    nav: {
      today: "今日",
      coach: "健康教练",
      healthData: "健康数据",
      planHistory: "计划与历史",
    },
    common: {
      retry: "重试",
      refresh: "刷新",
      loading: "加载中…",
      empty: "暂时没有可用数据。",
      offline: "离线——CarePath 无法连接 API。",
      apiError: "CarePath 无法加载此页面。",
      language: "语言",
    },
    safety: {
      title: "健康行为支持，不替代医疗服务",
      body: "CarePath 仅支持低风险健康行为，不进行疾病诊断，也不会调整药物。内置演示记录均为合成数据。",
      urgent: "如出现紧急或严重症状，请联系当地急救服务或尽快寻求专业医疗帮助。",
    },
  },
  ja: {
    localeName: "日本語",
    nav: {
      today: "今日",
      coach: "コーチ",
      healthData: "健康データ",
      planHistory: "プランと履歴",
    },
    common: {
      retry: "再試行",
      refresh: "更新",
      loading: "読み込み中…",
      empty: "利用できるデータはまだありません。",
      offline: "オフライン — CarePath は API に接続できません。",
      apiError: "CarePath はこのページを読み込めませんでした。",
      language: "言語",
    },
    safety: {
      title: "健康行動の支援であり、医療行為ではありません",
      body: "CarePath は低リスクの健康行動を支援します。診断や薬の変更は行いません。組み込みデモ記録は合成データです。",
      urgent:
        "緊急または重い症状がある場合は、地域の救急サービスを利用するか、速やかに医療専門家へ相談してください。",
    },
  },
};

export function stringsFor(locale: AppLocale): MobileStrings {
  return MOBILE_STRINGS[locale];
}

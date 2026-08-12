import type { AppLocale } from "../i18n/resources";

export interface TokyoExample {
  id: "healthcare" | "cooling" | "family";
  label: string;
  query: string;
  municipality: string;
  municipalityLabel: string;
}

export interface TokyoCopy {
  productLine: string;
  heading: string;
  intro: string;
  languageLabel: string;
  requestLabel: string;
  requestPlaceholder: string;
  examplesLabel: string;
  locationHeading: string;
  locationWhy: string;
  useCurrentLocation: string;
  locating: string;
  locationReady: string;
  locationDenied: string;
  manualLabel: string;
  manualPlaceholder: string;
  useManualLocation: string;
  selectedLocation: string;
  findHelp: string;
  searching: string;
  missingRequest: string;
  missingLocation: string;
  offline: string;
  apiError: string;
  retry: string;
  resultsHeading: string;
  verifiedFacts: string;
  whyMatch: string;
  explanationUnavailable: string;
  sourceFreshness: string;
  sourceReportedLanguages: string;
  openingHours: string;
  accessNotes: string;
  address: string;
  distance: string;
  notReported: string;
  directions: string;
  officialPage: string;
  officialSource: string;
  call: string;
  noMatch: string;
  noMatchHint: string;
  clarification: string;
  unsupported: string;
  modelFallback: string;
  partialData: string;
  safetyTitle: string;
  safetyEmergency: string;
  privacyNote: string;
  coreLink: string;
  freshness: Record<"current" | "aging" | "stale" | "unknown", string>;
  category: Record<string, string>;
  examples: TokyoExample[];
}

const EN: TokyoCopy = {
  productLine: "CarePath Tokyo",
  heading: "Find the right Tokyo public service without knowing its name.",
  intro:
    "Describe what you need. CarePath uses official public data, your current area, and bounded multilingual assistance to return grounded options and next actions.",
  languageLabel: "Interface language",
  requestLabel: "What do you need help with?",
  requestPlaceholder: "For example: I need a nearby clinic where staff can support me in English.",
  examplesLabel: "Try a demo scenario",
  locationHeading: "Where should I search?",
  locationWhy:
    "Location is used only for this search. Precise browser coordinates are not stored by the Tokyo route.",
  useCurrentLocation: "Use current location",
  locating: "Getting your current location…",
  locationReady: "Current location ready",
  locationDenied: "Location permission was unavailable. Use a Tokyo municipality below instead.",
  manualLabel: "Or enter a Tokyo municipality",
  manualPlaceholder: "e.g. 新宿区",
  useManualLocation: "Use this area",
  selectedLocation: "Search location",
  findHelp: "Find help",
  searching: "Searching official Tokyo resources…",
  missingRequest: "Describe what you need before searching.",
  missingLocation: "Choose current location or a manual Tokyo municipality before searching.",
  offline: "CarePath Tokyo cannot reach the API. Check your connection and try again.",
  apiError: "CarePath Tokyo could not complete this search.",
  retry: "Try again",
  resultsHeading: "Grounded Tokyo resources",
  verifiedFacts: "Verified source facts",
  whyMatch: "Grounded explanation",
  explanationUnavailable:
    "The explanation model was unavailable or rejected. Source-backed resource facts remain usable.",
  sourceFreshness: "Source & freshness",
  sourceReportedLanguages: "Source-reported languages",
  openingHours: "Published opening information",
  accessNotes: "Access information",
  address: "Location",
  distance: "Distance",
  notReported: "Not reported by the source",
  directions: "Directions",
  officialPage: "Official page",
  officialSource: "Source record",
  call: "Call",
  noMatch: "No resource matched every requested constraint.",
  noMatchHint: "Try a nearby municipality, a wider area, or remove a non-essential constraint.",
  clarification: "CarePath needs one clarification before it can search.",
  unsupported: "That service is outside this bounded Tokyo demo.",
  modelFallback:
    "Model assistance was unavailable or invalid, so CarePath kept the deterministic fallback and did not invent resource facts.",
  partialData:
    "Some official records do not report language, opening, or access details. Missing fields stay unknown rather than being inferred.",
  safetyTitle: "Safety comes before resource ranking",
  safetyEmergency: "Ordinary resource ranking was paused for this request.",
  privacyNote:
    "No account or health-data upload is required. Tokyo search text and precise coordinates are not durably stored by this route.",
  coreLink: "CarePath Core reviewer",
  freshness: {
    current: "Current within source policy",
    aging: "Aging source record",
    stale: "Stale source record",
    unknown: "Freshness unknown",
  },
  category: {
    healthcare: "Healthcare",
    cooling_shelter: "Cooling shelter",
    public_health: "Public health",
    family_support: "Family support",
    women_support: "Women support",
    mental_health_support: "Mental health support",
  },
  examples: [
    {
      id: "healthcare",
      label: "English-speaking clinic",
      query: "I need a nearby clinic in Tokyo where staff can support me in English.",
      municipality: "新宿区",
      municipalityLabel: "Shinjuku City",
    },
    {
      id: "cooling",
      label: "Cooling shelter",
      query: "It is extremely hot. I need a nearby designated place where I can cool down.",
      municipality: "江東区",
      municipalityLabel: "Koto City",
    },
    {
      id: "family",
      label: "Family support",
      query:
        "I am overwhelmed with childcare and do not know which Tokyo public service I should contact for family support.",
      municipality: "江東区",
      municipalityLabel: "Koto City",
    },
  ],
};

const JA: TokyoCopy = {
  ...EN,
  heading: "サービス名が分からなくても、東京都の適切な公的支援先を探せます。",
  intro:
    "必要なことを自然な言葉で入力してください。公式オープンデータ、現在地、限定された多言語支援を使って、根拠のある候補と次の行動を提示します。",
  languageLabel: "表示言語",
  requestLabel: "どのような支援が必要ですか？",
  requestPlaceholder: "例：英語で対応してもらえる近くの診療所を探したいです。",
  examplesLabel: "デモシナリオ",
  locationHeading: "どこを検索しますか？",
  locationWhy: "位置情報は今回の検索だけに使用します。正確なブラウザ座標は保存しません。",
  useCurrentLocation: "現在地を使用",
  locating: "現在地を取得しています…",
  locationReady: "現在地を取得しました",
  locationDenied: "位置情報を利用できませんでした。代わりに東京都内の区市町村を入力してください。",
  manualLabel: "または東京都内の区市町村を入力",
  manualPlaceholder: "例：新宿区",
  useManualLocation: "この地域を使用",
  selectedLocation: "検索地域",
  findHelp: "支援先を探す",
  searching: "東京都の公式リソースを検索しています…",
  missingRequest: "検索する前に必要な支援を入力してください。",
  missingLocation: "現在地または東京都内の区市町村を選択してください。",
  offline: "API に接続できません。通信状態を確認して再試行してください。",
  apiError: "検索を完了できませんでした。",
  retry: "再試行",
  resultsHeading: "根拠のある東京都のリソース",
  verifiedFacts: "確認済みの出典情報",
  whyMatch: "根拠付き説明",
  explanationUnavailable: "説明モデルを利用できませんでした。出典に基づく事実はそのまま利用できます。",
  sourceFreshness: "出典と更新状況",
  sourceReportedLanguages: "出典に記載された対応言語",
  openingHours: "公表された開館・診療情報",
  accessNotes: "アクセス情報",
  address: "所在地",
  distance: "距離",
  notReported: "出典に記載なし",
  directions: "経路",
  officialPage: "公式ページ",
  officialSource: "出典レコード",
  call: "電話",
  noMatch: "指定した条件をすべて満たすリソースは見つかりませんでした。",
  noMatchHint: "近隣地域に変えるか、必須でない条件を外して再検索してください。",
  clarification: "検索前に1点確認が必要です。",
  unsupported: "このサービスは現在の限定版 Tokyo デモの対象外です。",
  modelFallback: "モデル支援を利用できなかったため、決定論的フォールバックを使用し、事実を生成していません。",
  partialData: "公式データに言語・開館時間・アクセス情報がない場合、推測せず不明のまま表示します。",
  safetyTitle: "安全確認をリソース順位付けより先に行います",
  safetyEmergency: "このリクエストでは通常のリソース検索を停止しました。",
  privacyNote: "アカウントや健康データのアップロードは不要です。Tokyo ルートは入力文や正確な座標を永続保存しません。",
  coreLink: "CarePath Core レビュアー",
  freshness: {
    current: "出典ポリシー上は最新",
    aging: "更新から時間が経過",
    stale: "古い出典レコード",
    unknown: "更新状況不明",
  },
  category: {
    healthcare: "医療機関",
    cooling_shelter: "クーリングシェルター",
    public_health: "公衆衛生",
    family_support: "子育て・家族支援",
    women_support: "女性支援",
    mental_health_support: "こころの健康支援",
  },
  examples: [
    {
      id: "healthcare",
      label: "英語対応の診療所",
      query: "東京で、英語で対応してもらえる近くの診療所を探したいです。",
      municipality: "新宿区",
      municipalityLabel: "新宿区",
    },
    {
      id: "cooling",
      label: "クーリングシェルター",
      query: "とても暑いので、近くの指定クーリングシェルターを探したいです。",
      municipality: "江東区",
      municipalityLabel: "江東区",
    },
    {
      id: "family",
      label: "子育て支援",
      query: "育児で困っていますが、どの公的な相談先に連絡すればよいのか分かりません。",
      municipality: "江東区",
      municipalityLabel: "江東区",
    },
  ],
};

const ZH: TokyoCopy = {
  ...EN,
  heading: "即使不知道服务名称，也能找到适合的东京都公共支持。",
  intro:
    "直接描述你的需求。CarePath 使用官方开放数据、当前位置和受限的多语言辅助，返回有来源依据的资源和下一步行动。",
  languageLabel: "界面语言",
  requestLabel: "你需要什么帮助？",
  requestPlaceholder: "例如：我想找一家附近可以用英语沟通的诊所。",
  examplesLabel: "试用演示场景",
  locationHeading: "在哪里搜索？",
  locationWhy: "位置仅用于本次搜索。Tokyo 路由不会保存精确的浏览器坐标。",
  useCurrentLocation: "使用当前位置",
  locating: "正在获取当前位置…",
  locationReady: "已获取当前位置",
  locationDenied: "无法使用位置权限。你仍可输入东京都内的区市町村继续。",
  manualLabel: "或输入东京都内的区市町村",
  manualPlaceholder: "例如：新宿区",
  useManualLocation: "使用这个区域",
  selectedLocation: "搜索位置",
  findHelp: "查找帮助",
  searching: "正在搜索东京官方资源…",
  missingRequest: "请先描述你的需求。",
  missingLocation: "请先选择当前位置或输入东京的区市町村。",
  offline: "CarePath Tokyo 无法连接 API。请检查网络后重试。",
  apiError: "CarePath Tokyo 无法完成本次搜索。",
  retry: "重试",
  resultsHeading: "有来源依据的东京资源",
  verifiedFacts: "经来源验证的事实",
  whyMatch: "有依据的说明",
  explanationUnavailable: "说明模型不可用或输出被拒绝，但有来源依据的资源事实仍然可用。",
  sourceFreshness: "来源与更新情况",
  sourceReportedLanguages: "来源明确报告的语言",
  openingHours: "来源公布的开放信息",
  accessNotes: "无障碍/访问说明",
  address: "位置",
  distance: "距离",
  notReported: "来源未报告",
  directions: "路线",
  officialPage: "官方网站",
  officialSource: "来源记录",
  call: "拨打电话",
  noMatch: "没有资源同时满足全部要求。",
  noMatchHint: "可以尝试邻近区域，或删除非必要限制后重新搜索。",
  clarification: "搜索前还需要确认一个信息。",
  unsupported: "该服务不在当前限定版 Tokyo 演示范围内。",
  modelFallback: "模型辅助不可用，因此 CarePath 保留确定性回退路径，并不会编造资源事实。",
  partialData: "部分官方记录没有语言、开放时间或访问说明。缺失字段会保持未知，不会被推断为已提供。",
  safetyTitle: "安全判断优先于资源排序",
  safetyEmergency: "此请求已暂停普通资源排序。",
  privacyNote: "无需注册账户或上传健康数据。Tokyo 路由不会持久保存搜索文本或精确坐标。",
  coreLink: "CarePath Core 评审版",
  freshness: {
    current: "按来源规则仍属当前数据",
    aging: "来源记录逐渐陈旧",
    stale: "来源记录已陈旧",
    unknown: "更新情况未知",
  },
  category: {
    healthcare: "医疗服务",
    cooling_shelter: "避暑/降温场所",
    public_health: "公共卫生",
    family_support: "育儿与家庭支持",
    women_support: "女性支持",
    mental_health_support: "心理健康支持",
  },
  examples: [
    {
      id: "healthcare",
      label: "可英语沟通的诊所",
      query: "我想在东京找一家附近可以用英语沟通的诊所。",
      municipality: "新宿区",
      municipalityLabel: "新宿区",
    },
    {
      id: "cooling",
      label: "指定避暑场所",
      query: "天气非常热，我想找一个附近的指定避暑场所。",
      municipality: "江東区",
      municipalityLabel: "江东区",
    },
    {
      id: "family",
      label: "育儿支持",
      query: "我在育儿方面遇到困难，但不知道应该联系东京的哪种公共支持服务。",
      municipality: "江東区",
      municipalityLabel: "江东区",
    },
  ],
};

export const TOKYO_COPY: Record<AppLocale, TokyoCopy> = {
  en: EN,
  ja: JA,
  zh: ZH,
};

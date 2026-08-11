import type { AppLocale } from "./resources";

type Translation = Record<AppLocale, string>;

const PHRASES: Translation[] = [
  { en: "Research prototype", zh: "研究原型", ja: "研究プロトタイプ" },
  {
    en: "Behaviour support, not medical care",
    zh: "健康行为支持，不替代医疗服务",
    ja: "健康行動の支援であり、医療行為ではありません",
  },
  {
    en: "CarePath does not diagnose conditions or change medication. Demo personas and built-in records are synthetic. Data-quality labels describe the records, not a medical state.",
    zh: "CarePath 不进行疾病诊断，也不会调整药物。演示用户和内置记录均为合成数据。数据质量标签描述的是记录质量，而不是医学状态。",
    ja: "CarePath は診断や薬の変更を行いません。デモペルソナと組み込み記録は合成データです。データ品質ラベルは記録の状態を示すもので、医学的状態を示すものではありません。",
  },
  { en: "Built-in demo persona", zh: "内置演示用户", ja: "組み込みデモペルソナ" },
  {
    en: "Switching persona resets this app journey so records cannot be accidentally mixed.",
    zh: "切换演示用户会重置当前体验流程，避免不同用户的记录被意外混合。",
    ja: "デモペルソナを切り替えると現在の操作フローがリセットされ、記録が誤って混在するのを防ぎます。",
  },
  {
    en: "Current persona data package is loaded.",
    zh: "当前演示用户的数据包已加载。",
    ja: "現在のデモペルソナのデータパッケージを読み込み済みです。",
  },
  { en: "API connection", zh: "API 连接", ja: "API 接続" },
  { en: "Checking /health…", zh: "正在检查 /health…", ja: "/health を確認中…" },
  {
    en: "Connection has not been checked.",
    zh: "尚未检查连接状态。",
    ja: "接続状態はまだ確認されていません。",
  },
  { en: "Check", zh: "检查", ja: "確認" },
  { en: "Not enough data", zh: "数据不足", ja: "データ不足" },
  { en: "Comparison unavailable", zh: "无法进行比较", ja: "比較できません" },
  {
    en: "Load a demo persona to calculate this summary.",
    zh: "请先加载演示用户以计算此摘要。",
    ja: "このサマリーを計算するにはデモペルソナを読み込んでください。",
  },
  { en: "Sleep duration", zh: "睡眠时长", ja: "睡眠時間" },
  { en: "Resting heart rate", zh: "静息心率", ja: "安静時心拍数" },
  { en: "Daily steps", zh: "每日步数", ja: "1日の歩数" },
  { en: "Stress score", zh: "压力评分", ja: "ストレススコア" },
  { en: "Sleep", zh: "睡眠", ja: "睡眠" },
  { en: "Resting HR", zh: "静息心率", ja: "安静時心拍" },
  { en: "Steps", zh: "步数", ja: "歩数" },
  { en: "Stress", zh: "压力", ja: "ストレス" },
  { en: "Data note:", zh: "数据说明：", ja: "データ注記：" },
  { en: "Fixed issues", zh: "已修复问题", ja: "修正済みの問題" },
  { en: "Skipped records", zh: "已跳过记录", ja: "スキップした記録" },
  { en: "Blocking errors", zh: "阻断错误", ja: "処理を停止したエラー" },
  {
    en: "No validation findings were reported.",
    zh: "未发现需要报告的校验问题。",
    ja: "報告すべき検証上の問題はありませんでした。",
  },
  {
    en: "Load demo data to view the raw series.",
    zh: "请加载演示数据以查看原始序列。",
    ja: "生の時系列を表示するにはデモデータを読み込んでください。",
  },
  {
    en: "No numeric observations are available in this range.",
    zh: "此时间范围内没有可用的数值观测。",
    ja: "この期間には数値観測データがありません。",
  },
  { en: "check", zh: "检查", ja: "確認" },
  {
    en: "Each mark is one raw daily observation. Missing days remain gaps; suspect records remain visible and are not smoothed away.",
    zh: "每个标记代表一条原始每日观测。缺失日期会保留为空缺；可疑记录仍然可见，不会被平滑处理隐藏。",
    ja: "各マークは1件の生の日次観測です。欠測日は空白のまま残り、疑わしい記録も表示され、平滑化で隠されません。",
  },
  {
    en: "No statement was returned for this section.",
    zh: "此部分未返回内容。",
    ja: "このセクションには回答文がありません。",
  },
  { en: "Citations:", zh: "引用：", ja: "引用：" },
  { en: "date unavailable", zh: "日期不可用", ja: "日付なし" },
  { en: "reliability", zh: "可靠性", ja: "信頼性" },
  { en: "Evidence ID:", zh: "证据 ID：", ja: "エビデンス ID：" },
  { en: "Record IDs:", zh: "记录 ID：", ja: "記録 ID：" },
  { en: "Hide exact chunk", zh: "收起原始证据片段", ja: "正確なチャンクを閉じる" },
  { en: "Show exact chunk", zh: "查看原始证据片段", ja: "正確なチャンクを表示" },
  { en: "Source ID:", zh: "来源 ID：", ja: "ソース ID：" },
  { en: "Retrieved:", zh: "检索日期：", ja: "取得日：" },
  {
    en: "Bounded Agent workflow",
    zh: "受约束的智能体工作流",
    ja: "制約付きエージェントワークフロー",
  },
  {
    en: "Only stage status is shown. Internal reasoning and raw chain-of-thought are never exposed.",
    zh: "仅显示各阶段状态。内部推理过程和原始思维链不会被展示。",
    ja: "表示するのは各段階の状態のみです。内部推論や生の思考過程は表示しません。",
  },
  { en: "Check safety", zh: "检查安全性", ja: "安全性を確認" },
  { en: "Analyse recent trends", zh: "分析近期趋势", ja: "最近の傾向を分析" },
  { en: "Retrieve evidence", zh: "检索证据", ja: "エビデンスを取得" },
  { en: "Compose verified plan", zh: "生成并验证计划", ja: "検証済みプランを作成" },

  { en: "Today dashboard", zh: "今日仪表板", ja: "今日のダッシュボード" },
  { en: "Today", zh: "今日", ja: "今日" },
  {
    en: "A neutral 7-day health-behaviour summary, a 30-day baseline and today's current plan action.",
    zh: "中立呈现近 7 天健康行为摘要、30 天基线以及今天的当前计划行动。",
    ja: "直近7日間の健康行動サマリー、30日間のベースライン、今日のプラン行動を中立的に表示します。",
  },
  { en: "Selected demo user", zh: "已选择的演示用户", ja: "選択中のデモユーザー" },
  { en: "API goals:", zh: "API 目标：", ja: "API 目標：" },
  { en: "timezone", zh: "时区", ja: "タイムゾーン" },
  { en: "Demo loaded", zh: "演示数据已加载", ja: "デモ読み込み済み" },
  { en: "Load demo", zh: "加载演示数据", ja: "デモを読み込む" },
  { en: "Refresh dashboard", zh: "刷新仪表板", ja: "ダッシュボードを更新" },
  { en: "Validating synthetic records…", zh: "正在校验合成记录…", ja: "合成記録を検証中…" },
  {
    en: "Recent 7 days vs 30-day baseline",
    zh: "近 7 天与 30 天基线对比",
    ja: "直近7日間と30日ベースラインの比較",
  },
  {
    en: "Values, units, date windows, coverage and reliability are returned by the API. Differences are descriptive, not diagnostic.",
    zh: "数值、单位、日期窗口、覆盖率和可靠性均由 API 返回。差异仅用于描述，不用于诊断。",
    ja: "値、単位、期間、カバレッジ、信頼性は API から返されます。差異は記述的なもので、診断を意味しません。",
  },
  { en: "Today's action", zh: "今日行动", ja: "今日のアクション" },
  { en: "Loading the current plan…", zh: "正在加载当前计划…", ja: "現在のプランを読み込み中…" },
  {
    en: "No current action is available yet.",
    zh: "目前还没有可用的行动。",
    ja: "現在利用できるアクションはまだありません。",
  },
  { en: "Data and safety notes", zh: "数据与安全说明", ja: "データと安全上の注意" },
  {
    en: '"Not enough data", coverage and reliability labels indicate data sufficiency only. CarePath does not use dashboard colour to label a person as healthy or unhealthy.',
    zh: "“数据不足”、覆盖率和可靠性标签仅表示数据充分程度。CarePath 不使用仪表板颜色将用户标记为健康或不健康。",
    ja: "「データ不足」、カバレッジ、信頼性のラベルはデータの十分性のみを示します。CarePath はダッシュボードの色で健康・不健康を判定しません。",
  },

  { en: "Longitudinal records", zh: "纵向记录", ja: "経時記録" },
  { en: "Health Data", zh: "健康数据", ja: "健康データ" },
  {
    en: "Inspect unsmoothed 7/30/60-day observations, data coverage and auditable CSV/JSON import reports.",
    zh: "查看未经平滑处理的 7/30/60 天观测、数据覆盖率以及可审计的 CSV/JSON 导入报告。",
    ja: "平滑化していない7/30/60日間の観測、データカバレッジ、監査可能なCSV/JSONインポートレポートを確認します。",
  },
  { en: "Built-in synthetic package", zh: "内置合成数据包", ja: "組み込み合成データパッケージ" },
  {
    en: "60 days across sleep, resting heart rate, steps and stress. The package contains structured missing periods and explicit suspect observations so the chart cannot hide them.",
    zh: "包含 60 天的睡眠、静息心率、步数和压力数据。数据包包含结构化缺失时段和明确标记的可疑观测，图表不会将其隐藏。",
    ja: "睡眠、安静時心拍数、歩数、ストレスの60日分のデータです。構造化された欠測期間と明示的な疑わしい観測を含み、チャートで隠されません。",
  },
  {
    en: "Synthetic package loaded",
    zh: "合成数据包已加载",
    ja: "合成データパッケージ読み込み済み",
  },
  { en: "Import selected persona", zh: "导入所选演示用户", ja: "選択したペルソナをインポート" },
  { en: "Validating and importing…", zh: "正在校验并导入…", ja: "検証してインポート中…" },
  { en: "CSV / JSON import", zh: "CSV / JSON 导入", ja: "CSV / JSON インポート" },
  {
    en: "Paste a standard CarePath CSV or project JSON package. The backend performs the same validation used by the API import endpoint and returns explicit repair, skip and blocking findings.",
    zh: "粘贴标准 CarePath CSV 或项目 JSON 数据包。后端会执行与 API 导入端点相同的校验，并明确返回修复、跳过和阻断结果。",
    ja: "標準のCarePath CSVまたはプロジェクトJSONパッケージを貼り付けます。バックエンドはAPIインポートと同じ検証を行い、修正、スキップ、停止理由を明示します。",
  },
  { en: "Checking import…", zh: "正在检查导入内容…", ja: "インポートを確認中…" },
  { en: "Raw longitudinal chart", zh: "原始纵向图表", ja: "生データの経時チャート" },
  {
    en: "Choose one metric and time range. No interpolation is applied between missing days.",
    zh: "选择一个指标和时间范围。缺失日期之间不会进行插值。",
    ja: "指標と期間を1つ選択します。欠測日の間に補間は行いません。",
  },
  {
    en: "Import a persona before requesting raw observations.",
    zh: "请先导入演示用户，再请求原始观测。",
    ja: "生の観測を取得する前にペルソナをインポートしてください。",
  },

  { en: "Evidence-grounded coach", zh: "基于证据的健康教练", ja: "エビデンスに基づくコーチ" },
  { en: "Coach", zh: "健康教练", ja: "コーチ" },
  {
    en: "Ask a health-behaviour question, inspect the bounded workflow and expand the exact evidence used around the answer.",
    zh: "提出健康行为问题，查看受约束的工作流，并展开回答所使用的具体证据。",
    ja: "健康行動について質問し、制約付きワークフローを確認し、回答に使われた具体的なエビデンスを展開できます。",
  },
  { en: "Ask CarePath", zh: "询问 CarePath", ja: "CarePath に質問" },
  {
    en: "Health behaviour coaching question",
    zh: "健康行为辅导问题",
    ja: "健康行動コーチングの質問",
  },
  {
    en: "Ask about recent changes and a realistic plan",
    zh: "询问近期变化和可执行的计划",
    ja: "最近の変化と現実的なプランについて質問",
  },
  { en: "Analyse and answer", zh: "分析并回答", ja: "分析して回答" },
  {
    en: "Load the selected synthetic persona first.",
    zh: "请先加载所选合成演示用户。",
    ja: "先に選択した合成ペルソナを読み込んでください。",
  },
  { en: "Safety:", zh: "安全级别：", ja: "安全性：" },
  { en: "Verifier:", zh: "验证器：", ja: "検証：" },
  { en: "not reported", zh: "未报告", ja: "未報告" },
  { en: "pending", zh: "等待中", ja: "保留中" },
  { en: "What I noticed", zh: "我注意到的情况", ja: "気づいたこと" },
  { en: "What the evidence suggests", zh: "证据提示", ja: "エビデンスが示すこと" },
  { en: "A realistic plan for this week", zh: "本周可执行的计划", ja: "今週の現実的なプラン" },
  {
    en: "No ordinary action plan was returned.",
    zh: "未返回常规行动计划。",
    ja: "通常のアクションプランは返されませんでした。",
  },
  {
    en: "When to seek professional help",
    zh: "何时寻求专业帮助",
    ja: "専門家に相談すべきタイミング",
  },
  { en: "What I am uncertain about", zh: "我仍不确定的部分", ja: "不確かな点" },
  {
    en: "No coaching answer has been requested yet.",
    zh: "尚未请求健康教练回答。",
    ja: "まだコーチング回答をリクエストしていません。",
  },
  { en: "Patient Evidence", zh: "用户证据", ja: "ユーザーエビデンス" },
  {
    en: "User-scoped measurements, tool facts and user-reported context remain separate from general guidance.",
    zh: "用户范围内的测量数据、工具事实和用户自述上下文与一般指南保持分离。",
    ja: "ユーザー固有の測定値、ツール由来の事実、自己申告の文脈は一般的なガイダンスと分離して扱います。",
  },
  {
    en: "Retrieving Patient Evidence…",
    zh: "正在检索用户证据…",
    ja: "ユーザーエビデンスを取得中…",
  },
  {
    en: "No Patient Evidence matched this bounded window.",
    zh: "此限定时间窗口内没有匹配的用户证据。",
    ja: "この限定期間に一致するユーザーエビデンスはありません。",
  },
  { en: "External Evidence", zh: "外部证据", ja: "外部エビデンス" },
  {
    en: "Expand a result to inspect the exact guideline chunk, organisation, source date and retrieval date.",
    zh: "展开结果可查看具体指南片段、机构、来源日期和检索日期。",
    ja: "結果を展開すると、正確なガイドラインチャンク、組織、資料の日付、取得日を確認できます。",
  },
  {
    en: "Retrieving guideline evidence…",
    zh: "正在检索指南证据…",
    ja: "ガイドラインのエビデンスを取得中…",
  },
  {
    en: "No external guideline chunk matched this question.",
    zh: "没有与此问题匹配的外部指南片段。",
    ja: "この質問に一致する外部ガイドラインのチャンクはありません。",
  },
  { en: "Final response citation map", zh: "最终回答引用映射", ja: "最終回答の引用マップ" },
  { en: "Record/source IDs:", zh: "记录/来源 ID：", ja: "記録/ソース ID：" },

  { en: "Account & privacy", zh: "账户与隐私", ja: "アカウントとプライバシー" },
  {
    en: "Account optional · anonymous use remains available.",
    zh: "账户可选 · 仍可匿名使用。",
    ja: "アカウントは任意です · 匿名でも利用できます。",
  },
  { en: "Private mode is on.", zh: "隐私模式已开启。", ja: "プライベートモードはオンです。" },
  { en: "Standard storage mode.", zh: "标准存储模式。", ja: "標準ストレージモードです。" },
  { en: "Hide", zh: "收起", ja: "閉じる" },
  { en: "Manage", zh: "管理", ja: "管理" },
  { en: "Optional account", zh: "可选账户", ja: "任意のアカウント" },
  {
    en: "Signing in is never required. An account lets CarePath associate imported data, plans and feedback with the same user so they can be continued later.",
    zh: "登录并非必需。账户可以让 CarePath 将导入的数据、计划和反馈关联到同一用户，以便之后继续使用。",
    ja: "サインインは必須ではありません。アカウントを使うと、インポートしたデータ、プラン、フィードバックを同じユーザーに関連付け、後から継続できます。",
  },
  { en: "Checking account configuration…", zh: "正在检查账户配置…", ja: "アカウント設定を確認中…" },
  {
    en: "Account sign-in is not configured on this deployment yet. You can continue anonymously and use Private mode now.",
    zh: "当前部署尚未配置账户登录。你仍可匿名继续使用，并可立即使用隐私模式。",
    ja: "このデプロイではアカウントサインインはまだ設定されていません。匿名のまま続行し、プライベートモードを利用できます。",
  },
  { en: "Account email", zh: "账户邮箱", ja: "アカウントのメールアドレス" },
  { en: "Email", zh: "邮箱", ja: "メールアドレス" },
  { en: "Account password", zh: "账户密码", ja: "アカウントのパスワード" },
  { en: "Password", zh: "密码", ja: "パスワード" },
  { en: "Sign in", zh: "登录", ja: "サインイン" },
  { en: "Create account", zh: "创建账户", ja: "アカウントを作成" },
  { en: "Continue with Google", zh: "使用 Google 继续", ja: "Google で続行" },
  { en: "Use my saved data", zh: "使用我保存的数据", ja: "保存済みデータを使用" },
  {
    en: "No saved health profile is attached to this account yet. Import your data once to make it available on later sign-ins.",
    zh: "此账户目前还没有保存的健康档案。导入一次数据后，即可在之后登录时继续使用。",
    ja: "このアカウントにはまだ保存済みの健康プロフィールがありません。一度データをインポートすると、次回以降のサインインで利用できます。",
  },
  { en: "Sign out", zh: "退出登录", ja: "サインアウト" },
  { en: "Private mode", zh: "隐私模式", ja: "プライベートモード" },
  {
    en: "Private mode creates an isolated temporary workspace in server memory. Health records, journal content, plans, feedback and coaching interactions are not written to the persistent CarePath database. Exiting Private mode destroys the workspace; inactive sessions also expire after",
    zh: "隐私模式会在服务器内存中创建隔离的临时工作区。健康记录、日记内容、计划、反馈和健康教练交互不会写入 CarePath 持久数据库。退出隐私模式会销毁该工作区；非活动会话也会在",
    ja: "プライベートモードではサーバーメモリ上に分離された一時ワークスペースを作成します。健康記録、日記、プラン、フィードバック、コーチングのやり取りはCarePathの永続データベースには書き込まれません。プライベートモードを終了するとワークスペースは破棄され、非アクティブなセッションも",
  },
  { en: "minutes.", zh: "分钟后过期。", ja: "分後に期限切れになります。" },
  {
    en: "Turning Private mode on or off starts a clean journey. Load a built-in persona or import data after switching modes.",
    zh: "开启或关闭隐私模式都会开始一个全新的体验流程。切换模式后，请重新加载内置演示用户或导入数据。",
    ja: "プライベートモードをオンまたはオフにすると新しい操作フローが始まります。切り替え後に組み込みペルソナを読み込むか、データをインポートしてください。",
  },
  { en: "Exit Private mode", zh: "退出隐私模式", ja: "プライベートモードを終了" },
  { en: "Turn on Private mode", zh: "开启隐私模式", ja: "プライベートモードをオン" },

  { en: "Longitudinal adaptation", zh: "长期自适应", ja: "長期的な適応" },
  { en: "Plan & History", zh: "计划与历史", ja: "プランと履歴" },
  {
    en: "Review the active week, choose a lighter alternative when needed, record completion reasons, and trace how later plan versions change after feedback.",
    zh: "查看当前一周计划，在需要时选择更轻量的替代方案，记录完成情况与原因，并追踪后续计划版本如何根据反馈变化。",
    ja: "現在の1週間を確認し、必要に応じてより軽い選択肢を選び、完了理由を記録し、フィードバック後に後続のプランがどう変化したか追跡します。",
  },
  { en: "No active demo data", zh: "没有活动中的演示数据", ja: "有効なデモデータがありません" },
  {
    en: "Load a synthetic persona on Today or Health Data first.",
    zh: "请先在“今日”或“健康数据”中加载合成演示用户。",
    ja: "まず「今日」または「健康データ」で合成ペルソナを読み込んでください。",
  },
  { en: "Saving feedback…", zh: "正在保存反馈…", ja: "フィードバックを保存中…" },
  { en: "Feedback saved", zh: "反馈已保存", ja: "フィードバックを保存しました" },
  { en: "Current seven-day plan", zh: "当前七天计划", ja: "現在の7日間プラン" },
  { en: "Plan history and changes", zh: "计划历史与变化", ja: "プラン履歴と変更" },
  {
    en: "Versions are returned by the backend with stable plan IDs and supersession links. Action status changes remain traceable after feedback, and each version explains why its action difficulty or wording changed.",
    zh: "后端返回带有稳定计划 ID 和替代关系的版本。反馈后的行动状态变化仍可追溯，每个版本都会说明行动难度或措辞为何发生变化。",
    ja: "各バージョンは安定したプランIDと置換リンク付きでバックエンドから返されます。フィードバック後のアクション状態も追跡でき、各バージョンで難易度や文言が変わった理由を確認できます。",
  },
  { en: "difficulty", zh: "难度", ja: "難易度" },
  { en: "Lighter option:", zh: "更轻量方案：", ja: "より軽い選択肢：" },
  {
    en: "Reason, constraint or what made this difficult",
    zh: "原因、限制或困难之处",
    ja: "理由、制約、難しかった点",
  },
  { en: "Accept", zh: "接受", ja: "承認" },
  { en: "Choose lighter option", zh: "选择更轻量的方案", ja: "より軽い選択肢を選ぶ" },
  { en: "Reject", zh: "拒绝", ja: "却下" },
  { en: "Complete", zh: "完成", ja: "完了" },
  { en: "Partly done", zh: "部分完成", ja: "一部完了" },
  { en: "Not completed", zh: "未完成", ja: "未完了" },
  {
    en: "Add a reason before Reject or Not completed.",
    zh: "选择“拒绝”或“未完成”前请填写原因。",
    ja: "「却下」または「未完了」を選ぶ前に理由を入力してください。",
  },
  { en: "Why this version changed", zh: "此版本为何发生变化", ja: "このバージョンが変わった理由" },
  {
    en: "Earliest retained plan version.",
    zh: "保留的最早计划版本。",
    ja: "保持されている最も古いプランバージョンです。",
  },
  {
    en: "Earliest retained plan version; there is no earlier version to compare.",
    zh: "这是保留的最早计划版本，没有更早版本可供比较。",
    ja: "保持されている最も古いプランバージョンのため、比較できる以前のバージョンはありません。",
  },
  {
    en: "The number of retained actions changed between these plan versions.",
    zh: "这些计划版本之间保留的行动数量发生了变化。",
    ja: "これらのプランバージョン間で保持されるアクション数が変わりました。",
  },
  {
    en: "No material action, difficulty or feedback-status change from the previous version.",
    zh: "与上一版本相比，行动、难度或反馈状态没有实质变化。",
    ja: "前のバージョンから、アクション、難易度、フィードバック状態に重要な変化はありません。",
  },
  { en: "Rationale:", zh: "原因：", ja: "理由：" },

  {
    en: "Graduate student with a recent sleep and workload disruption.",
    zh: "最近睡眠和工作负荷受到影响的研究生。",
    ja: "最近、睡眠と作業負荷が乱れている大学院生。",
  },
  {
    en: "Remote worker with stable sleep but a recent drop in daily movement.",
    zh: "睡眠稳定但近期日常活动量下降的远程工作者。",
    ja: "睡眠は安定しているものの、最近の日常活動量が減っているリモートワーカー。",
  },
  {
    en: "Restore a regular evening routine while keeping activity manageable.",
    zh: "在保持活动量可承受的同时恢复规律晚间作息。",
    ja: "無理のない活動量を保ちながら、規則的な夜の習慣を取り戻す。",
  },
  {
    en: "Rebuild regular movement breaks without making the workday harder.",
    zh: "在不增加工作日负担的前提下恢复规律活动休息。",
    ja: "仕事日の負担を増やさず、定期的な運動休憩を取り戻す。",
  },
  {
    en: "I have felt more tired recently. What changed, and what is realistic this week?",
    zh: "我最近感觉更疲惫。发生了什么变化？这周做什么比较现实？",
    ja: "最近、以前より疲れを感じます。何が変わり、今週は何をするのが現実的ですか？",
  },
  {
    en: "My activity has dropped while working from home. What changed and what can I try?",
    zh: "居家办公后我的活动量下降了。发生了什么变化？我可以尝试什么？",
    ja: "在宅勤務で活動量が減りました。何が変わり、何を試せますか？",
  },
  {
    en: "Start winding down at the same time tonight.",
    zh: "今晚在固定时间开始放松准备入睡。",
    ja: "今夜は同じ時刻から就寝前のリラックスを始める。",
  },
  {
    en: "Take a 10-minute easy walk after dinner.",
    zh: "晚饭后轻松步行 10 分钟。",
    ja: "夕食後に10分間、無理のない散歩をする。",
  },
  {
    en: "Protect a 30-minute screen-free period before bed.",
    zh: "睡前留出 30 分钟不用屏幕。",
    ja: "就寝前に30分間、画面を見ない時間を確保する。",
  },
  {
    en: "Take a short movement break during the workday.",
    zh: "工作期间安排一次短暂活动休息。",
    ja: "仕事中に短い運動休憩を取る。",
  },
  {
    en: "Write down tomorrow's top three tasks before winding down.",
    zh: "放松前写下明天最重要的三件事。",
    ja: "就寝前のリラックスに入る前に、明日の重要な3つのタスクを書き出す。",
  },
  {
    en: "Repeat the 10-minute easy walk after dinner.",
    zh: "再次在晚饭后轻松步行 10 分钟。",
    ja: "夕食後の10分間の無理のない散歩をもう一度行う。",
  },
  {
    en: "Review which small routine felt easiest to keep.",
    zh: "回顾哪一个小习惯最容易坚持。",
    ja: "どの小さな習慣が最も続けやすかったか振り返る。",
  },
  {
    en: "Take a five-minute movement break after the first work block.",
    zh: "第一个工作时段后活动 5 分钟。",
    ja: "最初の作業ブロックの後に5分間の運動休憩を取る。",
  },
  {
    en: "Walk for 10 minutes after lunch.",
    zh: "午饭后步行 10 分钟。",
    ja: "昼食後に10分間歩く。",
  },
  {
    en: "Stand and stretch once during the afternoon.",
    zh: "下午起身伸展一次。",
    ja: "午後に一度立ってストレッチする。",
  },
  {
    en: "Place the next movement break on the calendar before work starts.",
    zh: "工作开始前把下一次活动休息加入日历。",
    ja: "仕事を始める前に次の運動休憩をカレンダーに入れる。",
  },
  {
    en: "Take a short walk before the final work block.",
    zh: "最后一个工作时段前短暂步行。",
    ja: "最後の作業ブロックの前に短い散歩をする。",
  },
  {
    en: "Repeat the easiest movement break from earlier in the week.",
    zh: "重复本周早些时候最容易完成的活动休息。",
    ja: "今週前半で最もやりやすかった運動休憩を繰り返す。",
  },
  {
    en: "Review which cue made movement easiest to remember.",
    zh: "回顾哪一种提示最能帮助自己记得活动。",
    ja: "どの合図が運動を思い出すのに最も役立ったか振り返る。",
  },
  {
    en: "A deliberately small behaviour-support action grounded in the selected synthetic demo context.",
    zh: "基于所选合成演示情境而刻意设计的小型健康行为支持行动。",
    ja: "選択した合成デモの文脈に基づき、意図的に小さく設計した健康行動支援アクション。",
  },
];

function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

const LOOKUP = new Map<string, Translation>();
for (const phrase of PHRASES) {
  LOOKUP.set(normalize(phrase.en), phrase);
  LOOKUP.set(normalize(phrase.zh), phrase);
  LOOKUP.set(normalize(phrase.ja), phrase);
}

const STATUS: Record<string, Translation> = {
  routine: { en: "routine", zh: "常规", ja: "通常" },
  caution: { en: "caution", zh: "谨慎", ja: "注意" },
  urgent: { en: "urgent", zh: "紧急", ja: "緊急" },
  proposed: { en: "proposed", zh: "待确认", ja: "提案中" },
  accepted: { en: "accepted", zh: "已接受", ja: "承認済み" },
  rejected: { en: "rejected", zh: "已拒绝", ja: "却下済み" },
  modified: { en: "modified", zh: "已调整", ja: "調整済み" },
  completed: { en: "completed", zh: "已完成", ja: "完了" },
  partially_completed: { en: "partially_completed", zh: "部分完成", ja: "一部完了" },
  not_completed: { en: "not_completed", zh: "未完成", ja: "未完了" },
  low: { en: "low", zh: "低", ja: "低" },
  medium: { en: "medium", zh: "中", ja: "中" },
  high: { en: "high", zh: "高", ja: "高" },
};

function dynamicTranslation(locale: AppLocale, value: string): string | null {
  const status = STATUS[value];
  if (status !== undefined) {
    return status[locale];
  }

  let match = /^Request (.+)$/.exec(value);
  if (match?.[1]) {
    return locale === "zh"
      ? `请求 ${match[1]}`
      : locale === "ja"
        ? `リクエスト ${match[1]}`
        : value;
  }
  match = /^Version (\d+)$/.exec(value);
  if (match?.[1]) {
    return locale === "zh"
      ? `版本 ${match[1]}`
      : locale === "ja"
        ? `バージョン ${match[1]}`
        : value;
  }
  match = /^Day (\d+)$/.exec(value);
  if (match?.[1]) {
    return locale === "zh" ? `第 ${match[1]} 天` : locale === "ja" ? `${match[1]}日目` : value;
  }
  match = /^(\d+) days$/.exec(value);
  if (match?.[1]) {
    return locale === "zh" ? `${match[1]} 天` : locale === "ja" ? `${match[1]}日間` : value;
  }
  match = /^(\d+)% coverage$/.exec(value);
  if (match?.[1]) {
    return locale === "zh"
      ? `覆盖率 ${match[1]}%`
      : locale === "ja"
        ? `カバレッジ ${match[1]}%`
        : value;
  }
  match = /^Connected · (.+)$/.exec(value);
  if (match?.[1]) {
    return locale === "zh"
      ? `已连接 · ${match[1]}`
      : locale === "ja"
        ? `接続済み · ${match[1]}`
        : value;
  }
  match = /^Loading (.+)…$/.exec(value);
  if (match?.[1]) {
    return locale === "zh"
      ? `正在加载${match[1]}…`
      : locale === "ja"
        ? `${match[1]}を読み込み中…`
        : value;
  }
  match = /^Import validation report · (.+)$/.exec(value);
  if (match?.[1]) {
    const translatedStatus = STATUS[match[1]]?.[locale] ?? match[1];
    return locale === "zh"
      ? `导入校验报告 · ${translatedStatus}`
      : locale === "ja"
        ? `インポート検証レポート · ${translatedStatus}`
        : value;
  }
  match = /^(\d+) received · (\d+) persisted · (.+)$/.exec(value);
  if (match?.[1] && match[2] && match[3]) {
    return locale === "zh"
      ? `收到 ${match[1]} 条 · 已保存 ${match[2]} 条 · ${match[3]}`
      : locale === "ja"
        ? `${match[1]}件受信 · ${match[2]}件保存 · ${match[3]}`
        : value;
  }
  match = /^Imported (.+)$/.exec(value);
  if (match?.[1]) {
    return locale === "zh"
      ? `导入时间 ${match[1]}`
      : locale === "ja"
        ? `インポート日時 ${match[1]}`
        : value;
  }
  match = /^(\d+) days · (.+) · (\d+) observed · (\d+) missing$/.exec(value);
  if (match?.[1] && match[2] && match[3] && match[4]) {
    return locale === "zh"
      ? `${match[1]} 天 · ${match[2]} · ${match[3]} 条观测 · ${match[4]} 天缺失`
      : locale === "ja"
        ? `${match[1]}日間 · ${match[2]} · ${match[3]}件観測 · ${match[4]}日欠測`
        : value;
  }
  match = /^Chunk (.+) · score (.+)$/.exec(value);
  if (match?.[1] && match[2]) {
    return locale === "zh"
      ? `片段 ${match[1]} · 得分 ${match[2]}`
      : locale === "ja"
        ? `チャンク ${match[1]} · スコア ${match[2]}`
        : value;
  }
  return null;
}

export function translateStaticText(locale: AppLocale, input: string): string {
  if (input.length === 0) {
    return input;
  }
  const leading = input.match(/^\s*/)?.[0] ?? "";
  const trailing = input.match(/\s*$/)?.[0] ?? "";
  const core = normalize(input);
  if (core.length === 0) {
    return input;
  }
  const exact = LOOKUP.get(core);
  const translated = exact?.[locale] ?? dynamicTranslation(locale, core);
  return translated === null || translated === undefined
    ? input
    : `${leading}${translated}${trailing}`;
}

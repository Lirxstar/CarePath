# ruff: noqa: RUF001
"""Deterministic user-visible Coach copy for supported interface languages."""

from __future__ import annotations

from backend.domain.models import Domain, MetricType


def language_key(language: str) -> str:
    lowered = language.casefold()
    if lowered.startswith("zh"):
        return "zh"
    if lowered.startswith("ja"):
        return "ja"
    return "en"


_METRIC_LABELS: dict[MetricType, dict[str, str]] = {
    MetricType.SLEEP_DURATION: {"en": "sleep duration", "zh": "睡眠时长", "ja": "睡眠時間"},
    MetricType.RESTING_HEART_RATE: {
        "en": "resting heart rate",
        "zh": "静息心率",
        "ja": "安静時心拍数",
    },
    MetricType.STEPS: {"en": "steps", "zh": "步数", "ja": "歩数"},
    MetricType.ACTIVE_MINUTES: {
        "en": "active minutes",
        "zh": "活动分钟数",
        "ja": "活動時間",
    },
    MetricType.STRESS_SCORE: {"en": "stress score", "zh": "压力评分", "ja": "ストレススコア"},
    MetricType.MOOD_SCORE: {"en": "mood score", "zh": "情绪评分", "ja": "気分スコア"},
    MetricType.ACTIVITY_CONFIDENCE: {
        "en": "activity confidence",
        "zh": "活动信心",
        "ja": "活動への自信",
    },
}

_DIRECTION_LABELS: dict[str, dict[str, str]] = {
    "increased": {"en": "increased", "zh": "上升", "ja": "増加"},
    "decreased": {"en": "decreased", "zh": "下降", "ja": "減少"},
    "stable": {"en": "was stable", "zh": "保持稳定", "ja": "安定"},
}


def _minute_article(minutes: int) -> str:
    return "an" if minutes in {8, 11, 18} else "a"


def metric_label(metric: MetricType | str, language: str) -> str:
    try:
        resolved = metric if isinstance(metric, MetricType) else MetricType(metric)
    except ValueError:
        return str(metric).replace("_", " ")
    return _METRIC_LABELS.get(resolved, {"en": resolved.value}).get(
        language_key(language), resolved.value
    )


def trend_statement(
    *,
    metric: MetricType | str,
    direction: str,
    current_mean: float,
    baseline_mean: float,
    percentage_change: float,
    language: str,
) -> str:
    key = language_key(language)
    label = metric_label(metric, key)
    direction_label = _DIRECTION_LABELS.get(direction, {}).get(key, direction.replace("_", " "))
    if key == "zh":
        return (
            f"{label}{direction_label}：近期平均值为 {current_mean:.2f}，"
            f"上一窗口为 {baseline_mean:.2f}（{percentage_change:+.1f}%）。"
        )
    if key == "ja":
        return (
            f"{label}は{direction_label}：直近の平均は {current_mean:.2f}、"
            f"前の期間は {baseline_mean:.2f}（{percentage_change:+.1f}%）です。"
        )
    return (
        f"{label} {direction_label}: recent mean {current_mean:.2f} versus "
        f"{baseline_mean:.2f} in the previous window ({percentage_change:+.1f}%)."
    )


def data_gap_text(value: str, language: str) -> str:
    key = language_key(language)
    metric_raw, separator, window_raw = value.partition(":")
    if not separator or not window_raw.endswith("d"):
        return value
    days = window_raw[:-1]
    label = metric_label(metric_raw, key)
    if key == "zh":
        return f"{label}的近 {days} 天数据不足。"
    if key == "ja":
        return f"{label}の直近{days}日間のデータが不足しています。"
    return f"Available {label} data are limited for the recent {days}-day window."


def recent_data_limited_text(language: str) -> str:
    key = language_key(language)
    if key == "zh":
        return "近期可用数据有限，因此计划保持保守。"
    if key == "ja":
        return "最近利用できるデータが限られているため、プランを保守的にしています。"
    return "Recent data are limited, so the plan remains conservative."


def no_external_evidence_statement(language: str) -> str:
    key = language_key(language)
    if key == "zh":
        return "未使用匹配的外部指南证据；该行动保持在一般低风险健康行为支持的边界内。"
    if key == "ja":
        return (
            "一致する外部ガイドラインのエビデンスは使用していません。"
            "この行動は一般的な低リスクの健康行動支援の範囲内です。"
        )
    return (
        "No matching external guideline evidence was used; the action stays within the "
        "planner's general low-risk behaviour-support boundary."
    )


def external_evidence_statement(content: str, language: str) -> str:
    compact = " ".join(content.split())
    sentence = compact.split(".", 1)[0].strip()
    if not sentence:
        sentence = compact
    if len(sentence) > 220:
        sentence = f"{sentence[:217].rstrip()}..."
    key = language_key(language)
    if key == "zh":
        return f"检索到的指南原文指出：“{sentence}”"
    if key == "ja":
        return f"取得したガイドライン原文：「{sentence}」"
    return f"Retrieved guidance states: {sentence}."


def plan_action_description(
    *,
    domain: Domain,
    minutes: int,
    activity_limited: bool,
    language: str,
) -> str:
    key = language_key(language)
    if domain is Domain.SLEEP:
        if key == "zh":
            return f"在计划睡觉前，用 {minutes} 分钟完成一个固定的放松提示。"
        if key == "ja":
            return f"就寝予定時刻の前に、{minutes} 分間の一貫したクールダウン習慣を行います。"
        return (
            f"Use {minutes} minutes for a consistent wind-down cue before your intended "
            "sleep period."
        )
    if domain is Domain.PHYSICAL_ACTIVITY:
        if activity_limited:
            if key == "zh":
                return f"在已说明的活动限制范围内，选择 {minutes} 分钟舒适的活动。"
            if key == "ja":
                return f"申告済みの活動制限の範囲内で、{minutes} 分間の無理のない運動を選びます。"
            return (
                f"Choose {minutes} minutes of comfortable movement that stays within your "
                "stated activity constraints."
            )
        if key == "zh":
            return f"进行 {minutes} 分钟舒适步行，或进行等量的轻度活动。"
        if key == "ja":
            return f"{minutes} 分間の無理のない散歩、または同程度の軽い運動を行います。"
        return (
            f"Take {_minute_article(minutes)} {minutes}-minute comfortable walk "
            "or equivalent light movement break."
        )
    if domain is Domain.STRESS_MOOD:
        if key == "zh":
            return f"安排 {minutes} 分钟安静恢复时间，可使用节律呼吸或其他偏好的放松方式。"
        if key == "ja":
            return (
                f"{minutes} 分間の静かな回復時間を取り、"
                "ペース呼吸など好みの落ち着く方法を使います。"
            )
        return (
            f"Take {_minute_article(minutes)} {minutes}-minute quiet recovery break using "
            "paced breathing or another preferred calming routine."
        )
    if key == "zh":
        return f"用 {minutes} 分钟检查一个常用行走区域，清除可避免的绊倒风险。"
    if key == "ja":
        return f"{minutes} 分かけて、普段歩く場所の避けられるつまずき要因を確認します。"
    return (
        f"Spend {minutes} minutes checking one commonly used walking area for avoidable "
        "trip hazards."
    )


def plan_frequency(language: str, *, weekly: bool = False) -> str:
    key = language_key(language)
    if weekly:
        if key == "zh":
            return "连续七天，每天完成一个小行动"
        if key == "ja":
            return "7日間、毎日1つの小さな行動"
        return "one small action daily for seven days"
    if key == "zh":
        return "当天一次"
    if key == "ja":
        return "その日に1回"
    return "once that day"


def plan_follow_up(language: str) -> str:
    key = language_key(language)
    if key == "zh":
        return (
            "七天后回顾完成情况和舒适度；如果完成率较低，下个计划应进一步减量；"
            "任何与专业限制冲突或感觉不安全的行动都应暂停。"
        )
    if key == "ja":
        return (
            "7日後に実行状況と無理のなさを振り返り、実行率が低い場合は次のプランを軽くします。"
            "専門家からの制限と矛盾する、または安全でないと感じる行動は中止します。"
        )
    return (
        "Review completion and comfort after seven days; scale the next plan down "
        "if completion is low, and pause any action that conflicts with a professional "
        "restriction or feels unsafe."
    )


def plan_rationale(
    *,
    low_completion: bool,
    high_stress: bool,
    data_limited: bool,
    accepted_feedback: bool,
    evidence_grounded: bool,
    language: str,
) -> str:
    key = language_key(language)
    if key == "zh":
        reasons: list[str] = []
        if low_completion:
            reasons.append("近期结构化行动完成率较低，因此降低了行动强度")
        if high_stress:
            reasons.append("近期压力数据较高，因此保持较小负担")
        if data_limited:
            reasons.append("近期数据不完整，因此计划保持保守")
        if not reasons and accepted_feedback:
            reasons.append("近期已接受的反馈支持暂时保持当前行动规模，等待更多完成情况数据")
        if not reasons:
            reasons.append("行动规模根据现有用户背景和以往完成情况进行了调整")
        grounding = (
            "一般性指导得到检索到的外部证据支持"
            if evidence_grounded
            else "该建议明确标记为一般性的低风险健康行为指导"
        )
        return f"{'；'.join(reasons)}；{grounding}。"
    if key == "ja":
        reasons_ja: list[str] = []
        if low_completion:
            reasons_ja.append("最近の計画行動の実行率が低かったため、行動量を減らしました")
        if high_stress:
            reasons_ja.append("最近のストレスデータが高かったため、負担を小さくしました")
        if data_limited:
            reasons_ja.append("最近のデータが不十分なため、プランを保守的にしました")
        if not reasons_ja and accepted_feedback:
            reasons_ja.append(
                "最近受け入れられたフィードバックを踏まえ、"
                "実行データが増えるまでは現在の行動量を維持します"
            )
        if not reasons_ja:
            reasons_ja.append(
                "利用可能なユーザー状況とこれまでの実行履歴に合わせて行動量を調整しました"
            )
        grounding_ja = (
            "一般的なガイダンスは取得した外部エビデンスで支持されています"
            if evidence_grounded
            else "この提案は一般的な低リスクの健康行動ガイダンスとして明示されています"
        )
        return f"{'。'.join(reasons_ja)}。{grounding_ja}。"

    reasons_en: list[str] = []
    if low_completion:
        reasons_en.append("recent structured completion was low, so the action was reduced")
    if high_stress:
        reasons_en.append("recent stress data were high, so workload was kept small")
    if data_limited:
        reasons_en.append("recent data were incomplete, so the plan stays conservative")
    if not reasons_en and accepted_feedback:
        reasons_en.append(
            "recent accepted feedback supports maintaining the current action size until "
            "completion evidence is available"
        )
    if not reasons_en:
        reasons_en.append(
            "the action is scaled to the available user context and prior completion history"
        )
    grounding_en = (
        "general guidance is supported by retrieved external evidence"
        if evidence_grounded
        else "the suggestion is explicitly marked as general low-risk behavioural guidance"
    )
    return f"{' ; '.join(reasons_en)}; {grounding_en}."


def fallback_goal(domain: Domain, language: str) -> str:
    key = language_key(language)
    if domain is Domain.SLEEP:
        labels = {"en": "sleep", "zh": "睡眠", "ja": "睡眠"}
    elif domain is Domain.PHYSICAL_ACTIVITY:
        labels = {"en": "physical activity", "zh": "身体活动", "ja": "身体活動"}
    elif domain is Domain.STRESS_MOOD:
        labels = {"en": "stress mood", "zh": "压力与情绪", "ja": "ストレスと気分"}
    else:
        labels = {"en": "fall safety", "zh": "跌倒预防", "ja": "転倒予防"}
    label = labels[key]
    if key == "zh":
        return f"建立可持续的{label}习惯"
    if key == "ja":
        return f"持続可能な{label}習慣を作る"
    return f"Build a sustainable {label} routine"

from backend.domain.models import Domain, MetricType
from backend.localization import (
    data_gap_text,
    no_external_evidence_statement,
    plan_action_description,
    plan_follow_up,
    plan_frequency,
    plan_rationale,
    trend_statement,
)


def test_chinese_dynamic_coach_copy_is_localized() -> None:
    assert (
        trend_statement(
            metric=MetricType.SLEEP_DURATION,
            direction="decreased",
            current_mean=6.38,
            baseline_mean=7.60,
            percentage_change=-16.0,
            language="zh",
        )
        == "睡眠时长下降：近期平均值为 6.38，上一窗口为 7.60（-16.0%）。"
    )
    assert "计划睡觉前" in plan_action_description(
        domain=Domain.SLEEP, minutes=12, activity_limited=False, language="zh"
    )
    assert plan_frequency("zh") == "当天一次"
    assert "七天后" in plan_follow_up("zh")
    assert "一般性的低风险" in plan_rationale(
        low_completion=False,
        high_stress=False,
        data_limited=False,
        accepted_feedback=False,
        evidence_grounded=False,
        language="zh",
    )
    assert data_gap_text("sleep_duration:7d", "zh") == "睡眠时长的近 7 天数据不足。"
    assert "未使用匹配的外部指南证据" in no_external_evidence_statement("zh")


def test_japanese_dynamic_coach_copy_is_localized() -> None:
    statement = trend_statement(
        metric=MetricType.STRESS_SCORE,
        direction="increased",
        current_mean=6.2,
        baseline_mean=4.1,
        percentage_change=51.2,
        language="ja",
    )
    assert "ストレススコア" in statement
    assert "増加" in statement
    assert "就寝予定時刻" in plan_action_description(
        domain=Domain.SLEEP, minutes=8, activity_limited=False, language="ja"
    )
    assert plan_frequency("ja", weekly=True) == "7日間、毎日1つの小さな行動"

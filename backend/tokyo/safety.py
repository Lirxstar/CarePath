# ruff: noqa: E501, RUF001
"""Deterministic CP-205 safety and privacy boundary for CarePath Tokyo.

Safety classification runs before resource lookup or model use. Emergency and
professional-help facts are frozen to authoritative Tokyo sources and rendered
locally in English, Japanese, or Chinese.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import RiskLevel
from backend.safety.triage import PolicyFlag, triage_safety
from backend.tokyo.journeys import InterfaceLanguage


class TokyoSafetyDisposition(StrEnum):
    ROUTINE_NAVIGATION = "routine_navigation"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    URGENT_PROFESSIONAL_HELP = "urgent_professional_help"
    EMERGENCY_ESCALATION = "emergency_escalation"


class TokyoSafetyReference(BaseModel):
    """Versioned authoritative reference for one safety-critical fact set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    title: str
    publisher: str
    canonical_url: str
    retrieved_at: date
    source_as_of: date | None = None


class TokyoPrivacyBoundary(BaseModel):
    """Explicit retention contract for the Tokyo primary journey."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    precise_location_use: Literal["current_request_only"] = "current_request_only"
    precise_location_persisted: Literal[False] = False
    free_text_persisted_by_tokyo_route: Literal[False] = False
    longitudinal_health_history_required: Literal[False] = False


class TokyoSafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: TokyoSafetyDisposition
    bypass_resource_navigation: bool
    message: str
    matched_rule_ids: tuple[str, ...] = ()
    policy_flags: tuple[PolicyFlag, ...] = ()
    references: tuple[TokyoSafetyReference, ...] = ()
    privacy: TokyoPrivacyBoundary = Field(default_factory=TokyoPrivacyBoundary)


class TokyoSafetyBoundaryResponse(BaseModel):
    """Returned instead of ordinary ranking when CP-205 blocks navigation."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["safety_boundary"] = "safety_boundary"
    safety: TokyoSafetyDecision


AMBULANCE_119_REFERENCE = TokyoSafetyReference(
    source_id="tokyo-health-ambulance-119",
    title="How to call an ambulance",
    publisher="東京都保健医療局",
    canonical_url=(
        "https://www.hokeniryo.metro.tokyo.lg.jp/iryo/iryo_hoken/medical_info_eng/emergency_call"
    ),
    retrieved_at=date(2026, 8, 12),
    source_as_of=date(2023, 1, 1),
)

EMERGENCY_CONSULTATION_7119_REFERENCE = TokyoSafetyReference(
    source_id="tokyo-fire-emergency-consultation-7119",
    title="東京消防庁救急相談センター",
    publisher="東京消防庁",
    canonical_url="https://www.tfd.metro.tokyo.lg.jp/lfe/kyuu_adv/soudan-center.html",
    retrieved_at=date(2026, 8, 12),
)

POLICE_110_REFERENCE = TokyoSafetyReference(
    source_id="tokyo-police-emergency-110",
    title="For Visitors to Tokyo",
    publisher="警視庁",
    canonical_url=(
        "https://www.keishicho.metro.tokyo.lg.jp/multilingual/english/"
        "safe_society/victim_of_crime/ninpo.html"
    ),
    retrieved_at=date(2026, 8, 12),
    source_as_of=date(2026, 5, 22),
)

HEAT_SAFETY_REFERENCE = TokyoSafetyReference(
    source_id="tokyo-fire-heat-safety",
    title="熱中症に注意",
    publisher="東京消防庁",
    canonical_url="https://www.tfd.metro.tokyo.lg.jp/lfe/nichijo/heat/teate.html",
    retrieved_at=date(2026, 8, 12),
)


_HEAT_CONTEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:heat|hot|heatstroke|heat stroke|overheated)\b",
        r"熱中症|猛暑|暑い|暑さ|高温",
        r"热中暑|中暑|炎热|高温|天气很热|天气非常热",
    )
)
_HEAT_EMERGENCY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:cannot|can't|unable to) (?:walk|stand|move)\b",
        r"\b(?:passed out|fainted|unconscious|unresponsive)\b",
        r"\b(?:confused|disoriented|acting strangely)\b",
        r"歩けない|立てない|動けない|意識がない|反応がない|言動がおかしい",
        r"走不了|不能走|无法走|站不住|不能站|无法站|动不了|无法活动|失去意识|昏迷|意识混乱|言行异常",
    )
)
_UNCERTAIN_SERIOUS_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:not sure|don't know|do not know).{0,45}(?:emergency|serious|dangerous)\b",
        r"\b(?:feel very unwell|something is seriously wrong).{0,40}\b",
        r"不知道.{0,20}(?:是不是|是否).{0,10}(?:急症|紧急|严重)|说不清.{0,15}(?:很严重|很不舒服)",
        r"(?:救急|緊急).{0,20}(?:か分からない|かわからない)|ひどく具合が悪い.{0,20}(?:説明できない|よく分からない)",
    )
)
_VIOLENCE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:kill|seriously hurt|attack) someone\b",
        r"\b(?:shoot|stab) someone\b",
        r"杀(?:了)?别人|伤害别人|袭击别人|捅别人|枪击别人",
        r"誰かを殺|誰かを傷つけ|誰かを襲|刺すつもり|撃つつもり",
    )
)
_HEAT_MILD_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:dizzy|dizziness|fatigue|tired|headache|nausea)\b",
        r"めまい|ふらつき|疲労|だるい|頭痛|吐き気",
        r"头晕|疲劳|乏力|头痛|恶心",
    )
)

_PROFESSIONAL_HELP_FLAGS = {
    PolicyFlag.PERSISTENT_WORSENING,
    PolicyFlag.RECURRENT_FALL,
    PolicyFlag.SELF_HARM,
    PolicyFlag.DIAGNOSIS_REQUEST,
    PolicyFlag.MEDICATION_REQUEST,
    PolicyFlag.ACTIVITY_RESTRICTION,
}
_UNCERTAINTY_FLAGS = {PolicyFlag.DATA_QUALITY, PolicyFlag.UNCERTAINTY}


def assess_tokyo_safety(
    query: str,
    interface_language: InterfaceLanguage,
) -> TokyoSafetyDecision:
    """Classify a Tokyo request before any model call or resource ranking."""

    core = triage_safety(query)
    normalized = _normalize(query)
    heat_context = _matches_any(normalized, _HEAT_CONTEXT_PATTERNS)
    heat_emergency = heat_context and _matches_any(normalized, _HEAT_EMERGENCY_PATTERNS)

    matched_rule_ids = list(core.matched_rule_ids)
    policy_flags = core.policy_flags

    if core.risk_level is RiskLevel.URGENT or heat_emergency:
        if heat_emergency and "TOKYO-URG-HEAT-001" not in matched_rule_ids:
            matched_rule_ids.append("TOKYO-URG-HEAT-001")
        violence = _matches_any(normalized, _VIOLENCE_PATTERNS)
        references = [AMBULANCE_119_REFERENCE]
        if heat_context:
            references.append(HEAT_SAFETY_REFERENCE)
        if violence:
            references.append(POLICE_110_REFERENCE)
        return TokyoSafetyDecision(
            disposition=TokyoSafetyDisposition.EMERGENCY_ESCALATION,
            bypass_resource_navigation=True,
            message=_emergency_message(interface_language, violence=violence),
            matched_rule_ids=tuple(matched_rule_ids),
            policy_flags=policy_flags,
            references=_dedupe_references(references),
        )

    flags = set(core.policy_flags)
    if core.risk_level is RiskLevel.CAUTION:
        if flags & _UNCERTAINTY_FLAGS:
            return TokyoSafetyDecision(
                disposition=TokyoSafetyDisposition.INSUFFICIENT_INFORMATION,
                bypass_resource_navigation=True,
                message=_insufficient_message(interface_language),
                matched_rule_ids=core.matched_rule_ids,
                policy_flags=core.policy_flags,
                references=(
                    EMERGENCY_CONSULTATION_7119_REFERENCE,
                    AMBULANCE_119_REFERENCE,
                ),
            )
        if flags & _PROFESSIONAL_HELP_FLAGS:
            return TokyoSafetyDecision(
                disposition=TokyoSafetyDisposition.URGENT_PROFESSIONAL_HELP,
                bypass_resource_navigation=True,
                message=_professional_help_message(interface_language),
                matched_rule_ids=core.matched_rule_ids,
                policy_flags=core.policy_flags,
                references=(
                    EMERGENCY_CONSULTATION_7119_REFERENCE,
                    AMBULANCE_119_REFERENCE,
                ),
            )

    if _matches_any(normalized, _UNCERTAIN_SERIOUS_PATTERNS):
        return TokyoSafetyDecision(
            disposition=TokyoSafetyDisposition.INSUFFICIENT_INFORMATION,
            bypass_resource_navigation=True,
            message=_insufficient_message(interface_language),
            matched_rule_ids=("TOKYO-UNC-001",),
            references=(
                EMERGENCY_CONSULTATION_7119_REFERENCE,
                AMBULANCE_119_REFERENCE,
            ),
        )

    references: tuple[TokyoSafetyReference, ...] = ()
    message = _routine_message(interface_language)
    if heat_context and _matches_any(normalized, _HEAT_MILD_PATTERNS):
        references = (HEAT_SAFETY_REFERENCE, AMBULANCE_119_REFERENCE)
        message = _heat_routine_message(interface_language)
    return TokyoSafetyDecision(
        disposition=TokyoSafetyDisposition.ROUTINE_NAVIGATION,
        bypass_resource_navigation=False,
        message=message,
        references=references,
    )


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _matches_any(value: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(value) is not None for pattern in patterns)


def _dedupe_references(
    references: list[TokyoSafetyReference],
) -> tuple[TokyoSafetyReference, ...]:
    by_id = {reference.source_id: reference for reference in references}
    return tuple(by_id[source_id] for source_id in by_id)


def _routine_message(language: InterfaceLanguage) -> str:
    return {
        InterfaceLanguage.EN: "No safety boundary was triggered; bounded resource navigation may continue.",
        InterfaceLanguage.JA: "安全上の中断条件は検出されませんでした。範囲を限定したリソース案内を続行できます。",
        InterfaceLanguage.ZH: "未触发安全中断条件，可以继续进行受限的公共资源导航。",
    }[language]


def _heat_routine_message(language: InterfaceLanguage) -> str:
    return {
        InterfaceLanguage.EN: (
            "Resource navigation may continue. For heat-related discomfort, move to a cooler place, "
            "cool the body, and take fluids if you can. If severe warning signs develop, use 119."
        ),
        InterfaceLanguage.JA: (
            "リソース案内を続行できます。暑さによる体調不良では、涼しい場所へ移動し、体を冷やし、"
            "可能であれば水分を取ってください。重い症状が出た場合は119を利用してください。"
        ),
        InterfaceLanguage.ZH: (
            "可以继续资源导航。若因炎热出现不适，请先移到凉爽处、给身体降温，并在能够饮水时补充水分。"
            "如果出现严重警示症状，请拨打119。"
        ),
    }[language]


def _emergency_message(language: InterfaceLanguage, *, violence: bool) -> str:
    base = {
        InterfaceLanguage.EN: (
            "This request contains signs that may require immediate emergency help. CarePath Tokyo "
            "will not diagnose the situation or rank ordinary resources. For a medical emergency "
            "in Tokyo, call 119 now."
        ),
        InterfaceLanguage.JA: (
            "直ちに緊急対応が必要な可能性のある内容が含まれています。CarePath Tokyo は診断や通常の"
            "リソース順位付けを行いません。東京都内の医療上の緊急時は、今すぐ119番に電話してください。"
        ),
        InterfaceLanguage.ZH: (
            "该请求包含可能需要立即紧急处理的情况。CarePath Tokyo 不会进行诊断，也不会继续普通资源排名。"
            "在东京遇到医疗紧急情况时，请立即拨打119。"
        ),
    }[language]
    if not violence:
        return base
    suffix = {
        InterfaceLanguage.EN: " If there is an immediate crime or violence emergency, call 110.",
        InterfaceLanguage.JA: " 犯罪や暴力の緊急事態が目前にある場合は110番に電話してください。",
        InterfaceLanguage.ZH: " 如果存在正在发生的犯罪或暴力紧急情况，请拨打110。",
    }[language]
    return base + suffix


def _professional_help_message(language: InterfaceLanguage) -> str:
    return {
        InterfaceLanguage.EN: (
            "CarePath Tokyo cannot diagnose a condition or tell you to start, stop, or change "
            "medication. This request should pause ordinary resource ranking and use professional "
            "assessment. If you are unsure whether you need a hospital or ambulance in Tokyo, call "
            "#7119, which operates 24 hours a day. If the situation becomes severe, call 119."
        ),
        InterfaceLanguage.JA: (
            "CarePath Tokyo は診断や、薬の開始・中止・変更の指示を行いません。通常のリソース順位付けを"
            "中断し、専門家による評価を優先してください。病院へ行くべきか救急車を呼ぶべきか迷う場合は、"
            "24時間対応の#7119に相談してください。重い状態になった場合は119番に電話してください。"
        ),
        InterfaceLanguage.ZH: (
            "CarePath Tokyo 不会诊断疾病，也不会指示开始、停止或更改药物。此类请求应暂停普通资源排名，"
            "优先由专业人员评估。如果不确定在东京应去医院还是叫救护车，可拨打24小时服务的#7119；"
            "若情况变得严重，请拨打119。"
        ),
    }[language]


def _insufficient_message(language: InterfaceLanguage) -> str:
    return {
        InterfaceLanguage.EN: (
            "There is not enough information to safely rank an ordinary service. CarePath Tokyo "
            "will preserve that uncertainty rather than reassure or diagnose. If you are unsure "
            "whether this is an emergency in Tokyo, call #7119; if the situation is severe, call 119."
        ),
        InterfaceLanguage.JA: (
            "通常のサービスを安全に順位付けするには情報が不足しています。CarePath Tokyo は安心させる"
            "断定や診断をせず、不確実性を明示します。緊急かどうか迷う場合は#7119に相談し、重い状態なら"
            "119番に電話してください。"
        ),
        InterfaceLanguage.ZH: (
            "目前信息不足以安全地进行普通服务排名。CarePath Tokyo 会保留这种不确定性，而不会给出安慰性"
            "断言或诊断。如果不确定是否属于紧急情况，可在东京拨打#7119；若情况严重，请拨打119。"
        ),
    }[language]

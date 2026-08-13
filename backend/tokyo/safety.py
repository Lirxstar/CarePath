# ruff: noqa: E501, RUF001
"""Deterministic CP-205 safety and privacy boundary for CarePath Tokyo.

Safety classification runs before resource lookup or model use. Emergency and
professional-help facts are frozen to authoritative Tokyo sources and rendered
locally in English, Japanese, or Chinese. Safety-critical source facts are
re-evaluated on every request so stale or unavailable verification cannot remain
actionable indefinitely.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import RiskLevel
from backend.safety.triage import PolicyFlag, triage_safety
from backend.tokyo.journeys import InterfaceLanguage


class TokyoSafetyDisposition(StrEnum):
    ROUTINE_NAVIGATION = "routine_navigation"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    URGENT_PROFESSIONAL_HELP = "urgent_professional_help"
    EMERGENCY_ESCALATION = "emergency_escalation"


class TokyoSafetyAvailabilityState(StrEnum):
    VERIFIED_AVAILABLE = "verified_available"
    UNKNOWN = "unknown"
    VERIFIED_UNAVAILABLE = "verified_unavailable"


class TokyoSafetyEligibilityState(StrEnum):
    VERIFIED_APPLICABLE = "verified_applicable"
    UNKNOWN = "unknown"
    VERIFIED_INAPPLICABLE = "verified_inapplicable"


class TokyoSafetyVerificationStatus(StrEnum):
    UNEVALUATED = "unevaluated"
    VERIFIED_CURRENT = "verified_current"
    EXPIRED = "expired"
    AVAILABILITY_UNKNOWN = "availability_unknown"
    VERIFIED_UNAVAILABLE = "verified_unavailable"
    ELIGIBILITY_UNKNOWN = "eligibility_unknown"
    VERIFIED_INAPPLICABLE = "verified_inapplicable"
    SUPERSEDED = "superseded"


class TokyoSafetyReference(BaseModel):
    """Versioned authoritative reference for one safety-critical fact set.

    ``valid_until`` is a CarePath revalidation deadline, not an assertion that the
    underlying official source expires on that date. ``verification_status`` and
    ``currently_verified_actionable`` are recalculated at request time and default
    fail-closed so an unevaluated frozen object cannot be presented as current.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    title: str
    publisher: str
    canonical_url: str
    retrieved_at: date
    source_as_of: date | None = None
    valid_until: date
    service_hours: str | None = None
    eligibility: str | None = None
    languages: tuple[str, ...] | None = None
    availability_state: TokyoSafetyAvailabilityState
    eligibility_state: TokyoSafetyEligibilityState
    superseded_by_source_id: str | None = None
    verification_status: TokyoSafetyVerificationStatus = TokyoSafetyVerificationStatus.UNEVALUATED
    currently_verified_actionable: bool = False


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
    valid_until=date(2027, 8, 12),
    availability_state=TokyoSafetyAvailabilityState.VERIFIED_AVAILABLE,
    eligibility_state=TokyoSafetyEligibilityState.VERIFIED_APPLICABLE,
)

EMERGENCY_CONSULTATION_7119_REFERENCE = TokyoSafetyReference(
    source_id="tokyo-fire-emergency-consultation-7119",
    title="東京消防庁救急相談センター",
    publisher="東京消防庁",
    canonical_url="https://www.tfd.metro.tokyo.lg.jp/lfe/kyuu_adv/soudan-center.html",
    retrieved_at=date(2026, 8, 12),
    valid_until=date(2026, 11, 10),
    service_hours="24 hours / 365 days",
    availability_state=TokyoSafetyAvailabilityState.VERIFIED_AVAILABLE,
    eligibility_state=TokyoSafetyEligibilityState.VERIFIED_APPLICABLE,
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
    valid_until=date(2027, 8, 12),
    availability_state=TokyoSafetyAvailabilityState.VERIFIED_AVAILABLE,
    eligibility_state=TokyoSafetyEligibilityState.VERIFIED_APPLICABLE,
)

HEAT_SAFETY_REFERENCE = TokyoSafetyReference(
    source_id="tokyo-fire-heat-safety",
    title="熱中症に注意",
    publisher="東京消防庁",
    canonical_url="https://www.tfd.metro.tokyo.lg.jp/lfe/nichijo/heat/teate.html",
    retrieved_at=date(2026, 8, 12),
    valid_until=date(2026, 9, 30),
    availability_state=TokyoSafetyAvailabilityState.VERIFIED_AVAILABLE,
    eligibility_state=TokyoSafetyEligibilityState.VERIFIED_APPLICABLE,
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
_TOKYO_TIME_ZONE = ZoneInfo("Asia/Tokyo")


def assess_tokyo_safety(
    query: str,
    interface_language: InterfaceLanguage,
    *,
    as_of: date | None = None,
) -> TokyoSafetyDecision:
    """Classify a Tokyo request before any model call or resource ranking.

    Safety disposition is determined independently from reference freshness. A
    stale, unknown, unavailable, inapplicable, or superseded preferred reference
    can remove only the action driven by that fact; it can never downgrade an
    emergency or urgent disposition into ordinary resource navigation.
    """

    effective_date = as_of or _tokyo_today()
    ambulance_119 = _evaluate_reference(AMBULANCE_119_REFERENCE, effective_date)
    consultation_7119 = _evaluate_reference(
        EMERGENCY_CONSULTATION_7119_REFERENCE,
        effective_date,
    )
    police_110 = _evaluate_reference(POLICE_110_REFERENCE, effective_date)
    heat_safety = _evaluate_reference(HEAT_SAFETY_REFERENCE, effective_date)

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
        emergency_references = [ambulance_119]
        if heat_context:
            emergency_references.append(heat_safety)
        if violence:
            emergency_references.append(police_110)
        return TokyoSafetyDecision(
            disposition=TokyoSafetyDisposition.EMERGENCY_ESCALATION,
            bypass_resource_navigation=True,
            message=_emergency_message(
                interface_language,
                ambulance_119=_reference_is_actionable(ambulance_119),
                police_110=violence and _reference_is_actionable(police_110),
                violence=violence,
            ),
            matched_rule_ids=tuple(matched_rule_ids),
            policy_flags=policy_flags,
            references=_dedupe_references(emergency_references),
        )

    flags = set(core.policy_flags)
    if core.risk_level is RiskLevel.CAUTION:
        if flags & _UNCERTAINTY_FLAGS:
            return TokyoSafetyDecision(
                disposition=TokyoSafetyDisposition.INSUFFICIENT_INFORMATION,
                bypass_resource_navigation=True,
                message=_insufficient_message(
                    interface_language,
                    consultation_7119=_reference_is_actionable(consultation_7119),
                    ambulance_119=_reference_is_actionable(ambulance_119),
                ),
                matched_rule_ids=core.matched_rule_ids,
                policy_flags=core.policy_flags,
                references=(consultation_7119, ambulance_119),
            )
        if flags & _PROFESSIONAL_HELP_FLAGS:
            return TokyoSafetyDecision(
                disposition=TokyoSafetyDisposition.URGENT_PROFESSIONAL_HELP,
                bypass_resource_navigation=True,
                message=_professional_help_message(
                    interface_language,
                    consultation_7119=_reference_is_actionable(consultation_7119),
                    ambulance_119=_reference_is_actionable(ambulance_119),
                ),
                matched_rule_ids=core.matched_rule_ids,
                policy_flags=core.policy_flags,
                references=(consultation_7119, ambulance_119),
            )

    if _matches_any(normalized, _UNCERTAIN_SERIOUS_PATTERNS):
        return TokyoSafetyDecision(
            disposition=TokyoSafetyDisposition.INSUFFICIENT_INFORMATION,
            bypass_resource_navigation=True,
            message=_insufficient_message(
                interface_language,
                consultation_7119=_reference_is_actionable(consultation_7119),
                ambulance_119=_reference_is_actionable(ambulance_119),
            ),
            matched_rule_ids=("TOKYO-UNC-001",),
            references=(consultation_7119, ambulance_119),
        )

    routine_references: tuple[TokyoSafetyReference, ...] = ()
    message = _routine_message(interface_language)
    if heat_context and _matches_any(normalized, _HEAT_MILD_PATTERNS):
        routine_references = (heat_safety, ambulance_119)
        message = _heat_routine_message(
            interface_language,
            heat_guidance=_reference_is_actionable(heat_safety),
            ambulance_119=_reference_is_actionable(ambulance_119),
        )
    return TokyoSafetyDecision(
        disposition=TokyoSafetyDisposition.ROUTINE_NAVIGATION,
        bypass_resource_navigation=False,
        message=message,
        references=routine_references,
    )


def _tokyo_today() -> date:
    return datetime.now(_TOKYO_TIME_ZONE).date()


def _evaluate_reference(
    reference: TokyoSafetyReference,
    as_of: date,
) -> TokyoSafetyReference:
    if reference.superseded_by_source_id is not None:
        status = TokyoSafetyVerificationStatus.SUPERSEDED
    elif reference.availability_state is TokyoSafetyAvailabilityState.UNKNOWN:
        status = TokyoSafetyVerificationStatus.AVAILABILITY_UNKNOWN
    elif reference.availability_state is TokyoSafetyAvailabilityState.VERIFIED_UNAVAILABLE:
        status = TokyoSafetyVerificationStatus.VERIFIED_UNAVAILABLE
    elif reference.eligibility_state is TokyoSafetyEligibilityState.UNKNOWN:
        status = TokyoSafetyVerificationStatus.ELIGIBILITY_UNKNOWN
    elif reference.eligibility_state is TokyoSafetyEligibilityState.VERIFIED_INAPPLICABLE:
        status = TokyoSafetyVerificationStatus.VERIFIED_INAPPLICABLE
    elif as_of > reference.valid_until:
        status = TokyoSafetyVerificationStatus.EXPIRED
    else:
        status = TokyoSafetyVerificationStatus.VERIFIED_CURRENT

    return reference.model_copy(
        update={
            "verification_status": status,
            "currently_verified_actionable": status
            is TokyoSafetyVerificationStatus.VERIFIED_CURRENT,
        }
    )


def _reference_is_actionable(reference: TokyoSafetyReference) -> bool:
    return (
        reference.verification_status is TokyoSafetyVerificationStatus.VERIFIED_CURRENT
        and reference.currently_verified_actionable
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


def _heat_routine_message(
    language: InterfaceLanguage,
    *,
    heat_guidance: bool,
    ambulance_119: bool,
) -> str:
    if not heat_guidance:
        return _routine_message(language)

    base = {
        InterfaceLanguage.EN: (
            "Resource navigation may continue. For heat-related discomfort, move to a cooler place, "
            "cool the body, and take fluids if you can."
        ),
        InterfaceLanguage.JA: (
            "リソース案内を続行できます。暑さによる体調不良では、涼しい場所へ移動し、体を冷やし、"
            "可能であれば水分を取ってください。"
        ),
        InterfaceLanguage.ZH: (
            "可以继续资源导航。若因炎热出现不适，请先移到凉爽处、给身体降温，并在能够饮水时补充水分。"
        ),
    }[language]
    if ambulance_119:
        return base + {
            InterfaceLanguage.EN: " If severe warning signs develop, use 119.",
            InterfaceLanguage.JA: " 重い症状が出た場合は119番を利用してください。",
            InterfaceLanguage.ZH: " 如果出现严重警示症状，请拨打119。",
        }[language]
    return base + _unverified_emergency_contact_suffix(language)


def _emergency_message(
    language: InterfaceLanguage,
    *,
    ambulance_119: bool,
    police_110: bool,
    violence: bool,
) -> str:
    base = {
        InterfaceLanguage.EN: (
            "This request contains signs that may require immediate emergency help. CarePath Tokyo "
            "will not diagnose the situation or rank ordinary resources."
        ),
        InterfaceLanguage.JA: (
            "直ちに緊急対応が必要な可能性のある内容が含まれています。CarePath Tokyo は診断や通常の"
            "リソース順位付けを行いません。"
        ),
        InterfaceLanguage.ZH: (
            "该请求包含可能需要立即紧急处理的情况。CarePath Tokyo 不会进行诊断，也不会继续普通资源排名。"
        ),
    }[language]
    if ambulance_119:
        base += {
            InterfaceLanguage.EN: " For a medical emergency in Tokyo, call 119 now.",
            InterfaceLanguage.JA: " 東京都内の医療上の緊急時は、今すぐ119番に電話してください。",
            InterfaceLanguage.ZH: " 在东京遇到医疗紧急情况时，请立即拨打119。",
        }[language]
    else:
        base += _unverified_emergency_contact_suffix(language)

    if not violence:
        return base
    if police_110:
        return base + {
            InterfaceLanguage.EN: " If there is an immediate crime or violence emergency, call 110.",
            InterfaceLanguage.JA: " 犯罪や暴力の緊急事態が目前にある場合は110番に電話してください。",
            InterfaceLanguage.ZH: " 如果存在正在发生的犯罪或暴力紧急情况，请拨打110。",
        }[language]
    return base + {
        InterfaceLanguage.EN: (
            " For an immediate crime or violence emergency, use a current official police emergency source."
        ),
        InterfaceLanguage.JA: " 犯罪や暴力の緊急時は、最新の警察公式緊急情報を利用してください。",
        InterfaceLanguage.ZH: " 如遇正在发生的犯罪或暴力紧急情况，请使用当前官方警务紧急信息。",
    }[language]


def _professional_help_message(
    language: InterfaceLanguage,
    *,
    consultation_7119: bool,
    ambulance_119: bool,
) -> str:
    base = {
        InterfaceLanguage.EN: (
            "CarePath Tokyo cannot diagnose a condition or tell you to start, stop, or change "
            "medication. This request should pause ordinary resource ranking and use professional assessment."
        ),
        InterfaceLanguage.JA: (
            "CarePath Tokyo は診断や、薬の開始・中止・変更の指示を行いません。通常のリソース順位付けを"
            "中断し、専門家による評価を優先してください。"
        ),
        InterfaceLanguage.ZH: (
            "CarePath Tokyo 不会诊断疾病，也不会指示开始、停止或更改药物。此类请求应暂停普通资源排名，"
            "优先由专业人员评估。"
        ),
    }[language]
    return base + _professional_contact_suffix(
        language,
        consultation_7119=consultation_7119,
        ambulance_119=ambulance_119,
    )


def _insufficient_message(
    language: InterfaceLanguage,
    *,
    consultation_7119: bool,
    ambulance_119: bool,
) -> str:
    base = {
        InterfaceLanguage.EN: (
            "There is not enough information to safely rank an ordinary service. CarePath Tokyo "
            "will preserve that uncertainty rather than reassure or diagnose."
        ),
        InterfaceLanguage.JA: (
            "通常のサービスを安全に順位付けするには情報が不足しています。CarePath Tokyo は安心させる"
            "断定や診断をせず、不確実性を明示します。"
        ),
        InterfaceLanguage.ZH: (
            "目前信息不足以安全地进行普通服务排名。CarePath Tokyo 会保留这种不确定性，而不会给出安慰性"
            "断言或诊断。"
        ),
    }[language]
    return base + _professional_contact_suffix(
        language,
        consultation_7119=consultation_7119,
        ambulance_119=ambulance_119,
    )


def _professional_contact_suffix(
    language: InterfaceLanguage,
    *,
    consultation_7119: bool,
    ambulance_119: bool,
) -> str:
    if consultation_7119 and ambulance_119:
        return {
            InterfaceLanguage.EN: (
                " If you are unsure whether you need a hospital or ambulance in Tokyo, call #7119, "
                "which operates 24 hours a day. If the situation becomes severe, call 119."
            ),
            InterfaceLanguage.JA: (
                " 病院へ行くべきか救急車を呼ぶべきか迷う場合は、24時間対応の#7119に相談してください。"
                "重い状態になった場合は119番に電話してください。"
            ),
            InterfaceLanguage.ZH: (
                " 如果不确定在东京应去医院还是叫救护车，可拨打24小时服务的#7119；若情况变得严重，请拨打119。"
            ),
        }[language]
    if consultation_7119:
        return {
            InterfaceLanguage.EN: (
                " If you are unsure whether you need a hospital or ambulance in Tokyo, call #7119, "
                "which operates 24 hours a day. The stored 119 contact fact is not currently verified."
            ),
            InterfaceLanguage.JA: (
                " 病院へ行くべきか救急車を呼ぶべきか迷う場合は、24時間対応の#7119に相談してください。"
                "保存されている119の連絡先情報は現在の検証期限内ではありません。"
            ),
            InterfaceLanguage.ZH: (
                " 如果不确定在东京应去医院还是叫救护车，可拨打24小时服务的#7119。保存的119联系方式目前未通过有效期验证。"
            ),
        }[language]
    if ambulance_119:
        return {
            InterfaceLanguage.EN: (
                " The preferred consultation route is not currently verified, so it is not presented "
                "as actionable. If the situation is severe, call 119."
            ),
            InterfaceLanguage.JA: (
                " 優先する相談窓口は現在の検証期限内ではないため、利用可能とは表示しません。"
                "重い状態であれば119番に電話してください。"
            ),
            InterfaceLanguage.ZH: (
                " 首选咨询渠道目前未通过有效性验证，因此不会作为可执行渠道展示。若情况严重，请拨打119。"
            ),
        }[language]
    return {
        InterfaceLanguage.EN: (
            " Stored Tokyo emergency contact facts are not currently verified. Keep the higher safety "
            "disposition and use a current official emergency source rather than ordinary resource ranking."
        ),
        InterfaceLanguage.JA: (
            " 保存されている東京の緊急連絡先情報は現在の検証期限内ではありません。安全上の判定は維持し、"
            "通常のリソース順位付けではなく最新の公式緊急情報を利用してください。"
        ),
        InterfaceLanguage.ZH: (
            " 保存的东京紧急联系方式目前未通过有效性验证。应维持更高的安全处置，并使用当前官方紧急信息，"
            "而不是恢复普通资源排名。"
        ),
    }[language]


def _unverified_emergency_contact_suffix(language: InterfaceLanguage) -> str:
    return {
        InterfaceLanguage.EN: (
            " Seek immediate emergency help using a current official source; CarePath Tokyo's stored "
            "medical emergency contact fact is not currently verified."
        ),
        InterfaceLanguage.JA: (
            " 最新の公式情報を使って直ちに緊急援助を求めてください。CarePath Tokyo に保存された医療緊急"
            "連絡先情報は現在の検証期限内ではありません。"
        ),
        InterfaceLanguage.ZH: (
            " 请通过当前官方信息立即寻求紧急帮助；CarePath Tokyo 保存的医疗紧急联系方式目前未通过有效性验证。"
        ),
    }[language]

from __future__ import annotations

import re
from collections.abc import Hashable
from dataclasses import dataclass
from enum import StrEnum
from re import Pattern
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.models import RiskLevel

T = TypeVar("T", bound=Hashable)


class PolicyFlag(StrEnum):
    DIAGNOSIS_REQUEST = "diagnosis_request"
    MEDICATION_REQUEST = "medication_request"
    SELF_HARM = "self_harm"
    SERIOUS_FALL = "serious_fall"
    BREATHING_EMERGENCY = "breathing_emergency"
    NEUROLOGICAL_EMERGENCY = "neurological_emergency"
    SEVERE_ALLERGIC_REACTION = "severe_allergic_reaction"
    EXPLICIT_EMERGENCY = "explicit_emergency"
    PERSISTENT_WORSENING = "persistent_worsening"
    RECURRENT_FALL = "recurrent_fall"
    DATA_QUALITY = "data_quality"
    ACTIVITY_RESTRICTION = "activity_restriction"
    UNCERTAINTY = "uncertainty"


class ResponseAction(StrEnum):
    EMERGENCY_GUIDANCE = "emergency_guidance"
    DO_NOT_RELY_ON_CAREPATH = "do_not_rely_on_carepath"
    BYPASS_NORMAL_PLANNING = "bypass_normal_planning"
    NO_MEDICATION_ADVICE = "no_medication_advice"
    NON_DIAGNOSTIC_RESPONSE = "non_diagnostic_response"
    PROFESSIONAL_ASSESSMENT = "professional_assessment"
    PRESERVE_UNCERTAINTY = "preserve_uncertainty"
    CONSERVATIVE_ACTIVITY_ONLY = "conservative_activity_only"
    RESPECT_PROFESSIONAL_RESTRICTIONS = "respect_professional_restrictions"
    SEEK_IMMEDIATE_HUMAN_SUPPORT = "seek_immediate_human_support"


class SafetySignal(StrEnum):
    URGENT_BREATHING = "urgent_breathing"
    URGENT_NEUROLOGICAL = "urgent_neurological"
    SERIOUS_FALL_OR_TRAUMA = "serious_fall_or_trauma"
    URGENT_SELF_HARM = "urgent_self_harm"
    SEVERE_ALLERGIC_REACTION = "severe_allergic_reaction"
    EXPLICIT_EMERGENCY = "explicit_emergency"
    PERSISTENT_WORSENING = "persistent_worsening"
    RECURRENT_FALLS = "recurrent_falls"
    HISTORICAL_SELF_HARM = "historical_self_harm"
    DATA_QUALITY = "data_quality"
    ACTIVITY_RESTRICTION = "activity_restriction"
    AMBIGUOUS_SERIOUS_CONCERN = "ambiguous_serious_concern"


class TriageContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    structured_signals: frozenset[SafetySignal] = Field(default_factory=frozenset)


class TriageDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_level: RiskLevel
    matched_rule_ids: tuple[str, ...] = ()
    policy_flags: tuple[PolicyFlag, ...] = ()
    allow_normal_planning: bool
    required_response_actions: tuple[ResponseAction, ...] = ()
    uncertainty_reason: str | None = None


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    risk_level: RiskLevel
    policy_flag: PolicyFlag
    patterns: tuple[Pattern[str], ...]


def _compile(*patterns: str) -> tuple[Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


_TEXT_RULES: tuple[_Rule, ...] = (
    _Rule(
        "TRI-URG-001",
        RiskLevel.URGENT,
        PolicyFlag.BREATHING_EMERGENCY,
        _compile(
            r"\b(?:cannot|can't) breathe\b|\bnot breathing\b|\bgasping\b",
            r"\bsevere (?:difficulty|trouble) breathing\b",
            r"\bsevere (?:or persistent )?chest (?:pain|pressure)\b",
            r"\bchest (?:pain|pressure).{0,60}(?:shortness of breath|faint|passed out)",
            r"严重(?:的)?呼吸困难|喘不过气|无法呼吸|没有呼吸|严重(?:或持续)?(?:胸痛|胸部压迫)",
            r"息ができない|呼吸できない|激しい息苦しさ|重い胸の痛み|強い胸の圧迫感",
        ),
    ),
    _Rule(
        "TRI-URG-002",
        RiskLevel.URGENT,
        PolicyFlag.NEUROLOGICAL_EMERGENCY,
        _compile(
            r"\bface droop\b|\bone[- ]sided (?:weakness|numbness)\b",
            r"\bsudden (?:trouble|difficulty) speaking\b|\bnew severe confusion\b",
            r"\b(?:unconscious|unresponsive|loss of consciousness)\b",
            r"\b(?:ongoing|repeated) seizure\b|\bseizure.{0,40}(?:not recovering|won't wake)",
            r"面部下垂|一侧(?:无力|麻木)|突然(?:说话困难|言语不清)|严重意识混乱|失去意识|持续抽搐",
            r"顔の片側が下が|片側の(?:力が入らない|しびれ)|突然(?:話せない|ろれつが回らない)|意識がない|反応がない|けいれんが続",
        ),
    ),
    _Rule(
        "TRI-URG-003",
        RiskLevel.URGENT,
        PolicyFlag.SERIOUS_FALL,
        _compile(
            r"\b(?:fell|fall).{0,50}(?:passed out|lost consciousness|unconscious)\b",
            r"\bhead injur.{0,50}(?:can't stay awake|cannot stay awake|confusion|weakness)\b",
            r"\b(?:uncontrolled|severe) bleeding\b|\bmajor trauma\b",
            r"跌倒.{0,30}(?:失去意识|昏迷|昏倒)|头部受伤.{0,30}(?:无法保持清醒|意识混乱)|严重出血|止不住血",
            r"転倒.{0,30}(?:意識を失|気を失)|頭を打.{0,30}(?:起きていられない|意識がもうろう)|大量出血|出血が止まらない",
        ),
    ),
    _Rule(
        "TRI-URG-004",
        RiskLevel.URGENT,
        PolicyFlag.SELF_HARM,
        _compile(
            r"\b(?:plan|intend|going|about) to (?:kill|hurt) myself\b",
            r"\bsuicide plan\b|\bcan't keep myself safe\b|\bcannot keep myself safe\b",
            r"\bi want to die (?:now|today)\b|\bi am attempting suicide\b",
            r"\b(?:plan|going) to (?:kill|seriously hurt) someone\b",
            r"我(?:现在)?想自杀|我有自杀计划|我准备自杀|我要伤害自己|我无法保证自己安全|我要杀(?:了)?别人",
            r"今(?:すぐ)?自殺したい|自殺する計画がある|自分を傷つけるつもり|自分の安全を保てない|誰かを殺すつもり",
        ),
    ),
    _Rule(
        "TRI-URG-005",
        RiskLevel.URGENT,
        PolicyFlag.SEVERE_ALLERGIC_REACTION,
        _compile(
            r"\b(?:severe allergic reaction|anaphylaxis).{0,60}(?:can't breathe|difficulty breathing|faint|unconscious)",
            r"\bchoking\b|\bcan't breathe after (?:eating|taking)\b",
            r"严重过敏.{0,30}(?:呼吸困难|无法呼吸|昏倒|失去意识)|噎住了|窒息",
            r"重いアレルギー反応.{0,30}(?:息ができない|呼吸困難|失神)|窒息している|喉が詰まって息ができない",
        ),
    ),
    _Rule(
        "TRI-URG-006",
        RiskLevel.URGENT,
        PolicyFlag.EXPLICIT_EMERGENCY,
        _compile(
            r"\b(?:this is|having) (?:a )?(?:medical )?emergency\b",
            r"\bneed immediate emergency help\b|\bcall an ambulance now\b",
            r"这是(?:医疗)?紧急情况|正在发生紧急情况|需要立即急救|马上叫救护车",
            r"これは(?:医療)?緊急事態|救急車を今すぐ呼んで|すぐに救急対応が必要",
        ),
    ),
    _Rule(
        "TRI-CAU-001",
        RiskLevel.CAUTION,
        PolicyFlag.PERSISTENT_WORSENING,
        _compile(
            r"\b(?:persistent|worsening|getting worse).{0,50}(?:fatigue|dizziness|sleep|function|symptom)",
            r"\b(?:fatigue|dizziness|sleep problems?).{0,50}(?:persistent|worsening|getting worse)\b",
            r"(?:持续|反复|越来越严重|恶化).{0,20}(?:疲劳|头晕|睡眠|症状|功能)",
            r"(?:疲劳|头晕|睡眠|症状|功能).{0,20}(?:持续|反复|越来越严重|恶化)",
            r"(?:続いている|悪化している|だんだんひどく).{0,20}(?:疲労|めまい|睡眠|症状|機能)",
            r"(?:疲労|めまい|睡眠|症状|機能).{0,20}(?:続いている|悪化している|だんだんひどく)",
        ),
    ),
    _Rule(
        "TRI-CAU-002",
        RiskLevel.CAUTION,
        PolicyFlag.RECURRENT_FALL,
        _compile(
            r"\b(?:repeated|recurrent|multiple) (?:falls?|near[- ]falls?)\b",
            r"\b(?:fell|nearly fell) (?:twice|several times|again)\b|\bbalance is getting worse\b",
            r"反复跌倒|多次跌倒|差点跌倒.{0,15}(?:多次|好几次)|平衡越来越差",
            r"何度も転倒|転倒を繰り返|何度も転びそう|バランスが悪化",
        ),
    ),
    _Rule(
        "TRI-CAU-003",
        RiskLevel.CAUTION,
        PolicyFlag.SELF_HARM,
        _compile(
            r"\b(?:history of|used to) self[- ]harm\b|\bprevious suicide attempt\b",
            r"\battempted suicide (?:years ago|in the past|before)\b",
            r"曾经自伤|过去自残|以前自杀未遂|有自杀未遂史",
            r"以前自傷した|過去に自殺未遂|自傷歴がある",
        ),
    ),
    _Rule(
        "TRI-CAU-004",
        RiskLevel.CAUTION,
        PolicyFlag.DIAGNOSIS_REQUEST,
        _compile(
            r"\bcan you diagnose\b|\bdiagnose me\b|\bdo i have\b",
            r"\bcould this be (?:depression|heart disease|a disease|an illness)\b",
            r"\brule out .{0,40}(?:disease|condition|problem)\b",
            r"给我诊断|帮我诊断|我是不是得了|能不能排除|这是什么病",
            r"診断して|私は.{0,20}(?:病気|うつ病|心臓病)ですか|除外できますか",
        ),
    ),
    _Rule(
        "TRI-CAU-005",
        RiskLevel.CAUTION,
        PolicyFlag.MEDICATION_REQUEST,
        _compile(
            r"\b(?:start|stop|change|switch|increase|decrease|double|halve|skip|taper).{0,30}(?:medication|medicine|drug|dose)\b",
            r"\b(?:medication|medicine|drug|dose).{0,30}(?:start|stop|change|increase|decrease|double|skip|taper)\b",
            r"\b(?:drug|medication) interaction\b",
            r"停药|换药|加药|加量|减量|剂量|双倍(?:药|剂量)|药物相互作用",
            r"薬をやめ|薬を変え|増量|減量|用量|倍の量|薬の相互作用",
        ),
    ),
    _Rule(
        "TRI-CAU-006",
        RiskLevel.CAUTION,
        PolicyFlag.DATA_QUALITY,
        _compile(
            r"\bconflicting (?:fall )?reports?\b|\bdata (?:conflict|contradiction)\b",
            r"\b(?:fall )?records? (?:conflict|contradict)\b",
            r"\bsuspect sensor\b|\bsensor (?:reading|data).{0,20}(?:wrong|suspect)\b",
            r"\bmissing recent data\b",
            r"数据冲突|记录矛盾|传感器数据可疑|最近数据缺失",
            r"データが矛盾|記録が食い違|センサー値が怪しい|最近のデータが欠け",
        ),
    ),
    _Rule(
        "TRI-CAU-007",
        RiskLevel.CAUTION,
        PolicyFlag.ACTIVITY_RESTRICTION,
        _compile(
            r"\b(?:doctor|clinician|physio).{0,40}(?:told|said).{0,30}(?:not to|avoid|restrict).{0,30}(?:exercise|activity|walking|running)\b",
            r"\binjury.{0,40}(?:can't|cannot|prevents me from).{0,20}(?:walk|run|exercise)\b",
            r"医生.{0,30}(?:不让|限制|避免).{0,20}(?:运动|走路|跑步)|受伤.{0,30}(?:不能|无法)(?:运动|走路|跑步)",
            r"医師.{0,30}(?:運動を控え|運動を禁止|活動を制限)|けが.{0,30}(?:歩けない|走れない|運動できない)",
        ),
    ),
)


_STRUCTURED_RULES: dict[SafetySignal, tuple[str, RiskLevel, PolicyFlag]] = {
    SafetySignal.URGENT_BREATHING: (
        "TRI-URG-001",
        RiskLevel.URGENT,
        PolicyFlag.BREATHING_EMERGENCY,
    ),
    SafetySignal.URGENT_NEUROLOGICAL: (
        "TRI-URG-002",
        RiskLevel.URGENT,
        PolicyFlag.NEUROLOGICAL_EMERGENCY,
    ),
    SafetySignal.SERIOUS_FALL_OR_TRAUMA: (
        "TRI-URG-003",
        RiskLevel.URGENT,
        PolicyFlag.SERIOUS_FALL,
    ),
    SafetySignal.URGENT_SELF_HARM: (
        "TRI-URG-004",
        RiskLevel.URGENT,
        PolicyFlag.SELF_HARM,
    ),
    SafetySignal.SEVERE_ALLERGIC_REACTION: (
        "TRI-URG-005",
        RiskLevel.URGENT,
        PolicyFlag.SEVERE_ALLERGIC_REACTION,
    ),
    SafetySignal.EXPLICIT_EMERGENCY: (
        "TRI-URG-006",
        RiskLevel.URGENT,
        PolicyFlag.EXPLICIT_EMERGENCY,
    ),
    SafetySignal.PERSISTENT_WORSENING: (
        "TRI-CAU-001",
        RiskLevel.CAUTION,
        PolicyFlag.PERSISTENT_WORSENING,
    ),
    SafetySignal.RECURRENT_FALLS: (
        "TRI-CAU-002",
        RiskLevel.CAUTION,
        PolicyFlag.RECURRENT_FALL,
    ),
    SafetySignal.HISTORICAL_SELF_HARM: (
        "TRI-CAU-003",
        RiskLevel.CAUTION,
        PolicyFlag.SELF_HARM,
    ),
    SafetySignal.DATA_QUALITY: (
        "TRI-CAU-006",
        RiskLevel.CAUTION,
        PolicyFlag.DATA_QUALITY,
    ),
    SafetySignal.ACTIVITY_RESTRICTION: (
        "TRI-CAU-007",
        RiskLevel.CAUTION,
        PolicyFlag.ACTIVITY_RESTRICTION,
    ),
    SafetySignal.AMBIGUOUS_SERIOUS_CONCERN: (
        "TRI-CAU-006",
        RiskLevel.CAUTION,
        PolicyFlag.UNCERTAINTY,
    ),
}

_RISK_RANK = {
    RiskLevel.ROUTINE: 0,
    RiskLevel.CAUTION: 1,
    RiskLevel.URGENT: 2,
}


def _dedupe(items: list[T]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(items))


def _response_actions(
    risk_level: RiskLevel,
    flags: tuple[PolicyFlag, ...],
) -> tuple[ResponseAction, ...]:
    if risk_level is RiskLevel.URGENT:
        actions = [
            ResponseAction.EMERGENCY_GUIDANCE,
            ResponseAction.DO_NOT_RELY_ON_CAREPATH,
            ResponseAction.BYPASS_NORMAL_PLANNING,
            ResponseAction.NO_MEDICATION_ADVICE,
        ]
        if PolicyFlag.SELF_HARM in flags:
            actions.append(ResponseAction.SEEK_IMMEDIATE_HUMAN_SUPPORT)
        return tuple(actions)

    actions: list[ResponseAction] = []
    if PolicyFlag.DIAGNOSIS_REQUEST in flags:
        actions.append(ResponseAction.NON_DIAGNOSTIC_RESPONSE)
    if PolicyFlag.MEDICATION_REQUEST in flags:
        actions.append(ResponseAction.NO_MEDICATION_ADVICE)
    if PolicyFlag.DATA_QUALITY in flags or PolicyFlag.UNCERTAINTY in flags:
        actions.append(ResponseAction.PRESERVE_UNCERTAINTY)
    if PolicyFlag.ACTIVITY_RESTRICTION in flags:
        actions.extend(
            [
                ResponseAction.CONSERVATIVE_ACTIVITY_ONLY,
                ResponseAction.RESPECT_PROFESSIONAL_RESTRICTIONS,
            ]
        )
    if any(
        flag
        in {
            PolicyFlag.PERSISTENT_WORSENING,
            PolicyFlag.RECURRENT_FALL,
            PolicyFlag.SELF_HARM,
            PolicyFlag.DIAGNOSIS_REQUEST,
            PolicyFlag.MEDICATION_REQUEST,
        }
        for flag in flags
    ):
        actions.append(ResponseAction.PROFESSIONAL_ASSESSMENT)
    return _dedupe(actions)


def triage_safety(text: str, context: TriageContext | None = None) -> TriageDecision:
    """Classify safety risk without using an LLM or retrieved natural-language policy."""
    if not text.strip():
        raise ValueError("request_text must contain non-whitespace text")

    normalized = " ".join(text.casefold().split())
    matched_rule_ids: list[str] = []
    flags: list[PolicyFlag] = []
    risk_level = RiskLevel.ROUTINE

    for rule in _TEXT_RULES:
        if any(pattern.search(normalized) for pattern in rule.patterns):
            matched_rule_ids.append(rule.rule_id)
            flags.append(rule.policy_flag)
            if _RISK_RANK[rule.risk_level] > _RISK_RANK[risk_level]:
                risk_level = rule.risk_level

    if context is not None:
        for signal in context.structured_signals:
            rule_id, signal_risk, flag = _STRUCTURED_RULES[signal]
            matched_rule_ids.append(rule_id)
            flags.append(flag)
            if _RISK_RANK[signal_risk] > _RISK_RANK[risk_level]:
                risk_level = signal_risk

    if risk_level is RiskLevel.ROUTINE:
        return TriageDecision(
            risk_level=RiskLevel.ROUTINE,
            allow_normal_planning=True,
        )

    deduped_flags = _dedupe(flags)
    uncertainty_reason = None
    if PolicyFlag.DATA_QUALITY in deduped_flags or PolicyFlag.UNCERTAINTY in deduped_flags:
        uncertainty_reason = "Safety-relevant data is missing, conflicting, suspect, or ambiguous."

    return TriageDecision(
        risk_level=risk_level,
        matched_rule_ids=_dedupe(matched_rule_ids),
        policy_flags=deduped_flags,
        allow_normal_planning=False,
        required_response_actions=_response_actions(risk_level, deduped_flags),
        uncertainty_reason=uncertainty_reason,
    )

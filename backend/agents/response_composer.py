"""Deterministic final response composition with exact evidence references.

The Composer is intentionally a renderer over already-verified structured state.  It
never invents a citation, executes tools, changes risk, or turns user reports into
medical facts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.agents.context_builder import UserStateSummary
from backend.domain.models import RiskLevel
from backend.localization import (
    data_gap_text,
    external_evidence_statement,
    no_external_evidence_statement,
    recent_data_limited_text,
    trend_statement,
)
from backend.personalization.planner_v2 import PersonalizedWeeklyPlan
from backend.retrieval.evidence import EvidenceBundle, EvidenceType, GroupedEvidenceItem


class CitationSourceType(StrEnum):
    USER_RECORD = "user_record"
    EXTERNAL_GUIDELINE = "external_guideline"


class ResponseStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    statement_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    citation_ids: tuple[str, ...] = ()


class ResponsePlanAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str = Field(min_length=1)
    scheduled_date: str
    description: str = Field(min_length=1)
    frequency: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    citation_ids: tuple[str, ...] = ()


class ResponseCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(min_length=1)
    source_type: CitationSourceType
    evidence_id: str = Field(min_length=1)
    source_ids: tuple[str, ...] = ()
    source_id: str | None = None
    chunk_id: str | None = None
    display_citation: str | None = None
    supports: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_locatable_source(self) -> Self:
        if self.source_type is CitationSourceType.USER_RECORD and not self.source_ids:
            raise ValueError("user-record citations require source record IDs")
        if self.source_type is CitationSourceType.EXTERNAL_GUIDELINE and (
            not self.source_id or not self.chunk_id or not self.display_citation
        ):
            raise ValueError("external citations require source_id, chunk_id and display citation")
        return self


class StructuredCoachResponse(BaseModel):
    """Frontend-renderable final response with a frozen six-section contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: str = Field(min_length=2, max_length=8)
    risk_level: RiskLevel
    what_i_noticed: tuple[ResponseStatement, ...]
    what_the_evidence_suggests: tuple[ResponseStatement, ...]
    realistic_plan_for_this_week: tuple[ResponsePlanAction, ...]
    when_to_seek_professional_help: tuple[str, ...]
    sources: tuple[ResponseCitation, ...]
    what_i_am_uncertain_about: tuple[str, ...]
    rendered_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def citations_are_exact_and_resolvable(self) -> Self:
        citations = {item.citation_id: item for item in self.sources}
        if len(citations) != len(self.sources):
            raise ValueError("citation IDs must be unique")

        referenced: set[str] = set()
        statement_ids: set[str] = set()
        for statement in (*self.what_i_noticed, *self.what_the_evidence_suggests):
            statement_ids.add(statement.statement_id)
            referenced.update(statement.citation_ids)
        for action in self.realistic_plan_for_this_week:
            statement_ids.add(action.action_id)
            referenced.update(action.citation_ids)
        if referenced - citations.keys():
            raise ValueError("response contains an unresolved citation ID")
        if any(set(item.supports) - statement_ids for item in self.sources):
            raise ValueError("citation supports an unknown response item")
        return self


_HEADINGS: dict[str, tuple[str, str, str, str, str, str]] = {
    "en": (
        "What I noticed",
        "What the evidence suggests",
        "A realistic plan for this week",
        "When to seek professional help",
        "Sources",
        "What I am uncertain about",
    ),
    "zh": (
        "我注意到的情况",
        "现有证据提示什么",
        "本周可执行的计划",
        "何时寻求专业帮助",
        "来源",
        "我仍不确定的地方",
    ),
    "ja": (
        "確認できたこと",
        "エビデンスから示唆されること",
        "今週の現実的なプラン",
        "専門家の助けを求める目安",
        "出典",
        "まだ不確かなこと",
    ),
}


def _language_key(language: str) -> str:
    lowered = language.casefold()
    if lowered.startswith("zh"):
        return "zh"
    if lowered.startswith("ja"):
        return "ja"
    return "en"


def _fixed(language: str, key: str) -> str:
    values = {
        "no_change": {
            "en": "No reliable recent change was identified in the available records.",
            "zh": "现有记录中没有识别到可靠且显著的近期变化。",
            "ja": "利用可能な記録から、信頼できる大きな最近の変化は確認できませんでした。",
        },
        "no_external": {
            "en": (
                "No matching external guideline chunk was available, so the plan "
                "stays conservative and is not presented as evidence-specific advice."
            ),
            "zh": (
                "没有检索到匹配的外部指南片段\uff0c因此计划保持保守\uff0c"
                "不把它表述为特定证据支持的建议。"
            ),
            "ja": (
                "一致する外部ガイドラインのチャンクが得られなかったため、"
                "プランは保守的にし、特定エビデンスに基づく助言とは表現しません。"
            ),
        },
        "routine_help": {
            "en": (
                "Seek professional assessment if symptoms are persistent or worsening, "
                "falls or near-falls recur, or a planned action conflicts with an "
                "existing professional restriction."
            ),
            "zh": (
                "如果症状持续或加重、跌倒或险些跌倒反复出现\uff0c"
                "或计划与既有专业限制冲突\uff0c应寻求专业评估。"
            ),
            "ja": (
                "症状が続く・悪化する、転倒や転倒しかけることを繰り返す、"
                "または既存の専門家の制限とプランが矛盾する場合は、"
                "専門的な評価を受けてください。"
            ),
        },
        "not_diagnosis": {
            "en": "CarePath cannot determine a medical cause or diagnosis from these records.",
            "zh": "CarePath 无法根据这些记录确定医学原因或作出诊断。",
            "ja": "CarePath はこれらの記録から医学的な原因や診断を確定できません。",
        },
        "excluded_hostile": {
            "en": (
                "Some retrieved text was excluded because it contained instruction-like "
                "content; it was not used as evidence."
            ),
            "zh": "部分检索文本因包含类似指令的内容而被排除\uff0c未被用作证据。",
            "ja": "命令のような内容を含む取得テキストは除外され、エビデンスには使用していません。",
        },
    }
    return values[key][_language_key(language)]


class ResponseComposer:
    """Compose the six frozen sections without adding unverified medical claims."""

    def compose(
        self,
        *,
        summary: UserStateSummary,
        plan: PersonalizedWeeklyPlan,
        evidence: EvidenceBundle,
        risk_level: RiskLevel,
        language: str,
        prompt_injection_detected: bool = False,
    ) -> StructuredCoachResponse:
        noticed, user_sources = self._noticed(summary, language)
        evidence_statements, external_sources = self._evidence(plan, evidence, language)
        source_map = {item.citation_id: item for item in (*user_sources, *external_sources)}
        actions: list[ResponsePlanAction] = []
        support_updates: dict[str, set[str]] = {
            citation_id: set(item.supports) for citation_id, item in source_map.items()
        }

        evidence_by_id = {
            item.evidence_id: item
            for item in (*evidence.patient_evidence, *evidence.external_evidence)
        }
        for index, action in enumerate(plan.actions, start=1):
            action_id = f"plan-action-{index}"
            citation_ids: list[str] = []
            for evidence_id in action.evidence_ids:
                grouped = evidence_by_id.get(evidence_id)
                if grouped is None:
                    continue
                citation_id = self._citation_id(grouped)
                if citation_id not in source_map:
                    source = self._source_from_grouped(grouped)
                    source_map[citation_id] = source
                    support_updates[citation_id] = set(source.supports)
                citation_ids.append(citation_id)
                support_updates[citation_id].add(action_id)
            actions.append(
                ResponsePlanAction(
                    action_id=action_id,
                    scheduled_date=action.scheduled_date.isoformat(),
                    description=action.description,
                    frequency=action.frequency,
                    difficulty=action.difficulty.value,
                    rationale=action.rationale,
                    citation_ids=tuple(dict.fromkeys(citation_ids)),
                )
            )

        sources = tuple(
            item.model_copy(update={"supports": tuple(sorted(support_updates[item.citation_id]))})
            for item in source_map.values()
        )
        uncertainties = [data_gap_text(item, language) for item in summary.data_insufficient]
        if plan.data_limited and not uncertainties:
            uncertainties.append(recent_data_limited_text(language))
        if not evidence.external_evidence:
            uncertainties.append(_fixed(language, "no_external"))
        uncertainties.append(_fixed(language, "not_diagnosis"))
        if prompt_injection_detected:
            uncertainties.append(_fixed(language, "excluded_hostile"))

        response = StructuredCoachResponse(
            language=_language_key(language),
            risk_level=risk_level,
            what_i_noticed=noticed,
            what_the_evidence_suggests=evidence_statements,
            realistic_plan_for_this_week=tuple(actions),
            when_to_seek_professional_help=(_fixed(language, "routine_help"),),
            sources=sources,
            what_i_am_uncertain_about=tuple(dict.fromkeys(uncertainties)),
            rendered_text="placeholder",
        )
        return response.model_copy(update={"rendered_text": self._render(response)})

    @staticmethod
    def _noticed(
        summary: UserStateSummary,
        language: str,
    ) -> tuple[tuple[ResponseStatement, ...], tuple[ResponseCitation, ...]]:
        statements: list[ResponseStatement] = []
        citations: list[ResponseCitation] = []
        for index, trend in enumerate(summary.significant_trends[:3], start=1):
            statement_id = f"noticed-{index}"
            citation_id = f"user-records:{trend.metric_type.value}:{index}"
            statements.append(
                ResponseStatement(
                    statement_id=statement_id,
                    text=trend_statement(
                        metric=trend.metric_type,
                        direction=trend.direction,
                        current_mean=trend.current_mean,
                        baseline_mean=trend.baseline_mean,
                        percentage_change=trend.percentage_change,
                        language=language,
                    ),
                    citation_ids=(citation_id,),
                )
            )
            citations.append(
                ResponseCitation(
                    citation_id=citation_id,
                    source_type=CitationSourceType.USER_RECORD,
                    evidence_id=f"user-trend:{trend.metric_type.value}",
                    source_ids=trend.source_record_ids,
                    supports=(statement_id,),
                )
            )
        if not statements:
            statements.append(
                ResponseStatement(
                    statement_id="noticed-1",
                    text=_fixed(language, "no_change"),
                )
            )
        return tuple(statements), tuple(citations)

    def _evidence(
        self, plan: PersonalizedWeeklyPlan, evidence: EvidenceBundle, language: str
    ) -> tuple[tuple[ResponseStatement, ...], tuple[ResponseCitation, ...]]:
        statements: list[ResponseStatement] = []
        citations: list[ResponseCitation] = []
        plan_ids = set(plan.evidence_ids)
        relevant = [item for item in evidence.external_evidence if item.evidence_id in plan_ids]
        for index, item in enumerate(relevant[:3], start=1):
            statement_id = f"evidence-{index}"
            citation_id = self._citation_id(item)
            statements.append(
                ResponseStatement(
                    statement_id=statement_id,
                    text=external_evidence_statement(item.content, language),
                    citation_ids=(citation_id,),
                )
            )
            source = self._source_from_grouped(item)
            citations.append(source.model_copy(update={"supports": (statement_id,)}))
        if not statements:
            statements.append(
                ResponseStatement(
                    statement_id="evidence-1",
                    text=no_external_evidence_statement(language),
                )
            )
        return tuple(statements), tuple(citations)

    @staticmethod
    def _bounded_evidence_summary(content: str) -> str:
        compact = " ".join(content.split())
        sentence = compact.split(".", 1)[0].strip()
        if not sentence:
            sentence = compact
        if len(sentence) > 220:
            sentence = f"{sentence[:217].rstrip()}..."
        return f"Retrieved guidance states: {sentence}."

    @staticmethod
    def _citation_id(item: GroupedEvidenceItem) -> str:
        if item.evidence_type is EvidenceType.EXTERNAL_GUIDELINE:
            chunk_id = item.source_ids[-1] if item.source_ids else item.evidence_id
            return f"guideline:{chunk_id}"
        first = item.source_ids[0] if item.source_ids else item.evidence_id
        return f"user-record:{first}"

    @staticmethod
    def _source_from_grouped(item: GroupedEvidenceItem) -> ResponseCitation:
        if item.evidence_type is EvidenceType.EXTERNAL_GUIDELINE:
            source_id = item.source_ids[0] if item.source_ids else None
            chunk_id = item.source_ids[-1] if item.source_ids else None
            return ResponseCitation(
                citation_id=ResponseComposer._citation_id(item),
                source_type=CitationSourceType.EXTERNAL_GUIDELINE,
                evidence_id=item.evidence_id,
                source_ids=item.source_ids,
                source_id=source_id,
                chunk_id=chunk_id,
                display_citation=item.citation,
            )
        return ResponseCitation(
            citation_id=ResponseComposer._citation_id(item),
            source_type=CitationSourceType.USER_RECORD,
            evidence_id=item.evidence_id,
            source_ids=item.source_ids,
        )

    @staticmethod
    def _render(response: StructuredCoachResponse) -> str:
        headings = _HEADINGS[_language_key(response.language)]
        sections: list[str] = []

        def add(title: str, lines: list[str]) -> None:
            body = "\n".join(f"- {line}" for line in lines) if lines else "- —"
            sections.append(f"{title}\n{body}")

        add(headings[0], [item.text for item in response.what_i_noticed])
        add(headings[1], [item.text for item in response.what_the_evidence_suggests])
        add(
            headings[2],
            [
                f"{item.scheduled_date}: {item.description} ({item.difficulty})"
                for item in response.realistic_plan_for_this_week
            ],
        )
        add(headings[3], list(response.when_to_seek_professional_help))
        add(
            headings[4],
            [item.display_citation or ", ".join(item.source_ids) for item in response.sources],
        )
        add(headings[5], list(response.what_i_am_uncertain_about))
        return "\n\n".join(sections)


def controlled_safety_response(*, risk_level: RiskLevel, language: str) -> StructuredCoachResponse:
    """Return the same six-section contract for a blocked safety path."""

    key = _language_key(language)
    urgent = risk_level is RiskLevel.URGENT
    messages = {
        "en": (
            "CarePath detected a safety concern in what you reported.",
            "CarePath cannot assess or diagnose an emergency from this conversation.",
            (
                "Seek immediate in-person help or contact local emergency services now; "
                "do not rely on CarePath for emergency assessment."
            )
            if urgent
            else (
                "Please seek appropriate professional assessment before continuing "
                "ordinary coaching."
            ),
            "No ordinary weekly coaching plan is provided on this safety path.",
        ),
        "zh": (
            "CarePath 在你报告的内容中识别到了安全相关信号。",
            "CarePath 无法通过本次对话评估或诊断紧急医疗情况。",
            ("请立即寻求现场帮助或联系当地紧急服务\uff1b不要依赖 CarePath 进行紧急情况评估。")
            if urgent
            else "在继续常规健康行为指导前\uff0c请先寻求适当的专业评估。",
            "在此安全路径下不会提供常规的一周计划。",
        ),
        "ja": (
            "報告内容から安全上の懸念が検出されました。",
            "CarePath はこの会話から緊急事態を評価・診断できません。",
            (
                "直ちに対面での援助を求めるか、地域の救急サービスに連絡し、"
                "緊急評価を CarePath に頼らないでください。"
            )
            if urgent
            else "通常のコーチングを続ける前に、適切な専門的評価を受けてください。",
            "この安全経路では通常の1週間プランは提供しません。",
        ),
    }[key]
    response = StructuredCoachResponse(
        language=key,
        risk_level=risk_level,
        what_i_noticed=(ResponseStatement(statement_id="noticed-1", text=messages[0]),),
        what_the_evidence_suggests=(
            ResponseStatement(statement_id="evidence-1", text=messages[1]),
        ),
        realistic_plan_for_this_week=(),
        when_to_seek_professional_help=(messages[2],),
        sources=(),
        what_i_am_uncertain_about=(messages[3],),
        rendered_text="placeholder",
    )
    return response.model_copy(update={"rendered_text": ResponseComposer._render(response)})

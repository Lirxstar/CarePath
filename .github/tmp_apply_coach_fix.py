from pathlib import Path


def rep(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:80]!r}")
    file.write_text(text.replace(old, new))


rep(
    "backend/localization.py",
    '    return _METRIC_LABELS.get(resolved, {"en": resolved.value}) .get(\n        language_key(language), resolved.value\n    )',
    '    return _METRIC_LABELS.get(resolved, {"en": resolved.value}).get(\n        language_key(language), resolved.value\n    )',
)

rep(
    "backend/agents/runtime.py",
    '            start_date=summary.generated_at.date(),\n            request_text=request_text,\n        )',
    '            start_date=summary.generated_at.date(),\n            request_text=request_text,\n            language=language,\n        )',
)

planner = "backend/personalization/planner_v2.py"
rep(
    planner,
    'from backend.domain.models import ActionDifficulty, Domain, MetricType\nfrom backend.retrieval.evidence import ClaimScope, EvidenceBundle',
    'from backend.domain.models import ActionDifficulty, Domain, MetricType\nfrom backend.localization import (\n    fallback_goal,\n    language_key,\n    plan_action_description,\n    plan_follow_up,\n    plan_frequency,\n    plan_rationale,\n)\nfrom backend.retrieval.evidence import ClaimScope, EvidenceBundle',
)
rep(
    planner,
    '        start_date: date,\n        request_text: str,\n    ) -> PersonalizedWeeklyPlan:',
    '        start_date: date,\n        request_text: str,\n        language: str = "en",\n    ) -> PersonalizedWeeklyPlan:',
)
rep(
    planner,
    '        description = self._description(\n            domain, minutes, bool(summary.constraints.get("activity_constraints"))\n        )',
    '        description = self._description(\n            domain,\n            minutes,\n            bool(summary.constraints.get("activity_constraints")),\n            language,\n        )',
)
rep(
    planner,
    '            basis,\n            accepted_feedback_present=accepted_feedback_present,\n        )\n        follow_up = (\n            "Review completion and comfort after seven days; scale the next plan down "\n            "if completion is low, and pause any action that conflicts with a professional "\n            "restriction or feels unsafe."\n        )\n        alternatives = self._alternatives(domain, minutes)',
    '            basis,\n            accepted_feedback_present=accepted_feedback_present,\n            language=language,\n        )\n        follow_up = plan_follow_up(language)\n        alternatives = self._alternatives(domain, minutes, language)',
)
rep(planner, '                frequency="once that day",', '                frequency=plan_frequency(language),')
rep(planner, '        goal = self._goal(summary, domain)', '        goal = self._goal(summary, domain, language)')
rep(
    planner,
    '            frequency="one small action daily for seven days",',
    '            frequency=plan_frequency(language, weekly=True),',
)
rep(
    planner,
    '''    @staticmethod
    def _goal(summary: UserStateSummary, domain: Domain) -> str:
        prefix = f"{domain.value}:"
        return next(
            (goal for goal in summary.goals if goal.startswith(prefix)),
            f"Build a sustainable {domain.value} routine",
        )''',
    '''    @staticmethod
    def _goal(summary: UserStateSummary, domain: Domain, language: str = "en") -> str:
        prefix = f"{domain.value}:"
        existing = next((goal for goal in summary.goals if goal.startswith(prefix)), None)
        if existing is not None and language_key(language) == "en":
            return existing
        return fallback_goal(domain, language)''',
)
rep(
    planner,
    '''    @staticmethod
    def _description(domain: Domain, minutes: int, activity_limited: bool) -> str:
        if domain is Domain.SLEEP:
            return (
                f"Use {minutes} minutes for a consistent wind-down cue before your intended "
                "sleep period."
            )
        if domain is Domain.PHYSICAL_ACTIVITY:
            if activity_limited:
                return (
                    f"Choose {minutes} minutes of comfortable movement that stays within your "
                    "stated activity constraints."
                )
            return (
                f"Take {_minute_article(minutes)} {minutes}-minute comfortable walk "
                "or equivalent light movement break."
            )
        if domain is Domain.STRESS_MOOD:
            return (
                f"Take {_minute_article(minutes)} {minutes}-minute quiet recovery break using "
                "paced breathing or another "
                "preferred calming routine."
            )
        return (
            f"Spend {minutes} minutes checking one commonly used walking area for avoidable "
            "trip hazards."
        )''',
    '''    @staticmethod
    def _description(
        domain: Domain,
        minutes: int,
        activity_limited: bool,
        language: str = "en",
    ) -> str:
        return plan_action_description(
            domain=domain,
            minutes=minutes,
            activity_limited=activity_limited,
            language=language,
        )''',
)
rep(
    planner,
    '''    @staticmethod
    def _rationale(
        completion: float | None,
        data_limited: bool,
        stressed: bool,
        basis: GuidanceBasis,
        *,
        accepted_feedback_present: bool = False,
    ) -> str:
        reasons: list[str] = []
        if completion is not None and completion < 0.6:
            reasons.append("recent structured completion was low, so the action was reduced")
        if stressed:
            reasons.append("recent stress data were high, so workload was kept small")
        if data_limited:
            reasons.append("recent data were incomplete, so the plan stays conservative")
        if not reasons and accepted_feedback_present:
            reasons.append(
                "recent accepted feedback supports maintaining the current action size until "
                "completion evidence is available"
            )
        if not reasons:
            reasons.append(
                "the action is scaled to the available user context and prior completion history"
            )
        grounding = (
            "general guidance is supported by retrieved external evidence"
            if basis is GuidanceBasis.EVIDENCE_GROUNDED
            else "the suggestion is explicitly marked as general low-risk behavioural guidance"
        )
        return f"{' ; '.join(reasons)}; {grounding}."''',
    '''    @staticmethod
    def _rationale(
        completion: float | None,
        data_limited: bool,
        stressed: bool,
        basis: GuidanceBasis,
        *,
        accepted_feedback_present: bool = False,
        language: str = "en",
    ) -> str:
        return plan_rationale(
            low_completion=completion is not None and completion < 0.6,
            high_stress=stressed,
            data_limited=data_limited,
            accepted_feedback=accepted_feedback_present,
            evidence_grounded=basis is GuidanceBasis.EVIDENCE_GROUNDED,
            language=language,
        )''',
)
rep(
    planner,
    '''    @staticmethod
    def _alternatives(domain: Domain, minutes: int) -> tuple[PlanAlternative, ...]:
        shorter = max(2, minutes // 2)
        if domain is Domain.SLEEP:
            other = "Prepare the sleep environment and keep the same wake-time cue instead."
        elif domain is Domain.PHYSICAL_ACTIVITY:
            other = "Break the movement into two brief comfortable sessions instead."
        elif domain is Domain.STRESS_MOOD:
            other = "Use a quiet screen-free pause or brief written reflection instead."
        else:
            other = "Review lighting and clear one small walking path instead."
        return (
            PlanAlternative(
                description=(
                    f"Use {_minute_article(shorter)} {shorter}-minute version of the same action."
                ),
                reason="lower-effort fallback when time or energy is limited",
            ),
            PlanAlternative(
                description=other, reason="different low-risk route toward the same goal"
            ),
        )''',
    '''    @staticmethod
    def _alternatives(
        domain: Domain, minutes: int, language: str = "en"
    ) -> tuple[PlanAlternative, ...]:
        shorter = max(2, minutes // 2)
        key = language_key(language)
        if key == "zh":
            if domain is Domain.SLEEP:
                other = "改为整理睡眠环境，并保持相同的起床时间提示。"
            elif domain is Domain.PHYSICAL_ACTIVITY:
                other = "把活动拆成两次短时间、舒适的活动。"
            elif domain is Domain.STRESS_MOOD:
                other = "改为短暂离开屏幕安静休息，或进行简短书面反思。"
            else:
                other = "检查照明，并清理一小段常用行走路径。"
            return (
                PlanAlternative(
                    description=f"将同一行动缩短为 {shorter} 分钟。",
                    reason="时间或精力有限时采用更省力的备选方案",
                ),
                PlanAlternative(description=other, reason="以另一种低风险方式实现同一目标"),
            )
        if key == "ja":
            if domain is Domain.SLEEP:
                other = "代わりに睡眠環境を整え、同じ起床時刻の合図を保ちます。"
            elif domain is Domain.PHYSICAL_ACTIVITY:
                other = "運動を2回の短く無理のないセッションに分けます。"
            elif domain is Domain.STRESS_MOOD:
                other = "画面から離れて静かに休むか、短い書き出しを行います。"
            else:
                other = "照明を確認し、小さな歩行経路を1か所片づけます。"
            return (
                PlanAlternative(
                    description=f"同じ行動を {shorter} 分間の短い版にします。",
                    reason="時間やエネルギーが限られるときの負担の少ない代替案",
                ),
                PlanAlternative(description=other, reason="同じ目標に向けた別の低リスクな方法"),
            )
        if domain is Domain.SLEEP:
            other = "Prepare the sleep environment and keep the same wake-time cue instead."
        elif domain is Domain.PHYSICAL_ACTIVITY:
            other = "Break the movement into two brief comfortable sessions instead."
        elif domain is Domain.STRESS_MOOD:
            other = "Use a quiet screen-free pause or brief written reflection instead."
        else:
            other = "Review lighting and clear one small walking path instead."
        return (
            PlanAlternative(
                description=(
                    f"Use {_minute_article(shorter)} {shorter}-minute version of the same action."
                ),
                reason="lower-effort fallback when time or energy is limited",
            ),
            PlanAlternative(
                description=other, reason="different low-risk route toward the same goal"
            ),
        )''',
)

composer = "backend/agents/response_composer.py"
rep(
    composer,
    'from backend.domain.models import RiskLevel\nfrom backend.personalization.planner_v2 import PersonalizedWeeklyPlan',
    'from backend.domain.models import RiskLevel\nfrom backend.localization import (\n    data_gap_text,\n    external_evidence_statement,\n    no_external_evidence_statement,\n    recent_data_limited_text,\n    trend_statement,\n)\nfrom backend.personalization.planner_v2 import PersonalizedWeeklyPlan',
)
rep(
    composer,
    '        evidence_statements, external_sources = self._evidence(plan, evidence)',
    '        evidence_statements, external_sources = self._evidence(plan, evidence, language)',
)
rep(
    composer,
    '        uncertainties = list(summary.data_insufficient)\n        if plan.data_limited and not uncertainties:\n            uncertainties.append("recent_data_limited")',
    '        uncertainties = [data_gap_text(item, language) for item in summary.data_insufficient]\n        if plan.data_limited and not uncertainties:\n            uncertainties.append(recent_data_limited_text(language))',
)
rep(
    composer,
    '''                    text=(
                        f"{trend.metric_type.value} {trend.direction}: recent mean "
                        f"{trend.current_mean:.2f} versus "
                        f"{trend.baseline_mean:.2f} in the previous window "
                        f"({trend.percentage_change:+.1f}%)."
                    ),''',
    '''                    text=trend_statement(
                        metric=trend.metric_type,
                        direction=trend.direction,
                        current_mean=trend.current_mean,
                        baseline_mean=trend.baseline_mean,
                        percentage_change=trend.percentage_change,
                        language=language,
                    ),''',
)
rep(
    composer,
    '    def _evidence(\n        self, plan: PersonalizedWeeklyPlan, evidence: EvidenceBundle\n    ) -> tuple[tuple[ResponseStatement, ...], tuple[ResponseCitation, ...]]:',
    '    def _evidence(\n        self, plan: PersonalizedWeeklyPlan, evidence: EvidenceBundle, language: str\n    ) -> tuple[tuple[ResponseStatement, ...], tuple[ResponseCitation, ...]]:',
)
rep(
    composer,
    '                    text=self._bounded_evidence_summary(item.content),',
    '                    text=external_evidence_statement(item.content, language),',
)
rep(
    composer,
    '''                    text=(
                        "No matching external guideline evidence was used; the action "
                        "stays within the planner's general low-risk behaviour-support "
                        "boundary."
                    ),''',
    '                    text=no_external_evidence_statement(language),',
)

evidence_routes = "backend/api/app/evidence_routes.py"
rep(
    evidence_routes,
    '''    except ValueError as exc:
        raise CarePathError(
            "invalid_evidence_search",
            str(exc),
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from exc
    return list(hits)''',
    '''    except ValueError as exc:
        raise CarePathError(
            "invalid_evidence_search",
            str(exc),
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from exc
    except Exception as exc:
        raise CarePathError(
            "evidence_search_unavailable",
            "External guideline evidence is temporarily unavailable",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc
    return list(hits)''',
)

rep(
    "apps/mobile/src/ResilientRoutes.tsx",
    '''  const error = firstError([
    journey.coachState,
    journey.patientEvidenceState,
    journey.externalEvidenceState,
  ]);''',
    '  const error = firstError([journey.coachState]);',
)
rep(
    "apps/mobile/src/journey/JourneyContext.tsx",
    '      imported: importState.status === "success" && importState.data.status !== "failed",',
    '''      imported:
        (importState.status === "success" && importState.data.status !== "failed") ||
        profileState.status === "success",''',
)

screens = "apps/mobile/src/screens.tsx"
rep(
    screens,
    '<Text style={styles.helperText}>Load the selected synthetic persona first.</Text>',
    '<Text style={styles.helperText}>Add health data or load a demo persona first.</Text>',
)
rep(
    screens,
    '{patientEvidenceState.status === "error" ? (\n          <ErrorPanel error={patientEvidenceState.error} />\n        ) : null}',
    '''{patientEvidenceState.status === "error" ? (
          <Text style={styles.helperText}>
            Patient Evidence is temporarily unavailable. The coaching answer above can still be
            used; this evidence panel will not block it.
          </Text>
        ) : null}''',
)
rep(
    screens,
    '{externalEvidenceState.status === "error" ? (\n          <ErrorPanel error={externalEvidenceState.error} />\n        ) : null}',
    '''{externalEvidenceState.status === "error" ? (
          <Text style={styles.helperText}>
            External guideline evidence is temporarily unavailable. The coaching answer above
            remains limited to the evidence available to the verified workflow.
          </Text>
        ) : null}''',
)

catalog = "apps/mobile/src/i18n/catalog.ts"
marker = '''  {
    en: "No Patient Evidence matched this bounded window.",
    zh: "此限定时间窗口内没有匹配的用户证据。",
    ja: "この限定期間に一致するユーザーエビデンスはありません。",
  },'''
rep(
    catalog,
    marker,
    marker
    + '''
  {
    en: "Patient Evidence is temporarily unavailable. The coaching answer above can still be used; this evidence panel will not block it.",
    zh: "患者证据暂时不可用。上方的教练回答仍可使用；此证据面板不会阻止回答显示。",
    ja: "患者エビデンスは一時的に利用できません。上のコーチ回答は引き続き利用でき、このエビデンスパネルの障害で回答全体は停止しません。",
  },''',
)
marker = '''  {
    en: "No external guideline chunk matched this question.",
    zh: "没有与此问题匹配的外部指南片段。",
    ja: "この質問に一致する外部ガイドラインのチャンクはありません。",
  },'''
rep(
    catalog,
    marker,
    marker
    + '''
  {
    en: "External guideline evidence is temporarily unavailable. The coaching answer above remains limited to the evidence available to the verified workflow.",
    zh: "外部指南证据暂时不可用。上方教练回答仍仅基于已验证工作流当前可用的证据。",
    ja: "外部ガイドラインのエビデンスは一時的に利用できません。上のコーチ回答は、検証済みワークフローで利用可能なエビデンスの範囲に限定されています。",
  },''',
)
phrase_marker = '  { en: "External Evidence", zh: "外部证据", ja: "外部エビデンス" },'
rep(
    catalog,
    phrase_marker,
    '''  {
    en: "Add health data or load a demo persona first.",
    zh: "请先添加健康数据或加载演示用户。",
    ja: "健康データを追加するか、デモペルソナを読み込んでください。",
  },
'''
    + phrase_marker,
)

e2e = "apps/mobile/e2e/v08_demo.spec.ts"
rep(
    e2e,
    '''  await expect(page.getByText("Today dashboard")).toHaveCount(0);

  await openTab(page, "tab-health-data");''',
    '''  await expect(page.getByText("Today dashboard")).toHaveCount(0);
  await page.getByRole("button", { name: "加载演示数据" }).click();
  await expect(page.getByText("演示数据已加载")).toBeVisible({ timeout: 30_000 });

  await openTab(page, "tab-health-data");''',
)
rep(
    e2e,
    '''  await expect(page.getByText("基于证据的健康教练")).toBeVisible();
  await expect(page.getByText("询问 CarePath")).toBeVisible();

  await openTab(page, "tab-plan-history");''',
    '''  await expect(page.getByText("基于证据的健康教练")).toBeVisible();
  await expect(page.getByText("询问 CarePath")).toBeVisible();
  await page.getByRole("button", { name: "分析并回答" }).click();
  await expect(page.getByText(/睡眠时长.*近期平均值/).first()).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/计划睡觉前.*分钟/).first()).toBeVisible();
  await expect(page.getByText(/sleep_duration decreased/)).toHaveCount(0);
  await expect(page.getByText(/Use 12 minutes for a consistent wind-down cue/)).toHaveCount(0);
  await expect(page.getByText("Internal server error")).toHaveCount(0);

  await openTab(page, "tab-plan-history");''',
)

Path("tests/test_coach_localization.py").write_text(
    '''from backend.domain.models import Domain, MetricType
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
    assert trend_statement(
        metric=MetricType.SLEEP_DURATION,
        direction="decreased",
        current_mean=6.38,
        baseline_mean=7.60,
        percentage_change=-16.0,
        language="zh",
    ) == "睡眠时长下降：近期平均值为 6.38，上一窗口为 7.60（-16.0%）。"
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
'''
)

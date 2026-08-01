from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from backend.domain import Goal, Interaction, InterventionPlan, Observation, PlanAction, UserProfile
from backend.domain.models import (
    ActionDifficulty,
    Domain,
    InteractionStatus,
    Language,
    MetricType,
    QualityFlag,
    RiskLevel,
    SourceType,
)

from ..models import ImportIssue, ImportReport, PreparedImport
from ..validators import content_hash
from .mapping import (
    ACTION_STATUS_MAP,
    GOAL_STATUS_MAP,
    PLAN_STATUS_MAP,
    SUPPORTED_FHIR_RESOURCES,
    age_band_from_birth_date,
    careplan_goal_reference,
    deterministic_uuid,
    domain_code,
    goal_description,
    metric_code,
    normalize_date,
    normalize_datetime,
    normalize_reference,
    normalize_unit,
    patient_language,
    patient_timezone,
)

_EVENT_METRICS = {MetricType.FALL_EVENT, MetricType.NEAR_FALL_EVENT}


class FHIRBundleImporter:
    """Import the deliberately limited CarePath FHIR Bundle subset."""

    def prepare(self, data: bytes) -> PreparedImport:
        source_hash = content_hash(data)
        imported_at = datetime.now(UTC)
        try:
            decoded = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._failed(source_hash, imported_at, "invalid_bundle", str(exc))
        if not isinstance(decoded, dict) or decoded.get("resourceType") != "Bundle":
            return self._failed(
                source_hash,
                imported_at,
                "not_bundle",
                "resourceType must be Bundle",
            )
        entries = decoded.get("entry", [])
        if not isinstance(entries, list):
            return self._failed(
                source_hash,
                imported_at,
                "invalid_entries",
                "Bundle.entry must be a list",
            )

        resources: list[tuple[int, dict[str, Any]]] = []
        skipped: list[ImportIssue] = []
        fixed: list[ImportIssue] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("resource"), dict):
                skipped.append(
                    ImportIssue(
                        code="invalid_entry",
                        message="Bundle entry must contain a resource object",
                        record_index=index,
                    )
                )
                continue
            resource = dict(entry["resource"])
            resource_type = resource.get("resourceType")
            if resource_type not in SUPPORTED_FHIR_RESOURCES:
                skipped.append(
                    ImportIssue(
                        code="unsupported_resource_skipped",
                        message="Resource type is outside the simplified CarePath FHIR subset",
                        record_index=index,
                        resource_type=str(resource_type),
                    )
                )
                continue
            resource_id = resource.get("id")
            if not isinstance(resource_id, str) or not resource_id:
                skipped.append(
                    ImportIssue(
                        code="missing_resource_id",
                        message="Supported FHIR resources require id",
                        record_index=index,
                        resource_type=str(resource_type),
                    )
                )
                continue
            resources.append((index, resource))

        users: list[dict[str, object]] = []
        observations: list[dict[str, object]] = []
        goals: list[dict[str, object]] = []
        interactions: list[dict[str, object]] = []
        plans: list[dict[str, object]] = []
        actions: list[dict[str, object]] = []
        patients: dict[tuple[str, str], UUID] = {}
        patient_languages: dict[UUID, Language] = {}
        imported_goals: dict[tuple[str, str], tuple[UUID, Domain]] = {}

        for index, resource in self._resources_of_type(resources, "Patient"):
            try:
                patient_model, repairs = self._patient(resource, source_hash, imported_at)
                users.append(dict(patient_model.model_dump(mode="python")))
                patient_ref = ("Patient", str(resource["id"]))
                patients[patient_ref] = patient_model.user_id
                patient_languages[patient_model.user_id] = patient_model.preferred_language
                fixed.extend(self._issues(index, "Patient", repairs))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                skipped.append(self._invalid_resource(index, resource, exc))

        for index, resource in self._resources_of_type(resources, "Goal"):
            try:
                goal_model, original = self._goal(resource, source_hash, patients, imported_at)
                if goal_model is None:
                    skipped.append(
                        ImportIssue(
                            code="unknown_goal_domain",
                            message="Goal category is not a CarePath domain and was skipped",
                            record_index=index,
                            resource_type="Goal",
                            original_value=self._original_code(original),
                        )
                    )
                    continue
                goals.append(dict(goal_model.model_dump(mode="python")))
                imported_goals[("Goal", str(resource["id"]))] = (
                    goal_model.goal_id,
                    goal_model.domain,
                )
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                skipped.append(self._invalid_resource(index, resource, exc))

        for index, resource in self._resources_of_type(resources, "Observation"):
            try:
                observation_model, original = self._observation(resource, source_hash, patients)
                if observation_model is None:
                    skipped.append(
                        ImportIssue(
                            code="unknown_observation_code",
                            message="Observation code is not a CarePath metric and was skipped",
                            record_index=index,
                            resource_type="Observation",
                            original_value=self._original_code(original),
                        )
                    )
                    continue
                observations.append(dict(observation_model.model_dump(mode="python")))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                skipped.append(self._invalid_resource(index, resource, exc))

        for index, resource in self._resources_of_type(resources, "CarePlan"):
            try:
                plan, interaction, plan_actions = self._care_plan(
                    resource,
                    source_hash,
                    patients,
                    patient_languages,
                    imported_goals,
                    imported_at,
                )
                plans.append(dict(plan.model_dump(mode="python")))
                interactions.append(dict(interaction.model_dump(mode="python")))
                actions.extend(dict(action.model_dump(mode="python")) for action in plan_actions)
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                skipped.append(self._invalid_resource(index, resource, exc))

        return PreparedImport(
            report=ImportReport(
                status="partial" if skipped else "success",
                source_format="fhir",
                source_hash=source_hash,
                imported_at=imported_at,
                received_records=len(entries),
                inserted_records=0,
                fixed_issues=fixed,
                skipped_records=skipped,
            ),
            user_profiles=users,
            observations=observations,
            goals=goals,
            interactions=interactions,
            intervention_plans=plans,
            plan_actions=actions,
        )

    @staticmethod
    def _resources_of_type(
        resources: list[tuple[int, dict[str, Any]]],
        resource_type: str,
    ) -> list[tuple[int, dict[str, Any]]]:
        return [
            (index, resource)
            for index, resource in resources
            if resource.get("resourceType") == resource_type
        ]

    @staticmethod
    def _patient(
        resource: dict[str, Any],
        source_hash: str,
        imported_at: datetime,
    ) -> tuple[UserProfile, list[tuple[str, str]]]:
        birth_date = resource.get("birthDate")
        if birth_date is None:
            raise ValueError("FHIR Patient.birthDate is required for CarePath age_band")
        repairs: list[tuple[str, str]] = []
        language = patient_language(resource)
        if language is None:
            language = Language.EN
            repairs.append(
                ("language_defaulted", "Patient language missing or unsupported; defaulted to en")
            )
        timezone = patient_timezone(resource)
        if timezone is None:
            timezone = "UTC"
            repairs.append(("timezone_defaulted", "Patient timezone missing; defaulted to UTC"))
        return (
            UserProfile(
                user_id=deterministic_uuid(source_hash, "Patient", str(resource["id"])),
                age_band=age_band_from_birth_date(birth_date, imported_at),
                preferred_language=language,
                timezone=timezone,
                health_goals=[],
                coaching_preferences={"fhir_resource_id": str(resource["id"])},
                consent_flags={"fhir_import": True},
            ),
            repairs,
        )

    @staticmethod
    def _patient_id(
        resource: dict[str, Any],
        patients: dict[tuple[str, str], UUID],
    ) -> UUID:
        subject = resource.get("subject")
        if not isinstance(subject, dict):
            raise ValueError("subject.reference to Patient/<id> is required")
        reference = normalize_reference(subject.get("reference"))
        if reference is None or reference[0] != "Patient" or reference not in patients:
            raise ValueError("subject.reference must resolve to an imported Patient/<id>")
        return patients[reference]

    @classmethod
    def _observation(
        cls,
        resource: dict[str, Any],
        source_hash: str,
        patients: dict[tuple[str, str], UUID],
    ) -> tuple[Observation | None, dict[str, Any]]:
        metric, original_code = metric_code(resource)
        if metric is None:
            return None, original_code
        observed_at_raw = resource.get("effectiveDateTime", resource.get("issued"))
        observed_at = normalize_datetime(observed_at_raw)
        if metric in _EVENT_METRICS:
            if not isinstance(resource.get("valueBoolean"), bool):
                raise ValueError(f"FHIR {metric.value} requires valueBoolean")
            value_numeric = None
            value_boolean = bool(resource["valueBoolean"])
            unit = None
        else:
            quantity = resource.get("valueQuantity")
            if not isinstance(quantity, dict):
                raise ValueError(f"FHIR {metric.value} requires valueQuantity")
            raw_value = quantity.get("value")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise ValueError("valueQuantity.value must be numeric")
            value_numeric = float(raw_value)
            value_boolean = None
            unit = normalize_unit(metric, quantity)
        return (
            Observation(
                observation_id=deterministic_uuid(
                    source_hash,
                    "Observation",
                    str(resource["id"]),
                ),
                user_id=cls._patient_id(resource, patients),
                metric_type=metric,
                value_numeric=value_numeric,
                value_boolean=value_boolean,
                unit=unit,
                observed_at=observed_at,
                source_type=SourceType.FHIR,
                quality_flag=QualityFlag.VALID,
                confidence=1.0,
                metadata={
                    "fhir_resource_id": str(resource["id"]),
                    "fhir_original_code": original_code,
                },
            ),
            original_code,
        )

    @classmethod
    def _goal(
        cls,
        resource: dict[str, Any],
        source_hash: str,
        patients: dict[tuple[str, str], UUID],
        imported_at: datetime,
    ) -> tuple[Goal | None, dict[str, Any]]:
        domain, original_code = domain_code(resource)
        if domain is None:
            return None, original_code
        raw_status = resource.get("lifecycleStatus")
        if not isinstance(raw_status, str) or raw_status not in GOAL_STATUS_MAP:
            raise ValueError("unsupported Goal.lifecycleStatus")
        target_date: date | None = None
        targets = resource.get("target")
        if isinstance(targets, list) and targets and isinstance(targets[0], dict):
            raw_target_date = targets[0].get("dueDate")
            if raw_target_date is not None:
                target_date = normalize_date(raw_target_date)
        status_date = resource.get("statusDate")
        created_at = imported_at
        if isinstance(status_date, str):
            created_at = normalize_datetime(f"{status_date[:10]}T00:00:00+00:00")
        return (
            Goal(
                goal_id=deterministic_uuid(source_hash, "Goal", str(resource["id"])),
                user_id=cls._patient_id(resource, patients),
                domain=domain,
                description=goal_description(resource),
                status=GOAL_STATUS_MAP[raw_status],
                created_at=created_at,
                target_date=target_date,
            ),
            original_code,
        )

    @classmethod
    def _care_plan(
        cls,
        resource: dict[str, Any],
        source_hash: str,
        patients: dict[tuple[str, str], UUID],
        patient_languages: dict[UUID, Language],
        imported_goals: dict[tuple[str, str], tuple[UUID, Domain]],
        imported_at: datetime,
    ) -> tuple[InterventionPlan, Interaction, list[PlanAction]]:
        patient_id = cls._patient_id(resource, patients)
        goal_reference = careplan_goal_reference(resource)
        if goal_reference not in imported_goals:
            raise ValueError("CarePlan Goal reference must resolve to an imported Goal")
        goal_id, goal_domain = imported_goals[goal_reference]
        period = resource.get("period")
        if not isinstance(period, dict):
            raise ValueError("CarePlan.period is required")
        start = period.get("start")
        end = period.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError("CarePlan.period.start and end are required")
        raw_status = resource.get("status")
        if not isinstance(raw_status, str) or raw_status not in PLAN_STATUS_MAP:
            raise ValueError("unsupported CarePlan.status")

        interaction_id = deterministic_uuid(
            source_hash,
            "Interaction",
            f"careplan-{resource['id']}",
        )
        interaction = Interaction(
            interaction_id=interaction_id,
            user_id=patient_id,
            request_text=f"Imported FHIR CarePlan {resource['id']}",
            language=patient_languages.get(patient_id, Language.EN),
            started_at=imported_at,
            completed_at=imported_at,
            risk_level=RiskLevel.ROUTINE,
            final_status=InteractionStatus.COMPLETED,
            response_json={
                "source": "fhir_import",
                "fhir_resource_id": str(resource["id"]),
            },
        )
        plan = InterventionPlan(
            plan_id=deterministic_uuid(source_hash, "CarePlan", str(resource["id"])),
            user_id=patient_id,
            goal_id=goal_id,
            version=1,
            start_date=normalize_date(start),
            end_date=normalize_date(end),
            status=PLAN_STATUS_MAP[raw_status],
            generation_interaction_id=interaction_id,
        )
        plan_actions = cls._care_plan_actions(
            resource,
            source_hash,
            plan.plan_id,
            goal_domain,
        )
        return plan, interaction, plan_actions

    @staticmethod
    def _care_plan_actions(
        resource: dict[str, Any],
        source_hash: str,
        plan_id: UUID,
        goal_domain: Domain,
    ) -> list[PlanAction]:
        activities = resource.get("activity", [])
        if activities is None:
            return []
        if not isinstance(activities, list):
            raise ValueError("CarePlan.activity must be a list")
        actions: list[PlanAction] = []
        for index, activity in enumerate(activities):
            if not isinstance(activity, dict):
                raise ValueError("CarePlan.activity entries must be objects")
            detail = activity.get("detail")
            if not isinstance(detail, dict):
                raise ValueError("CarePlan.activity.detail is required in the supported subset")
            description = FHIRBundleImporter._activity_description(detail)
            frequency = FHIRBundleImporter._activity_frequency(detail)
            rationale = FHIRBundleImporter._activity_rationale(detail)
            raw_status = detail.get("status", "unknown")
            if not isinstance(raw_status, str) or raw_status not in ACTION_STATUS_MAP:
                raise ValueError("unsupported CarePlan.activity.detail.status")
            actions.append(
                PlanAction(
                    action_id=deterministic_uuid(
                        source_hash,
                        "PlanAction",
                        f"{resource['id']}-activity-{index}",
                    ),
                    plan_id=plan_id,
                    domain=goal_domain,
                    description=description,
                    frequency=frequency,
                    difficulty=ActionDifficulty.MEDIUM,
                    rationale=rationale,
                    status=ACTION_STATUS_MAP[raw_status],
                )
            )
        return actions

    @staticmethod
    def _activity_description(detail: dict[str, Any]) -> str:
        description = detail.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
        code = detail.get("code")
        if isinstance(code, dict):
            text = code.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
            codings = code.get("coding")
            if isinstance(codings, list):
                for coding_item in codings:
                    if not isinstance(coding_item, dict):
                        continue
                    for key in ("display", "code"):
                        value = coding_item.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
        raise ValueError("CarePlan activity requires description or code text")

    @staticmethod
    def _activity_frequency(detail: dict[str, Any]) -> str:
        timing = detail.get("scheduledTiming")
        if isinstance(timing, dict):
            code = timing.get("code")
            if isinstance(code, dict):
                raw_text = code.get("text")
                if isinstance(raw_text, str):
                    text = raw_text.strip()
                    if text:
                        return text
            repeat = timing.get("repeat")
            if isinstance(repeat, dict):
                frequency = repeat.get("frequency")
                period = repeat.get("period")
                period_unit = repeat.get("periodUnit")
                if isinstance(frequency, int) and frequency > 0:
                    if isinstance(period, (int, float)) and isinstance(period_unit, str):
                        return f"{frequency} every {period:g} {period_unit}"
                    return f"{frequency} times per documented period"
        return "as documented in FHIR CarePlan"

    @staticmethod
    def _activity_rationale(detail: dict[str, Any]) -> str:
        reason_codes = detail.get("reasonCode")
        if isinstance(reason_codes, list):
            for reason in reason_codes:
                if not isinstance(reason, dict):
                    continue
                text = reason.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return "Imported from FHIR CarePlan"

    @staticmethod
    def _issues(
        index: int,
        resource_type: str,
        repairs: list[tuple[str, str]],
    ) -> list[ImportIssue]:
        return [
            ImportIssue(
                code=code,
                message=message,
                record_index=index,
                resource_type=resource_type,
            )
            for code, message in repairs
        ]

    @staticmethod
    def _invalid_resource(
        index: int,
        resource: dict[str, Any],
        exc: Exception,
    ) -> ImportIssue:
        return ImportIssue(
            code="invalid_resource",
            message=str(exc),
            record_index=index,
            resource_type=str(resource.get("resourceType")),
            original_value=str(resource.get("id")),
        )

    @staticmethod
    def _original_code(original: dict[str, Any]) -> str:
        code = original.get("code")
        if isinstance(code, str) and code:
            return code
        return json.dumps(original, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _failed(
        source_hash: str,
        imported_at: datetime,
        code: str,
        message: str,
    ) -> PreparedImport:
        return PreparedImport(
            report=ImportReport(
                status="failed",
                source_format="fhir",
                source_hash=source_hash,
                imported_at=imported_at,
                received_records=0,
                inserted_records=0,
                blocking_errors=[ImportIssue(code=code, message=message)],
            )
        )

from typing import ClassVar

from .models import (
    AuditEvent,
    Goal,
    Interaction,
    InterventionPlan,
    JournalEntry,
    KnowledgeChunk,
    KnowledgeSource,
    Observation,
    PlanAction,
    PlanFeedback,
    UserProfile,
)


class UserProfileRecord(UserProfile):
    table_name: ClassVar[str] = "user_profiles"


class ObservationRecord(Observation):
    table_name: ClassVar[str] = "observations"


class JournalEntryRecord(JournalEntry):
    table_name: ClassVar[str] = "journal_entries"


class GoalRecord(Goal):
    table_name: ClassVar[str] = "goals"


class InterventionPlanRecord(InterventionPlan):
    table_name: ClassVar[str] = "intervention_plans"


class PlanActionRecord(PlanAction):
    table_name: ClassVar[str] = "plan_actions"


class PlanFeedbackRecord(PlanFeedback):
    table_name: ClassVar[str] = "plan_feedback"


class KnowledgeSourceRecord(KnowledgeSource):
    table_name: ClassVar[str] = "knowledge_sources"


class KnowledgeChunkRecord(KnowledgeChunk):
    table_name: ClassVar[str] = "knowledge_chunks"


class InteractionRecord(Interaction):
    table_name: ClassVar[str] = "interactions"


class AuditEventRecord(AuditEvent):
    table_name: ClassVar[str] = "audit_events"


CarePlanRecord = InterventionPlanRecord
ActionFeedbackRecord = PlanFeedbackRecord

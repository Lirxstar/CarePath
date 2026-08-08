from __future__ import annotations

from uuid import UUID

from backend.imports.models import PreparedImport


_USER_SCOPED_GROUPS = (
    "user_profiles",
    "observations",
    "journal_entries",
    "goals",
    "interactions",
    "intervention_plans",
    "plan_feedback",
)


def is_synthetic_import(prepared: PreparedImport) -> bool:
    if not prepared.user_profiles:
        return False
    for profile in prepared.user_profiles:
        consent = profile.get("consent_flags")
        if not isinstance(consent, dict) or consent.get("synthetic_demo") is not True:
            return False
    return True


def assign_import_user(prepared: PreparedImport, user_id: UUID) -> PreparedImport:
    """Return a deep copy whose user-scoped records belong to one account id."""

    assigned = prepared.model_copy(deep=True)
    for group_name in _USER_SCOPED_GROUPS:
        group = getattr(assigned, group_name)
        for record in group:
            if "user_id" in record:
                record["user_id"] = user_id
    for profile in assigned.user_profiles:
        consent = profile.get("consent_flags")
        flags = dict(consent) if isinstance(consent, dict) else {}
        flags["account_managed"] = True
        profile["consent_flags"] = flags
    return assigned

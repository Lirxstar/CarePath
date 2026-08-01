"""Simplified FHIR resource allowlist for the CP-002 contract boundary."""

FHIR_RESOURCE_TO_MODEL: dict[str, tuple[str, ...]] = {
    "Patient": ("UserProfile",),
    "Observation": ("Observation",),
    "Goal": ("Goal",),
    "CarePlan": ("InterventionPlan", "PlanAction"),
}

SUPPORTED_FHIR_RESOURCES: frozenset[str] = frozenset(FHIR_RESOURCE_TO_MODEL)

# Health Data Import Protocol

## Scope

This module imports simulated or public health data into the CarePath internal schema. It is not a full health information exchange server.

Supported formats:

- CSV wearable observations
- CarePath JSON data packages
- Simplified FHIR R4 Bundle subset

## Import Report

Every import returns an auditable report containing:

- `source_hash`: SHA-256 of the original source file
- `imported_at`: timezone-aware import timestamp
- `status`: success, partial, or failed
- fixed issues
- skipped records
- blocking errors

Import failures do not silently write partial business data.

## CSV and JSON validation

The importer validates:

- required columns and fields
- timestamps
- units
- duplicate records
- chronological order
- value ranges

Issues are classified as:

- fixed: safe normalization such as supported unit aliases
- skipped: invalid individual records that cannot be imported
- blocking: package-level failures that prevent import

## Simplified FHIR Support

Supported resources:

| FHIR Resource | Internal mapping |
| --- | --- |
| Patient | UserProfile |
| Observation | Observation |
| Goal | Goal |
| CarePlan | InterventionPlan + PlanAction |

Unsupported FHIR resources are skipped with explicit import report entries.

Unknown codes are not converted silently. Their original value is preserved in the import report or metadata.

## Non-goals

This implementation does not provide:

- complete FHIR server functionality
- terminology service integration
- clinical decision support
- medical diagnosis

The implementation demonstrates interoperability mapping for the CarePath data model only.

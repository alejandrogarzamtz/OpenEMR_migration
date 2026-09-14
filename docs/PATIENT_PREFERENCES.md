# Patient clinical preferences

OpenRM records patient preferences as longitudinal clinical observations rather
than mutable profile fields. Two legacy categories are preserved:

- `patient_treatment_intervention_preferences` → `treatment-intervention`
- `patient_care_experience_preferences` → `care-experience`

Every imported row retains its source identifier and complete source payload.
The observation LOINC code and display, effective date, workflow status, note,
and exactly one typed value (`coded`, `text`, or `boolean`) map to first-class
columns. `preference_value_sets` is imported as the response catalogue with its
code system, display, definition, order, and active state.

## Lifecycle and integrity

Current preferences are returned by default. `include_history=true` returns all
versions and inactive entries. An amendment creates a new record linked through
`supersedes_uuid`, marks the earlier version as amended, and requires a reason.
It cannot change the preference category or observation code. Removing a current
preference is a reason-required inactivation; records are never deleted.

Request validation rejects mixed value representations, incomplete coded values,
naive datetimes, and unknown categories or statuses. Every read and lifecycle
operation creates an audit event, and all item routes enforce patient ownership.

## API and user interface

- `GET /api/v1/patients/{uuid}/preference-catalog`
- `GET|POST /api/v1/patients/{uuid}/preferences`
- `POST /api/v1/patients/{uuid}/preferences/{preference_uuid}/amend`
- `DELETE /api/v1/patients/{uuid}/preferences/{preference_uuid}?reason=...`

The patient workspace exposes both categories, LOINC observations, imported
answer sets, typed entry, current/history views, amendments, and inactivation.
External coded answers remain representable when the legacy answer catalogue has
no matching entry.

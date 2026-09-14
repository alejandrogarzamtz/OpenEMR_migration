# Longitudinal care plans

OpenRM models care-plan entries as longitudinal clinical records rather than as
opaque encounter-form JSON. Each entry remains patient- and encounter-scoped
and preserves the fields of OpenEMR's `form_care_plan`: code and display text,
description, type, external identifier, related-note context, lifecycle status,
target/end dates, engagement category, and the complete coded-reason period.

The API provides authenticated create, list, update, and reason-required
inactivation operations under `/api/v1/patients/{patient_uuid}/care-plans`.
Dates and reason pairs are validated, every query is patient-compartment
scoped, reads and mutations are audited, and records attached to an
electronically locked encounter cannot be changed. The React chart provides
creation, status transitions, longitudinal display, and inactivation.

Each plan also has an append-only progress and outcome timeline. Events can
record plan and FHIR goal-achievement status, a narrative, or a coded numeric
measure with unit. Creating a plan and changing its lifecycle automatically add
status events; explicit progress/outcome events may update the current plan
status but can never rewrite earlier evidence. Outcome timestamps cannot predate
the plan, patient ownership is enforced, and signed encounters reject additions.

Legacy import projects every `form_care_plan` row into the relational model and
also retains the complete source payload. Because the legacy table permits
multiple rows under the same form ID and has no row primary key, import keys are
derived from a canonical row hash plus a deterministic duplicate ordinal. This
preserves identical duplicate rows while keeping repeated imports idempotent.
The original generic form payload remains available for independent source
reconciliation.

The legacy schema contains only the current `plan_status`, from which its FHIR
Goal service derived achievement status. Import therefore creates one source
event containing that exact status and the same deterministic row payload. It
labels the event as an initial legacy snapshot and does not claim that separate
historical outcomes existed.

FHIR R4 CarePlan and Goal read/search resources expose these records in the
patient compartment, including encounter and goal relationships and the latest
recorded achievement state. Production-source reconciliation remains explicit
parity work.

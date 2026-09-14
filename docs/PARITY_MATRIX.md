# OpenEMR functional parity matrix

This file is the binding completion checklist for the migration. A domain is
`complete` only when its database migration, API, React workflow, authorization,
audit trail, automated tests, legacy reconciliation, and integration contract
are all verified. “Partial” never counts as final parity.

| Domain | Current state | Remaining parity work |
|---|---|---|
| Authentication and sessions | Partial | revocable staff/portal sessions, refresh rotation/replay detection, logout, separate one-time recovery and encrypted TOTP MFA exist for both identity types; WebAuthn/U2F, SSO, password policy/history, admin MFA reset and device/session management remain |
| Users, practitioners and roles | Partial | full ACL/ACO migration, user lifecycle, practitioner roles and preferences |
| Patient demographics | Partial | normalized multiple addresses, telecoms and related people now preserve priority, validity, primary/emergency status and medical-information/decision flags with audited inactivation; employers, name history, advanced editing, consent/custom fields and complete legacy reconciliation remain |
| Patient search and chart | Partial | duplicate detection, merges, photos, chart locking and printable report |
| Scheduling and holidays | Partial | facility-aware events, resources, conflicts and statuses exist; recurrence expansion, categories, holidays, reminder delivery and wait list remain |
| Patient flow board | Partial | immutable tracker stages, rooms, timestamps and dashboard exist; configurable stage rules, analytics and remaining legacy actions remain |
| Encounters | Partial | lifecycle, locking, signing, diagnoses, providers and encounter forms |
| Clinical forms | Partial | structured/custom capture, signing and generic legacy preservation exist; specialized editors, dictation and per-form semantic validation remain |
| Problems and surgeries | Partial | full coding, verification, occurrence, associations and surgery workflow |
| Allergies | Partial | verification, intolerance detail, substance coding and reconciliation |
| Medications | Partial | adherence, devices, medication history and reconciliation |
| Prescriptions/eRx | Partial | core prescriptions/pharmacies exist; renewals, controlled substances and eRx integration remain |
| Immunizations | Partial | CVX administration exists; MVX, registry consent, refusals, inventory and registry exchange remain |
| Vitals and observations | Partial | capture, BMI and FHIR observations exist; growth charts and abnormal flags remain |
| Labs and procedures | Partial | multi-line orders, specimens, questions, HL7, Quest/LabCorp and review/sign-off |
| Documents | Partial | categories, filesystem/object storage, versions, templates and legal signing |
| Imaging | Missing | orders, results, DICOM/external viewer and ophthalmology imaging |
| Care plans and care teams | Missing | goals, participants, preferences and longitudinal workflow |
| Questionnaires/PRO/SDOH | Partial | versioned PHQ-9/GAD-7 responses and scoring exist; PROMIS, SDOH sets, patient delivery and broader repository remain |
| Clinical decision support | Missing | rules, reminders, alerts, measures and intervention feedback |
| Insurance and eligibility | Partial | eligibility checks, coordination of benefits and authorization workflows |
| Fee sheet and coding | Partial | configurable fee sheets, modifiers, diagnoses, NDC and price levels |
| Claims and X12 | Partial | 837 generation, partners, clearinghouse transport, rejections and rebilling |
| Payments and EOB/ERA | Partial | staff payment posting plus idempotent, processor-confirmed portal payment intents exist; 835 import, adjustments, allocations, deposits, refunds and reconciliation remain |
| Patient statements | Partial | explicitly released claim balances/history are patient-isolated in the portal; formatted statement generation, aging, collections and payment plans remain |
| Portal | Partial | separate patient and representative identities, forced temporary-password replacement, lockout, one-time recovery, encrypted TOTP MFA, explicit scoped proxy grants with immediate revocation, context-isolated messaging, appointments, released records, statements and payment-intent history are implemented; live payment adapter, patient questionnaires, configurable release policies and notification preferences remain |
| Internal messaging | Partial | patient-bound secure threads, staff replies, clinical tasks and notification outbox exist; staff-to-staff groups, preferences, SMS and Direct remain |
| Reports | Partial | all 48 legacy surfaces are cataloged and 11 report families have reproducible runs; 37 implementations remain |
| Quality measures | Missing | CQM/AMC calculation, exports, dashboards and result history |
| FHIR R4 API | Partial | remaining resources, search parameters, validation and bulk export |
| SMART on FHIR/OAuth | Missing | discovery, clients, scopes, launch context, refresh and revocation |
| Standard OpenEMR API | Missing | compatibility routes and portal API contracts |
| C-CDA/CCR/EHI export | Missing | generate, import, validate and complete patient export |
| Facilities and organizations | Partial | facilities, practitioners, warehouses and access assignments exist; organization hierarchy, departments and remaining settings remain |
| Inventory and drugs | Partial | warehouse lots, FEFO dispensing, immutable movements, destruction and scoped reconciliation exist; vendors, reorder workflow, prices and billing posting remain |
| Therapy groups | Missing | participants, counselors, group encounters and attendance |
| Amendments/disclosures | Missing | requests, approvals, history, disclosures and accounting |
| Templates and layouts | Missing | layout-based forms, custom fields and document templates |
| E-signatures | Missing | signing workflow, attestations, locks and legal audit evidence |
| Localization | Missing | language catalogs, locale/date/currency and translated UI |
| Administration/configuration | Missing | globals, lists, codes, modules, backups and background services |
| Webhooks/integration events | Missing | signed events, delivery retries, dead-letter handling and subscriptions |
| Extension/module compatibility | Missing | plugin SDK, hooks, module lifecycle and migration path for custom modules |
| Security/compliance operations | Partial | encryption, key rotation, immutable logs, retention, DR and access reviews |

## Integration completion gates

The system will not be called complete until all rows above are complete and:

1. Versioned OpenAPI and FHIR contracts are published with compatibility tests.
2. Database changes use reviewed migrations and support rollback.
3. Legacy imports are idempotent and reconcile counts, identifiers and hashes.
4. Role and patient-compartment authorization is tested for every endpoint.
5. Audit, backup/restore, disaster recovery, security and load tests pass.
6. A production-like parallel run demonstrates clinical and financial parity.
7. The external consuming project passes contract and end-to-end tests.

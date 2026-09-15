# OpenEMR functional parity matrix

This file is the binding completion checklist for the migration. A domain is
`complete` only when its database migration, API, React workflow, authorization,
audit trail, automated tests, legacy reconciliation, and integration contract
are all verified. “Partial” never counts as final parity.

| Domain | Current state | Remaining parity work |
|---|---|---|
| Authentication and sessions | Partial | revocable staff/portal sessions, refresh rotation/replay detection, logout, separate one-time recovery and encrypted TOTP MFA exist for both identity types; WebAuthn/U2F, SSO, password policy/history, admin MFA reset and device/session management remain |
| Users, practitioners and roles | Partial | full ACL/ACO migration, user lifecycle, practitioner roles and preferences |
| Patient demographics | Partial | normalized contacts, related people, employment, previous names, consent/directive history and layout fields have audited React workflows; guardian and mother columns backfill idempotently into related people with full guardian contact/address payload and no inferred authority; related contacts have scoped FHIR RelatedPerson contracts; importer output includes per-field typed and lossless-payload match counts, mismatch PIDs and a deterministic checksum; duplicate charts can be transactionally consolidated with immutable provenance while later imports resolve legacy aliases to the canonical chart; production-source reconciliation sign-off remains |
| Patient search and chart | Partial | deterministic duplicate scoring, registration blocking, documented override, merge preview, typed retained-chart confirmation, transactional record reassignment, conflict evidence, source UUID aliases, duplicate portal-identity shutdown, private versioned photos, E-signature-backed locking, and ACL-protected configurable HTML/PDF patient reports exist; site-specific report extension hooks and production-source acceptance remain |
| Scheduling and holidays | Partial | facility-aware events, resources, conflicts and statuses exist; recurrence expansion, categories, holidays, reminder delivery and wait list remain |
| Patient flow board | Partial | immutable tracker stages, rooms, timestamps and dashboard exist; configurable stage rules, analytics and remaining legacy actions remain |
| Encounters | Partial | lifecycle, locking, signing, diagnoses, providers and encounter forms |
| Clinical forms | Partial | generic preservation, signatures, amendments and locks exist; ten source-reconciled form families have contract-driven React editors and semantic validation, while patient-scoped document/result links from clinical notes are losslessly imported, audited, managed in React and covered by signature hashes; remaining specialized families remain |
| Problems and surgeries | Partial | full coding, verification, occurrence, associations and surgery workflow |
| Allergies | Partial | verification, intolerance detail, substance coding and reconciliation |
| Medications | Partial | adherence, devices, medication history and reconciliation |
| Prescriptions/eRx | Partial | complete legacy pharmacy/prescription provenance, nullable-date retention, audited detailed API, React display and expanded reporting exist; renewals, controlled substances, dispense lifecycle and live eRx integration remain |
| Immunizations | Partial | CVX administration exists; MVX, registry consent, refusals, inventory and registry exchange remain |
| Vitals and observations | Partial | capture, BMI and FHIR observations exist; growth charts and abnormal flags remain |
| Social history | Partial | append-only tobacco, alcohol, recreational-drug, activity, sleep, safety, counseling and narrative versions have lossless import, audited API, React authoring/history and printable-report coverage; coded FHIR observations and production reconciliation remain |
| Labs and procedures | Partial | lossless multi-line orders, report/result provenance and legacy rehydration now exist with audited API and React visibility; specimens, order questions, HL7, Quest/LabCorp and review/sign-off remain |
| Documents | Partial | categories, filesystem/object storage, versions, templates and legal signing |
| Imaging | Missing | orders, results, DICOM/external viewer and ophthalmology imaging |
| Care plans, teams and preferences | Partial | relational coded plans now include append-only status/progress/measured-outcome history; named polymorphic teams and both typed preference categories have audited React workflows, deterministic lossless import, and FHIR CarePlan/Goal/CareTeam read/search mappings; production reconciliation remains |
| Questionnaires/PRO/SDOH | Partial | versioned PHQ-9/GAD-7 definitions now preserve legacy item wording and expose scored, audited FHIR responses; PROMIS, SDOH sets, patient delivery and broader repository remain |
| Clinical decision support | Partial | evaluation history is losslessly imported and exposed through a permission- and facility-scoped immutable report; rule authoring/execution, reminders, measures and intervention feedback remain |
| Insurance and eligibility | Partial | eligibility checks, coordination of benefits and authorization workflows |
| Fee sheet and coding | Partial | configurable fee sheets, modifiers, diagnoses, NDC and price levels |
| Claims and X12 | Partial | 837 generation, partners, clearinghouse transport, rejections and rebilling |
| Payments and EOB/ERA | Partial | staff payment posting plus idempotent, processor-confirmed portal payment intents exist; 835 import, adjustments, allocations, deposits, refunds and reconciliation remain |
| Patient statements | Partial | explicitly released claim balances/history are patient-isolated in the portal, and integrated A/R collections/aging reporting is migrated; formatted statement generation and payment plans remain |
| Portal | Partial | separate patient and representative identities, forced temporary-password replacement, lockout, one-time recovery, encrypted TOTP MFA, explicit scoped proxy grants with immediate revocation, context-isolated messaging, patient-completed assigned questionnaires, notification inbox/preferences, appointments, released records, statements and payment-intent history are implemented; live payment adapter and configurable release policies remain |
| Internal messaging | Partial | patient-bound secure threads, staff group threads, clinical tasks, event preferences and a processable durable outbox exist; production SMTP/SMS and Direct adapters remain deployment integrations |
| Reports | Complete | all 48 legacy PHP surfaces are accounted: 46 runnable reports have typed, permissioned modern workflows and the 2 non-runnable Billing Manager criteria assets are verified against their React/Pydantic replacements; see `REPORT_PARITY.md` |
| Quality measures | Missing | CQM/AMC calculation, exports, dashboards and result history |
| FHIR R4 API | Complete | all 80 legacy route contracts are registered and tested, including directory writes, Device, Media, Medication, MedicationDispense, Specimen, Procedure, Provenance, ValueSet, Group, PractitionerRole, `$docref`, OperationDefinition and persisted system/patient/group Bulk Data export with authorized NDJSON retrieval and cancellation; this status does not claim external certification |
| SMART on FHIR/OAuth | Complete | SMART 2.2 standalone, EHR and patient launch; public-client Authorization Code with mandatory PKCE S256; RS256 OIDC identity; asymmetric Backend Services; patient/user/system v2 scopes; patient-compartment enforcement; single-use launch, code and assertion protection; discovery, administration, introspection and revocation are implemented and tested |
| Standard OpenEMR API | Complete | all 98 legacy Standard API routes and all 5 portal routes have authenticated, audited compatibility contracts, preserved response semantics and route-level tests; exact state is recorded in `LEGACY_API_INVENTORY.md` |
| C-CDA/EHI export | Complete | authenticated C-CDA R2.1 clinical summaries and patient-scoped ZIP exports include a checksum manifest plus a lossless JSON designated record set discovered through the patient foreign-key graph; XML/ZIP parsing and cross-patient isolation are tested |
| Facilities and organizations | Partial | facilities, practitioners, warehouses, access grants and longitudinal patient provider/facility responsibility exist with lossless legacy import and audited React management; organization hierarchy, departments and remaining settings remain |
| Inventory and drugs | Partial | warehouse lots, FEFO dispensing, immutable movements, destruction and scoped reconciliation exist; vendors, reorder workflow, prices and billing posting remain |
| Therapy groups | Missing | participants, counselors, group encounters and attendance |
| Amendments/disclosures | Missing | requests, approvals, history, disclosures and accounting |
| Templates and layouts | Missing | layout-based forms, custom fields and document templates |
| E-signatures | Partial | individual-form and encounter-wide signing require password reauthentication and record signer snapshots, attestations, amendments, content hashes and chained signature hashes in an append-only PostgreSQL table; encounter locks prohibit later forms/edits and legacy signatures retain both original hashes and payloads; delegated signing policy, certificate export and production legal-policy validation remain |
| Localization | Missing | language catalogs, locale/date/currency and translated UI |
| Administration/configuration | Missing | globals, lists, codes, modules, backups and background services |
| Webhooks/integration events | Missing | signed events, delivery retries, dead-letter handling and subscriptions |
| Extension/module compatibility | Missing | plugin SDK, hooks, module lifecycle and migration path for custom modules |
| Security/compliance operations | Partial | transactional SHA3-512 seals now detect modification/deletion in staff and identity audit streams; external anchoring, encryption/key rotation, retention enforcement, DR and access reviews remain |

## Integration completion gates

The system will not be called complete until all rows above are complete and:

1. Versioned OpenAPI and FHIR contracts are published with compatibility tests.
2. Database changes use reviewed migrations and support rollback.
3. Legacy imports are idempotent and reconcile counts, identifiers and hashes.
4. Role and patient-compartment authorization is tested for every endpoint.
5. Audit, backup/restore, disaster recovery, security and load tests pass.
6. A production-like parallel run demonstrates clinical and financial parity.
7. The external consuming project passes contract and end-to-end tests.

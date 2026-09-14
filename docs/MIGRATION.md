# Migration strategy

OpenEMR is a mature EHR, not a conventional CRUD application. Replacing it in
one release would endanger clinical continuity. This repository therefore uses
an incremental strangler migration.

## Boundaries

1. Keep PHP OpenEMR authoritative while each domain is being rebuilt.
2. Put FastAPI behind the same identity/access boundary and emit audit events
   for every access to protected health information.
3. Backfill a domain into the new schema, dual-read and reconcile it, then move
   writes only after measured parity.
4. Retire the corresponding PHP routes after an acceptance window and a tested
   rollback.

## Delivery order

| Phase | Domain | Exit condition |
|---|---|---|
| 1 | Identity, RBAC, audit, patients | reconciled patient counts and fields |
| 2 | Scheduling and encounters | parallel calendar/encounter validation |
| 3 | problems, medications, allergies | FHIR and clinical review parity |
| 4 | documents, labs, orders | document integrity and result routing |
| 5 | billing/claims | clearinghouse certification and reconciliation |
| 6 | portal, reports, remaining modules | operational sign-off and PHP shutdown |

## Patient mapping (initial)

The source `patient_data.pid` maps to the new `patients.legacy_pid`; `uuid` is
the external API identifier. Names, DOB, sex, email and phone are normalized in
the first pass. Site-specific layout fields must be inventoried before backfill.
Never copy secrets, session rows, or audit logs into application tables.

Before production use add organization-specific consent policy, SSO/MFA,
encryption/key management, backups, disaster recovery, retention, monitoring,
threat modelling, and regulatory validation. The development credentials are
not suitable for any real patient data.

## Import and reconciliation

The importer reads OpenEMR without modifying it and is a dry run by default:

```bash
python -m app.import_legacy --source 'mysql+pymysql://user:pass@openemr/openemr'
python -m app.import_legacy --source 'mysql+pymysql://user:pass@openemr/openemr' --commit
```

It currently migrates `patient_data`, its DEM layout definitions and values,
structured consent/directive decisions and employment history, the
problem/allergy/medication records in
`lists`, `form_encounter`, `form_vitals`, `immunizations`, `pharmacies`,
`prescriptions`, laboratory orders/results, and database-backed documents.
File-system document references are counted as rejected until their storage
volume is mounted. Insurance companies, patient coverages, charges, and claim
versions are also migrated with their legacy relationships. Legacy identifiers are unique keys, making
reruns idempotent. Compare `source`, `inserted`, and `existing` counts before
enabling `--commit`; every domain also reports `rejected` records requiring
storage remediation or clinical review.

Patient imports additionally emit `patient_demographic_reconciliation`. It
contains match counts and every divergent `pid` for each directly typed field,
the same evidence for every original `patient_data` value retained in
`legacy_payload`, missing patient identifiers, and a deterministic SHA-256
checksum. Cutover requires a reviewed report with no unexplained mismatches;
the dry run is evidence, not an instruction to overwrite the source system.

Interactive registration compares date of birth, normalized names, email and
phone against existing charts. Exact demographic matches are blocked until a
staff member reviews the candidates and records an override reason. Candidate
scores are an investigation aid only: the system never merges clinical charts
automatically, and every search or override is audited.

An authorized user may request a merge preview that enumerates every dependent
record and any uniqueness conflict before choosing the retained chart. The
merge requires a reason and an exact typed copy of the retained UUID, locks
both patient rows, moves dependent clinical and financial records in one
transaction, retains the retired UUID as an alias, and writes immutable merge
evidence. When both charts have portal identities, the retired identity is
disabled, detached, and its sessions are revoked. Conflicting custom-field
values are preserved in the merge evidence while the retained chart's value
wins; no conflict is silently discarded. Subsequent legacy imports resolve
retired legacy identifiers to the canonical chart.

The `forms` registry is reconciled against the actual `form_*` tables installed
in the source system. SOAP, ROS, physical-exam and clinic-note forms receive
normalized types; every other installed form is retained as a custom JSON
payload so module-specific clinical data is not silently discarded. Deleted,
orphaned, or missing-table registrations are reported as rejected.

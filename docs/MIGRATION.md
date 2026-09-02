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

It currently migrates `patient_data`, the problem/allergy/medication records in
`lists`, and `form_encounter`. Legacy identifiers are unique keys, making
reruns idempotent. Compare `source`, `inserted`, and `existing` counts before
enabling `--commit`; rejected/incomplete records require clinical review.

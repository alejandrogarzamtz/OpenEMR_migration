# Audit integrity

OpenRM records staff activity in `audit_events` and patient-portal or proxy
identity activity in `identity_audit_events`. Each ORM insert creates a separate
`audit_event_seals` row in the same transaction. The seal is a deterministic
SHA3-512 checksum over every meaningful field in its source event, including
the timestamp, acting identity, action, resource and detail.

Migration `20261006_0036` creates the seal store and backfills all existing
modern audit events using the same canonical representation. Event identifiers
are never reused, including in the SQLite test environment. The seal table does
not use a cascading foreign key: if an event is deleted, its seal remains as
evidence that the identifier previously existed.

Administrators with `admin:super:read` can run `audit_log_tamper_report` through
the normal report API and React report viewer. The report returns only failures:

- `tampered` when a source event no longer matches its stored checksum;
- `unsealed` when an event has no corresponding integrity record;
- `deleted` when a seal remains but its source event is gone.

The run itself is immutable report evidence with parameters, totals, SHA-256
snapshot checksum and authenticated CSV export. The report never repairs or
hides a failure.

These seals provide database tamper evidence comparable to the preserved
legacy checksum report; they do not make a compromised database physically
immutable. An attacker able to rewrite both source events and seals could
replace the evidence. Production deployments that require resistance to that
threat must additionally replicate or anchor seals in separately controlled,
append-only storage. External anchoring remains an explicit operations gap.

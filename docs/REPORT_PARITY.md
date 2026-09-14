# Legacy report parity ledger

This ledger accounts for every report surface discovered under the preserved
`interface/reports` tree. `MIGRATED` requires a query, permission, stored
snapshot, totals and CSV export. All entries remain visible through
`GET /api/v1/reports`; running a pending entry returns an explicit `501`.

| Legacy report key | Status |
|---|---|
| `amc_full_report` | PENDING |
| `amc_tracking` | PENDING |
| `appointments_report` | MIGRATED |
| `appt_encounter_report` | PENDING |
| `audit_log_tamper_report` | MIGRATED |
| `background_services` | MIGRATED — ordered service registry with active/manual scheduling, live lease status, last/next run semantics, totals and CSV |
| `cdr_log` | MIGRATED — lossless before/after decision payloads, legacy and normalized patient/user/facility identity, alert labels, inclusive date filters, facility isolation, totals and CSV |
| `chart_location_activity` | MIGRATED — patient-scoped, date-filtered append-only physical chart location/custody history with totals and CSV |
| `charts_checked_out` | MIGRATED — current checkout state derived from each patient's latest custody event, including named external custodians |
| `clinical_reports` | PENDING |
| `collections_report` | PENDING |
| `cqm` | PENDING |
| `criteria.tab` | EMBEDDED / PENDING — criteria UI included by the legacy billing report, not an independently executable report; parity belongs to the unfinished billing-report builder |
| `custom_report_range` | PENDING |
| `daily_summary_report` | MIGRATED |
| `destroyed_drugs_report` | MIGRATED |
| `direct_message_log` | MIGRATED |
| `encounters_report` | MIGRATED |
| `external_data` | MIGRATED — patient-scoped external encounters and procedures with dates, diagnosis/code text, provider/facility provenance, source identifiers, filters, totals and CSV |
| `front_receipts_report` | PENDING |
| `immunization_report` | MIGRATED |
| `insurance_allocation_report` | MIGRATED — date- and facility-scoped primary-insurance distribution with non-copay charges, visits, unique-patient attribution, percentages, totals and CSV |
| `inventory_activity` | MIGRATED |
| `inventory_list` | MIGRATED |
| `inventory_transactions` | MIGRATED |
| `ip_tracker` | MIGRATED — cumulative/windowed failures, automatic and manual blocking, timing flag, protected reset/update, filters and CSV |
| `ippf_cyp_report` | PENDING |
| `ippf_daily` | PENDING |
| `ippf_statistics` | PENDING |
| `message_list` | MIGRATED |
| `non_reported` | PENDING |
| `pat_ledger` | PENDING |
| `patient_edu_web_lookup` | MIGRATED — configurable ordered resource catalog, validated single-placeholder HTTP(S) templates, URL-encoded audited searches, administration, React workflow, snapshot and CSV |
| `patient_flow_board_report` | MIGRATED |
| `patient_list` | MIGRATED |
| `patient_list_creation` | PENDING |
| `payment_processing_report` | PENDING |
| `prepayment_balance_report` | PENDING |
| `prescriptions_report` | MIGRATED |
| `receipts_by_method_report` | PENDING |
| `referrals_report` | MIGRATED — facility/date/status scoped referral-loop report with recipient organization, request/reply dates, patient identifiers and reason |
| `report.script` | EMBEDDED / PENDING — shared JavaScript for the legacy billing criteria component, not an independently executable report; parity belongs to that parent workflow |
| `report_results` | MIGRATED — date-filtered immutable run history with title, completion state, row count, actor, SHA-256 integrity checksum, snapshot totals and CSV |
| `rwt_2026_report` | PENDING |
| `sales_by_item` | MIGRATED |
| `services_by_category` | MIGRATED — active service catalog, superbill categories, code-type/category filters, modifiers, units, related codes and multi-level prices |
| `svc_code_financial_report` | PENDING |
| `unique_seen_patients_report` | MIGRATED |

Current accounting: **48 cataloged, 27 migrated, 21 pending/embedded**.

`criteria.tab` and `report.script` are included implementation assets rather
than standalone routes. They remain explicitly accounted for, but must not be
represented as runnable reports. Their date/text/radio/dropdown criteria
behavior will be verified with the parent billing-report builder.

`cdr_log` preserves raw `value` and `new_value` text exactly, including empty
or malformed historical JSON, so a report never rewrites clinical evidence.
Unresolved legacy references remain queryable by their original IDs. Modern
facility grants constrain both normalized and legacy facility identities.

`insurance_allocation_report` groups each charged encounter under the primary
coverage effective on that encounter date, or under `-- No Insurance --`.
Copay-coded and zero-value lines are excluded, encounter counts remain visits,
and each patient contributes once to the patient distribution denominator.

`clinical_reports` remains pending after source-level review. Its legacy query
requires lossless social-history versions plus procedure-order metadata,
result provenance, detailed prescription fields and patient-provider facility
assignments that are not yet retained by the normalized import. Those data
contracts must land before the multi-dimensional React report can claim parity.

`appt_encounter_report` remains pending after source-level review. Its legacy
error detection depends on billing authorization, justification, billed flags,
modifiers and patient copays that the current normalized charge/payment model
does not yet preserve. It must be completed with the broader financial-ledger
phase rather than represented by a lossy appointment/encounter join.

`message_list` reports the normalized secure-message history without exposing
message bodies in broad report exports. It retains the legacy date, author,
patient, type/status and update semantics and adds stable message/thread and
patient UUIDs. `direct_message_log` is backed by the durable communication
outbox and therefore reports outbound email, Direct and future delivery
channels, status transitions, attempts and failures. It does not claim inbound
Direct parity: inbound Direct transport remains part of the communication
integration gap.

`immunization_report` uses normalized immunization and patient records, keeps
CVX, administration, manufacturer, lot, route, site, dose, completion/refusal
state and stable identifiers, and excludes `entered-in-error` records as the
legacy registry report did. The reproducible CSV report is migrated; registry
submission and HL7 VXU generation remain integration work and are not implied
by this status.

`inventory_activity` reconstructs beginning and ending balances from each
lot's current balance and immutable movement ledger, then groups sales,
distributions/consumption, purchases, both sides of transfers, adjustments and
in-period destruction by product and warehouse. Every detail row enforces
`ending = starting + activity`; warehouse filters and user warehouse scopes
are applied before aggregation.

`audit_log_tamper_report` verifies independent SHA3-512 seals for both staff
and portal/identity audit streams. It reports modified rows, missing seals and
sealed event IDs whose source row was deleted. Migration `0036` backfills
existing modern audit rows; every subsequent ORM insert is sealed in the same
database transaction. See `AUDIT_INTEGRITY.md` for the trust boundary.

`background_services` preserves the legacy worker registry and reports manual
versus automatic scheduling, calculated last/next runs and current lease state.
As in the source report, an expired lease is not considered busy even if the
historical running flag remains set.

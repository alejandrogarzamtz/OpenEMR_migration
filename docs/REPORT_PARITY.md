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
| `background_services` | PENDING |
| `cdr_log` | PENDING |
| `chart_location_activity` | MIGRATED — patient-scoped, date-filtered append-only physical chart location/custody history with totals and CSV |
| `charts_checked_out` | MIGRATED — current checkout state derived from each patient's latest custody event, including named external custodians |
| `clinical_reports` | PENDING |
| `collections_report` | PENDING |
| `cqm` | PENDING |
| `criteria.tab` | PENDING |
| `custom_report_range` | PENDING |
| `daily_summary_report` | MIGRATED |
| `destroyed_drugs_report` | MIGRATED |
| `direct_message_log` | MIGRATED |
| `encounters_report` | MIGRATED |
| `external_data` | PENDING |
| `front_receipts_report` | PENDING |
| `immunization_report` | MIGRATED |
| `insurance_allocation_report` | PENDING |
| `inventory_activity` | MIGRATED |
| `inventory_list` | MIGRATED |
| `inventory_transactions` | MIGRATED |
| `ip_tracker` | PENDING |
| `ippf_cyp_report` | PENDING |
| `ippf_daily` | PENDING |
| `ippf_statistics` | PENDING |
| `message_list` | MIGRATED |
| `non_reported` | PENDING |
| `pat_ledger` | PENDING |
| `patient_edu_web_lookup` | PENDING |
| `patient_flow_board_report` | MIGRATED |
| `patient_list` | MIGRATED |
| `patient_list_creation` | PENDING |
| `payment_processing_report` | PENDING |
| `prepayment_balance_report` | PENDING |
| `prescriptions_report` | MIGRATED |
| `receipts_by_method_report` | PENDING |
| `referrals_report` | PENDING |
| `report.script` | PENDING |
| `report_results` | PENDING |
| `rwt_2026_report` | PENDING |
| `sales_by_item` | MIGRATED |
| `services_by_category` | PENDING |
| `svc_code_financial_report` | PENDING |
| `unique_seen_patients_report` | MIGRATED |

Current accounting: **48 cataloged, 18 migrated, 30 pending**.

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

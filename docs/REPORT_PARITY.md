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
| `audit_log_tamper_report` | PENDING |
| `background_services` | PENDING |
| `cdr_log` | PENDING |
| `chart_location_activity` | PENDING |
| `charts_checked_out` | PENDING |
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
| `immunization_report` | PENDING |
| `insurance_allocation_report` | PENDING |
| `inventory_activity` | PENDING |
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

Current accounting: **48 cataloged, 13 migrated, 35 pending**.

`message_list` reports the normalized secure-message history without exposing
message bodies in broad report exports. It retains the legacy date, author,
patient, type/status and update semantics and adds stable message/thread and
patient UUIDs. `direct_message_log` is backed by the durable communication
outbox and therefore reports outbound email, Direct and future delivery
channels, status transitions, attempts and failures. It does not claim inbound
Direct parity: inbound Direct transport remains part of the communication
integration gap.

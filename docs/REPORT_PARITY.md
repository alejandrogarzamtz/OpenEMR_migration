# Legacy report parity ledger

This ledger accounts for every report surface discovered under the preserved
`interface/reports` tree. `MIGRATED` requires a query, permission, stored
snapshot, totals and CSV export. All entries remain visible through
`GET /api/v1/reports`; running a pending entry returns an explicit `501`.

| Legacy report key | Status |
|---|---|
| `amc_full_report` | MIGRATED — typed saved AMC calculations, Standard/AMC denominator math, lossless ordered patient-level evidence, unresolved legacy patient identity, summary/detail modes, immutable snapshots and CSV |
| `amc_tracking` | MIGRATED — referral, patient-request and encounter candidates; date/provider filters, durable normal/electronic completion evidence, audited transitions, immutable snapshots and CSV |
| `appointments_report` | MIGRATED |
| `appt_encounter_report` | MIGRATED — full-outer appointment/encounter reconciliation, billing diagnostics, copays, practitioner totals, facility ACL, snapshots and CSV |
| `audit_log_tamper_report` | MIGRATED |
| `background_services` | MIGRATED — ordered service registry with active/manual scheduling, live lease status, last/next run semantics, totals and CSV |
| `cdr_log` | MIGRATED — lossless before/after decision payloads, legacy and normalized patient/user/facility identity, alert labels, inclusive date filters, facility isolation, totals and CSV |
| `chart_location_activity` | MIGRATED — patient-scoped, date-filtered append-only physical chart location/custody history with totals and CSV |
| `charts_checked_out` | MIGRATED — current checkout state derived from each patient's latest custody event, including named external custodians |
| `clinical_reports` | MIGRATED |
| `collections_report` | MIGRATED — integrated A/R responsibility, effective payer/policy selection, charges, product sales, payments, adjustments, aging buckets, patient and insurance modes, facility ACL, snapshots and CSV |
| `cqm` | PENDING |
| `criteria.tab` | EMBEDDED / PENDING — criteria UI included by the legacy billing report, not an independently executable report; parity belongs to the unfinished billing-report builder |
| `custom_report_range` | MIGRATED — printable patient Superbill with qualifying new-patient encounters, full demographics and subscriber coverage, active charge/provider fallback, copay reconciliation, facility ACL, snapshots and CSV |
| `daily_summary_report` | MIGRATED |
| `destroyed_drugs_report` | MIGRATED |
| `direct_message_log` | MIGRATED |
| `encounters_report` | MIGRATED |
| `external_data` | MIGRATED — patient-scoped external encounters and procedures with dates, diagnosis/code text, provider/facility provenance, source identifiers, filters, totals and CSV |
| `front_receipts_report` | MIGRATED — lossless receipt lines grouped by patient/timestamp, current and prior amounts, method/source/actor, method subtotals, facility/provider scope, snapshots and CSV |
| `immunization_report` | MIGRATED |
| `insurance_allocation_report` | MIGRATED — date- and facility-scoped primary-insurance distribution with non-copay charges, visits, unique-patient attribution, percentages, totals and CSV |
| `inventory_activity` | MIGRATED |
| `inventory_list` | MIGRATED |
| `inventory_transactions` | MIGRATED |
| `ip_tracker` | MIGRATED — cumulative/windowed failures, automatic and manual blocking, timing flag, protected reset/update, filters and CSV |
| `ippf_cyp_report` | MIGRATED — typed CYP factors across active MA services and paid medication sales, encounter-date/facility scope, invoice identity, detail/summary totals, snapshots and CSV |
| `ippf_daily` | MIGRATED — single-day/facility scoped clinic record; current contraceptive method, new/returning/contraceptive clients, eight named service counters, totals, snapshots and CSV |
| `ippf_statistics` | MIGRATED — configurable IPPF, Member Association and GCAC families; legacy row/content combinations, service/product/referral attribution, sex/facility/date filters, total/sex/age/demographic dimensions, snapshots and CSV |
| `message_list` | MIGRATED |
| `non_reported` | MIGRATED — unsubmitted reportable ICD-9 issue detection, date/patient/code filters, scoped HL7 2.5.1 ADT export, durable submission exclusion, snapshots and CSV |
| `pat_ledger` | MIGRATED — patient/date/facility/provider-scoped procedure ledger with encounter charges, live payments and adjustments, unapplied-credit reconciliation, balances, snapshots and CSV |
| `patient_edu_web_lookup` | MIGRATED — configurable ordered resource catalog, validated single-placeholder HTTP(S) templates, URL-encoded audited searches, administration, React workflow, snapshot and CSV |
| `patient_flow_board_report` | MIGRATED |
| `patient_list` | MIGRATED |
| `patient_list_creation` | MIGRATED — eleven patient cohort modes with source-specific dates/providers, wildcard and demographic filters, per-mode ACL, stable identity, deterministic sorting, snapshots and CSV |
| `payment_processing_report` | MIGRATED — gateway transaction audit, patient/service/ticket/transaction/action filters, success/error state, sale/reversal links, encrypted-source disclosure, snapshots and CSV; live Sphere void/credit requires a configured gateway |
| `prepayment_balance_report` | MIGRATED — standalone prepayment sessions, live non-deleted allocations, open/unapplied threshold, optional check dates and patient, parked-global filter, exact monetary totals, snapshots and CSV |
| `prescriptions_report` | MIGRATED |
| `receipts_by_method_report` | MIGRATED — copays plus integrated A/R payments/adjustments by payer, configured method or check reference; service/deposit dates, procedure/provider/facility filters, detail/summary, snapshots and CSV |
| `referrals_report` | MIGRATED — facility/date/status scoped referral-loop report with recipient organization, request/reply dates, patient identifiers and reason |
| `report.script` | EMBEDDED / PENDING — shared JavaScript for the legacy billing criteria component, not an independently executable report; parity belongs to that parent workflow |
| `report_results` | MIGRATED — date-filtered immutable run history with title, completion state, row count, actor, SHA-256 integrity checksum, snapshot totals and CSV |
| `rwt_2026_report` | MIGRATED — fixed April–September 2026 ONC period; lossless C-CDA, Direct, QRDA import/export, API actor/resource analytics and optional EHI-export evidence; modern API requests remain continuously measured |
| `sales_by_item` | MIGRATED |
| `services_by_category` | MIGRATED — active service catalog, superbill categories, code-type/category filters, modifiers, units, related codes and multi-level prices |
| `svc_code_financial_report` | MIGRATED — fee-code units, billed, live applied payment, adjustment and balance totals; facility/provider ACL scope, important-code flag/filter, snapshots and CSV |
| `unique_seen_patients_report` | MIGRATED |

Current accounting: **48 cataloged, 45 migrated, 3 pending/embedded**.

`criteria.tab` and `report.script` are included implementation assets rather
than standalone routes. They remain explicitly accounted for, but must not be
represented as runnable reports. Their date/text/radio/dropdown criteria
behavior will be verified with the parent billing-report builder.

`custom_report_range` preserves the legacy New Patient Encounter selection and
reverse chronological Superbill order, while treating the selected end date as
the full calendar day instead of reproducing the legacy midnight-only SQL edge
case. It emits the latest value for every displayed demographic and primary,
secondary and tertiary subscriber field, retains complete source insurance
rows, applies charge-level provider fallback, excludes inactive billing rows,
reconciles live patient copays, and keeps encounters without charges printable.

`non_reported` retains each source problem row and its original issue timestamp,
joins only codes explicitly marked reportable, and excludes issues with a durable
syndromic-submission record. Its authenticated HL7 export reproduces the legacy
2.5.1 ADT A01, EVN, PID, PV1, OBX and DG1 contract, requires an authorized sending
facility with NPI, escapes delimiters, records message control IDs, and prevents
duplicate export from a stale report snapshot. As in the source workflow, the
record proves generation/export under the `PH_SS-NoAck` profile, not receiver ACK.

`pat_ledger` requires an explicit patient and reproduces the legacy accounting
scope: active procedure-code charges from encounters in the selected period,
all non-deleted A/R activity attached to those encounters, and payment sessions
created in the period whose funds were partially applied. Charge fees are not
multiplied by units, payments and adjustments reduce encounter balances, and
only the residual portion of a partially applied session reduces the grand
balance. Detail rows retain both the displayed original payment and its applied
and balance effects so totals remain auditable rather than inferred.

`patient_list_creation` reproduces all eleven legacy selection modes rather than
collapsing them into a generic demographic list. Each mode applies its original
date source and detail shape across demographics, issues, medications,
prescriptions, communication consent, primary insurance, encounters, custom
observation forms, procedure orders and laboratory results. Provider filters and
permissions follow the selected source; SQL `%` and `_` wildcards, multi-valued
race/ethnicity, unique-patient totals and user-selected deterministic ordering
are preserved. Runs are immutable, checksum-protected cohorts that can be
retrieved or exported again without silently recomputing membership.

`ippf_cyp_report` retains CYP factors as typed decimal fields on service and
medication definitions. It combines active `MA` charge lines with non-zero-fee
drug sales, scopes both through their encounter date and facility, preserves
invoice and stable patient/encounter identity, rounds factors before extension
as the source report does, and supports both auditable detail and product-total
views with immutable CSV-capable snapshots.

`cdr_log` preserves raw `value` and `new_value` text exactly, including empty
or malformed historical JSON, so a report never rewrites clinical evidence.
Unresolved legacy references remain queryable by their original IDs. Modern
facility grants constrain both normalized and legacy facility identities.

`insurance_allocation_report` groups each charged encounter under the primary
coverage effective on that encounter date, or under `-- No Insurance --`.
Copay-coded and zero-value lines are excluded, encounter counts remain visits,
and each patient contributes once to the patient distribution denominator.

`clinical_reports` now reproduces the legacy cohort dimensions for demographics,
primary provider/facility, communication consent, diagnoses, prescriptions,
laboratory results, procedure lines, most-recent social history, service codes
and immunizations. Date semantics, SQL-style wildcards, combinatorial rows,
facility ACL, deterministic ordering, immutable snapshots, authenticated CSV,
validation, golden fixtures and the React filter/table workflow are covered.

The migration also retains the source billing date and complete billing row, the
immunization amount/unit and complete immunization row, and the procedure type's
standard code so these report dimensions are not reconstructed from weaker
encounter or display-label approximations.

`appt_encounter_report` performs a full-outer reconciliation so appointments
without visits and visits without appointments remain visible. It preserves the
legacy code-type fee/justification rules, charge authorization and billed flags,
modifiers, complete billing rows and patient copays from active `ar_activity`
PCP entries. Results include stable modern identifiers, explicit diagnostic
messages, practitioner subtotals and grand totals, facility ACL, immutable
snapshots and CSV. Encounter provider/facility snapshots and complete source
rows are rehydrated on repeat imports rather than only applied to new records.

`collections_report` applies the legacy integrated-A/R responsibility rule from
encounter statement count, closed insurance level and coverage effective on the
service date. It reconciles active service charges, product sales, non-voided
payments and adjustments; supports patient, insurer, insurer-summary, credit and
all-balance modes; and computes configurable service-date or last-activity aging
as of an explicit date. Payment-session payer, reference, check/deposit date and
method are preserved as typed provenance while the complete source activity row
remains retained. Broad report reads are constrained by facility grants.

`front_receipts_report` preserves every source `payments` row independently of
claim and integrated-A/R payments. It reproduces the legacy receipt identity by
grouping rows on exact patient and timestamp, sums current-encounter and prior-
balance amounts separately, retains the source, method and actor labels, and
provides method and grand totals. Encounter joins intentionally exclude legacy
prepayments without a visit, matching the source report, and facility/provider
scope is enforced before grouping.

`receipts_by_method_report` combines active billed copays with non-voided
integrated-A/R payments and adjustments only for registered encounters, as the
legacy report does. It supports payment/deposit or invoice-date semantics,
facility and charge-provider scope, procedure-code prefix matching, effective
coverage policy display, and detailed or grouped output by payer, configured
payment-method label or check reference. Source session labels and activity
memo/follow-up/reason fields are typed while every original row remains intact.

`payment_processing_report` preserves every `payment_processing_audit` column,
including binary identifiers, original amount text, encrypted request/response
evidence, reversal evidence and sale-to-reversal links. Typed filters and totals
never expose the encrypted blob. Front labels and legacy error explanations are
derived only when the source value is already readable JSON; otherwise the row
explicitly reports that source installation keys are required. Live Sphere
void/credit submission remains an external integration gate and is not implied
by the migrated read-only report.

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

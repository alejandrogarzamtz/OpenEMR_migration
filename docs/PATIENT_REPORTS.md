# Printable patient reports

OpenRM provides authenticated comprehensive patient reports at
`GET /api/v1/patients/{patient_uuid}/report.html` and
`GET /api/v1/patients/{patient_uuid}/report.pdf`. They follow the principal
sections of OpenEMR's Patient Report while rendering only data already migrated
into typed target models. The HTML response supports browser printing and the
PDF response is generated server-side as a downloadable document.

Access requires the OpenEMR-compatible `patients/pat_rep` read grant. Section
content is additionally limited by `patients/demo`, `patients/med`,
`patients/docs`, and `acct/bill`; the report grant never broadens underlying
access. The API resolves retired duplicate-chart UUIDs to the retained chart,
scopes every query by that patient, HTML-escapes values, and emits
`private, no-store`, CSP and `nosniff` headers. Every export creates an audit
event containing the selected period, section counts and an evidence SHA-256
also returned as `X-Report-SHA256` and printed in the report.

Optional ISO dates limit time-based encounters, forms, laboratory orders,
immunizations, vital signs and claims:

```text
/api/v1/patients/{uuid}/report.html?start=2026-01-01&end=2026-12-31
```

The optional `sections` parameter accepts a comma-separated subset of:
`demographics`, `addresses`, `telecommunications`, `previous-names`,
`related-people`, `employment`, `clinical-items`, `prescriptions`,
`immunizations`, `vitals`, `encounters`, `clinical-forms`, `care-plans`, `laboratory`,
`documents`, `insurance`, and `claims`. Unknown names and empty selections are
rejected rather than silently producing an ambiguous report.

The React chart lets users select a date range and report sections, opens HTML
as a short-lived authenticated local blob for printing, and downloads direct
server-generated PDF output without exposing bearer credentials in a URL.
Site-specific report extension hooks and production-source acceptance remain
explicit parity work.

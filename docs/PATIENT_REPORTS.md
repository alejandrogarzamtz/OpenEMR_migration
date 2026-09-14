# Printable patient reports

OpenRM provides an authenticated comprehensive patient report at
`GET /api/v1/patients/{patient_uuid}/report.html`. It follows the principal
sections of OpenEMR's Patient Report while rendering only data already migrated
into typed target models.

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

The React chart opens the authenticated response as a short-lived local blob
and invokes the browser print dialog. Browsers can save the result as PDF
without exposing bearer credentials in a URL. Direct server-side PDF output,
configurable section selection and site-specific report extension hooks remain
explicit parity work.

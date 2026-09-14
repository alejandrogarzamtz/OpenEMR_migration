# Patient portal record access

OpenRM treats portal identity and clinical-record publication as separate
security boundaries. A valid patient session proves who is making the request;
it does not make every record for that patient automatically visible.

## Publication contract

- Appointments are read-only and selected by the authenticated portal
  account's internal `patient_id`.
- Laboratory results are hidden until staff release them. Only `final` and
  `corrected` results are eligible; preliminary and cancelled results cannot be
  released.
- Documents are private on upload and require an explicit staff release.
- Clinical forms are private on creation and require both a valid signature and
  an explicit staff release.
- Revocation clears the publication state immediately. Portal list and content
  routes always re-check current state rather than relying on a prior response.

Staff publication stores both the release timestamp and staff identity. Portal
list and download activity is written to `identity_audit_events` with the portal
account and patient identity. Requests for another patient's known document UUID
return the same not-found response as an unknown document.

## API surface

Patient routes are under `/api/v1/portal`: `appointments`, `results`,
`documents`, document `content`, and `forms`. Staff release and revoke routes
are attached to the corresponding patient, laboratory result, or laboratory
order resources. The OpenAPI document at `/docs` is the executable contract.

The `billing/statement` route contains only claims explicitly released by
staff. Payment intent history is patient- and portal-account-bound. The payment
contract is detailed in [Portal Billing and Payments](PAYMENTS.md).

## Deployment controls

Operators can disable portal areas independently with:

```text
PORTAL_APPOINTMENTS_ENABLED
PORTAL_RESULTS_ENABLED
PORTAL_DOCUMENTS_ENABLED
PORTAL_FORMS_ENABLED
PORTAL_BILLING_ENABLED
```

All default to `true` in the development environment. Disabling an area makes
its portal route unavailable; it does not delete data or change release state.

## Current limitations

Live payment-processor adapters, portal password recovery, portal MFA,
authorized representatives and proxy access, patient-entered questionnaires, configurable delayed-result
release, bulk document archives, and notification preferences remain parity
work. The portal must not be described as a complete OpenEMR replacement until
those workflows and their organization-specific policies are verified.

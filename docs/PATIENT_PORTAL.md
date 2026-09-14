# Patient portal record access

OpenRM treats portal identity and clinical-record publication as separate
security boundaries. A valid patient session proves who is making the request;
it does not make every record for that patient automatically visible.

Portal identities support one-time, non-enumerating email recovery and optional
encrypted TOTP MFA with one-use recovery codes. Both use portal-only tables and
routes, and successful recovery revokes every existing portal session. See
[Authentication](AUTHENTICATION.md) for the complete lifecycle.

## Patient contexts and representative access

A portal identity may own a patient record, represent one or more patients, or
do both. Representatives receive their own credentials; shared patient
credentials are not used. A family or demographic relationship alone never
authorizes access.

Authorized staff create a patient-specific grant that records the relationship,
authority or consent basis, optional evidence reference, validity dates, and
the allowed areas: appointments, records, documents, forms, messages, and
billing. Representative requests must identify an active patient context with
the `X-Portal-Patient` header. Every protected route resolves that context and
scope from current database state, so expiration or revocation takes effect on
the next request even when the representative still has a valid login session.

The portal context switcher displays only the account owner's record and active
grants. Staff manage representative identities and grant history from the
communications workspace. Grant, revoke, and representative portal activity is
audited with both the acting identity and target patient whenever applicable.

## Publication contract

- Appointments are read-only and selected by the resolved patient context.
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

Patient routes are under `/api/v1/portal`: `contexts`, `appointments`, `results`,
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

Live payment-processor adapters, patient-entered questionnaires, configurable delayed-result
release, bulk document archives, and notification preferences remain parity
work. The portal must not be described as a complete OpenEMR replacement until
those workflows and their organization-specific policies are verified.

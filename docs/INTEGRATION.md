# Integration contract

External projects should integrate through `/api/v1` or `/fhir`; direct access
to application tables is not a supported contract. OpenAPI is available at
`/openapi.json` and FHIR capability discovery at `/fhir/metadata`.

The current bearer JWT is for development only. The stable production contract
will use OAuth 2.1/SMART scopes, asymmetric signing, organization/tenant and
patient context, idempotency keys for writes, cursor pagination, RFC 7807-style
errors, signed webhooks and explicit API deprecation windows.

For each consuming project, add contract tests that pin the API version and
exercise authentication, patient lookup, clinical reads/writes, audit context,
retry behavior and webhook verification. Integration-specific requirements
belong in this document and in executable tests, not in undocumented database
coupling.


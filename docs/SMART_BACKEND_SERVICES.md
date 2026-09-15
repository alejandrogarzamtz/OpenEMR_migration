# SMART Backend Services

OpenRM implements the asymmetric backend-services profile from SMART App
Launch 2.2 for pre-authorized, headless FHIR integrations. Discovery is
available at `GET /fhir/.well-known/smart-configuration`.

An administrator registers a client name, stable client ID, public JWKS and
the exact `system/Resource.r`, `.s`, or `.rs` scopes it may request. Only RSA
or EC public keys using RS384 or ES384 are accepted. Private keys are never
uploaded to OpenRM. Registration, token issuance and client revocation are
audited.

The client signs a one-time JWT assertion and posts it to
`/oauth2/default/token` with:

- `grant_type=client_credentials`
- one or more pre-authorized `system/` scopes
- `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer`
- `client_assertion=<signed JWT>`

The assertion must use a registered `kid`, identify the client in both `iss`
and `sub`, target the advertised token URL in `aud`, expire within five
minutes, and contain `iat`, `exp`, and a unique `jti`. Assertion replay is
persistently rejected. Issued access tokens live for at most five minutes,
cannot access `/api/*`, and are checked against both the registered client
scope and the owning OpenRM user's permissions on every FHIR request.

`POST /oauth2/default/introspect` and `POST /oauth2/default/revoke` require a
new signed client assertion. Disabling a client immediately revokes all its
active sessions. OAuth responses prohibit caching.

Set `API_PUBLIC_URL` to the externally reachable HTTPS origin before
registration or production use. The value becomes the exact token audience;
reverse-proxy rewriting must preserve it. TLS termination and private-key
custody are deployment responsibilities.

Interactive EHR/patient launch, authorization-code + PKCE, OpenID Connect,
patient/user launch context, and Bulk Data export are separate remaining
profiles and are not advertised by this backend-only implementation.

Specification: [SMART App Launch 2.2 Backend Services](https://hl7.org/fhir/smart-app-launch/backend-services.html).

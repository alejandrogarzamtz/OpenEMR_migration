# SMART App Launch

OpenRM implements SMART App Launch 2.2 for interactive applications and
pre-authorized backend services. Discovery is available at
`GET /fhir/.well-known/smart-configuration`.

## Interactive applications

Public applications use Authorization Code with mandatory PKCE S256. Redirect
URIs are compared exactly; authorization requests, launch handles and codes
expire after five minutes; launch handles and codes are single-use; and the
client's `state` and OIDC `nonce` are preserved and validated by the protocol.
Standalone, EHR and patient-portal launches are supported.

Interactive permissions use SMART v2 `user/Resource.rs` and
`patient/Resource.rs` scopes. Patient scopes are enforced against the selected
launch compartment for both searches and individual reads. EHR launches can
bind a patient and encounter. Patient launches are restricted to the portal
identity's own record or an active representative grant.

Requests for `openid fhirUser` receive an RS256 ID Token with issuer, audience,
nonce, stable subject and a resolvable Practitioner or Patient `fhirUser` URL.
The public signing key is exposed by `/oauth2/default/jwks`; OIDC discovery is
available from both `/fhir/.well-known/openid-configuration` and the issuer-based
`/.well-known/openid-configuration/fhir` path.

OpenRM does not advertise `offline_access`, so interactive refresh tokens are
intentionally not issued. Applications obtain a new authorization after the
five-minute access token expires or is revoked.

## Backend services

Administrators register a client ID, public JWKS and exact `system/Resource.r`,
`.s` or `.rs` scopes. Only RSA or EC public keys using RS384 or ES384 are
accepted; private key material is rejected. The client authenticates at
`/oauth2/default/token` with `client_credentials` and a one-time
`private_key_jwt` assertion whose `iss` and `sub` equal the client ID and whose
`aud` is the advertised token endpoint. Persistent `jti` replay protection,
introspection and revocation are enforced.

Every SMART token is restricted to `/fhir/*`, remains bounded by the owning
OpenRM user's ACL and is checked against its granted SMART scopes. Disabling a
client immediately revokes all active sessions. OAuth responses prohibit
caching.

## Administration and deployment

The React administration workspace registers backend or interactive clients.
Interactive registrations contain exact redirect URIs, a launch URI, supported
launch types and least-privilege scopes. Authenticated staff and portal flows
create launch handles through `POST /api/v1/smart/launches`.

Set `API_PUBLIC_URL` to the externally reachable HTTPS origin. For stable OIDC
signatures, mount an access-restricted PEM RSA private key and configure
`SMART_OIDC_PRIVATE_KEY_PATH` plus `SMART_OIDC_KEY_ID`. Production refuses to
issue OIDC tokens without that key; development generates an ephemeral 3072-bit
key when no path is configured. TLS termination, signing-key
rotation and external deployment-profile validation remain operator duties.

Specification: [SMART App Launch 2.2](https://hl7.org/fhir/smart-app-launch/STU2.2/).

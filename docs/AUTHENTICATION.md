# Authentication and session architecture

OpenRM keeps staff and patient identities separate while applying the same
server-side session guarantees to both. Staff users authenticate at
`/api/v1/auth/token`; patient portal accounts authenticate at
`/api/v1/portal/auth/token`.

## Token lifecycle

1. A successful login creates an `auth_sessions` row containing the identity,
   current access-token identifier, refresh-token digest, expiry, client
   metadata and revocation state.
2. The API returns a short-lived signed JWT. The React application keeps it in
   memory rather than browser storage.
3. A high-entropy refresh credential is placed in an identity-specific
   `HttpOnly`, `SameSite=Strict` cookie. Staff and portal cookie paths are
   isolated.
4. Refresh rotates both the refresh credential and access `jti`. The previous
   access JWT becomes invalid immediately. Reuse of the immediately preceding
   refresh credential revokes the whole session.
5. Logout revokes the session row and deletes its refresh cookie. Every API
   request checks JWT signature and expiry plus the current server-side session
   and `jti`, so revocation does not wait for JWT expiration.

The database stores SHA-256 digests of high-entropy refresh values, never the
credentials themselves. Legacy access and refresh tokens are not imported.

## Password recovery

`POST /api/v1/auth/password-reset/request` always returns the same accepted
response, whether or not the email identifies an active user. For an active
account it invalidates older unused reset tokens, creates a 30-minute one-time
token, and queues a delivery in `communication_deliveries`.

`POST /api/v1/auth/password-reset/confirm` consumes that token, applies a new
Argon2 password hash, and revokes every active staff session for the account.
The React recovery screen is available at `/reset-password`.

## Production configuration

- Generate `JWT_SECRET` with a cryptographically secure secret manager and
  rotate it through a controlled deployment procedure.
- Set `SECURE_COOKIES=true` behind HTTPS. Do not expose authentication over
  plaintext transport.
- Set `PUBLIC_WEB_URL` to the canonical HTTPS web origin so reset links cannot
  point to an untrusted host.
- Keep `CORS_ORIGINS` to an explicit allowlist; wildcard origins are
  incompatible with credentialed requests.
- Configure and monitor the email outbox worker before enabling staff password
  recovery in a live environment.
- Review session retention, administrative session/device controls, password
  history, MFA and SSO requirements before production rollout; these remain
  open in the parity ledger.

Automated tests cover rotation, prior-token replay, immediate access-token
invalidation, logout, reset non-enumeration, single use, password replacement,
global session revocation, and the equivalent portal refresh/logout lifecycle.

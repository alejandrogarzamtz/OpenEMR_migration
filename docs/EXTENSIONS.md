# Extensions and webhooks

OpenRM extensions integrate through a versioned, out-of-process API. The
platform does not load third-party Python or execute legacy PHP modules inside
the FastAPI process. This boundary keeps extension failure, dependency and
deployment risk separate from clinical request handling while providing a
documented migration path for integrations and community modules.

## Extension lifecycle

Administrators install a strict JSON manifest through
`POST /api/v1/admin/extensions`. A manifest declares an immutable extension
key, semantic version, API version, capabilities and every event the extension
may publish. Unknown fields, capabilities and malformed event names are
rejected. Administrators can update manifest metadata and version, enable or
disable a package, and rotate its credential. Every lifecycle change is
audited.

An extension credential has the form `ext.{extension_uuid}.{secret}` and is
sent in `X-OpenRM-Extension-Key`. OpenRM stores only its SHA-256 digest and
returns the plaintext credential once, when it is issued or rotated. Disabling
an extension immediately prevents authentication and stops new deliveries to
subscriptions owned by that extension.

The public `GET /api/v1/extensions/sdk` endpoint describes the current `v1`
authentication, event-envelope, signature and payload-size contracts.

## Integration events

Application mutations create durable `api.mutation` events. Extensions with
the `events:publish` capability can publish only events declared in their
manifest and only inside `extension.{extension-key}.*`. Extension event data is
limited to 64 KiB.

Every event has a stable UUID, type, schema version, occurrence time, optional
resource reference and JSON data. Matching uses exact event names, `*`, or a
namespace pattern such as `extension.lab-bridge.*`. An event and each matching
delivery are committed to PostgreSQL before delivery is attempted.

## Webhook delivery

Administrators create subscriptions with an HTTPS endpoint, event patterns and
a bounded retry count. The subscription secret is encrypted at rest and shown
only on creation or rotation. Delivery sends the canonical event JSON as the
unmodified request body with these headers:

- `OpenRM-Webhook-Id`: stable delivery UUID;
- `OpenRM-Webhook-Timestamp`: Unix timestamp;
- `OpenRM-Webhook-Signature`: `v1=` followed by an HMAC-SHA256 digest.

The signed bytes are:

```text
{delivery_id}.{unix_timestamp}.{raw_body}
```

Consumers must verify the signature against the raw body, reject stale
timestamps, and retain processed delivery IDs before applying side effects.
Delivery is at least once: a timeout may occur after a consumer has accepted a
request, so idempotency is required.

The worker retries non-2xx responses and transport failures with exponential
backoff starting at 30 seconds and capped at 24 hours. Exhausted deliveries
enter `dead-letter` state and can be explicitly replayed by an administrator.
Database row locking with `SKIP LOCKED` prevents concurrent workers from
claiming the same due row on PostgreSQL.

Webhook URLs must use HTTPS and cannot contain embedded credentials or
fragments. Literal local/private addresses are rejected at registration. DNS
is resolved again immediately before every request, and a destination is
rejected if any resolved address is private, local, reserved or otherwise not
globally routable. HTTP redirects are not followed. These application checks
reduce SSRF exposure; production egress controls must independently restrict
where the API service can connect and remove the remaining DNS time-of-check to
time-of-use risk.

## Python SDK

The dependency-free reference client is in `sdk/python`:

```bash
python -m pip install ./sdk/python
```

`ExtensionClient` reads extension identity and publishes declared events.
`verify_webhook` verifies signatures, timestamp tolerance and optional replay
detection. See the package README and tests for an end-to-end example.

## Legacy module compatibility

The importer maps the legacy `modules` registry into `extension_packages`,
including status, version, description, hook declarations, module settings,
ACL sections and user/group assignments, and complete source-row evidence.
Configuration metadata is retained, but values are represented only by SHA-256
evidence hashes; legacy secrets are never copied into extension manifests.

Imported legacy modules use API version `legacy`. This records inventory and
migration evidence; it does not claim binary compatibility. A legacy module
must be adapted to the `v1` API or reimplemented as an out-of-process service
before it can participate in the modern extension contract.

## Operational boundary

The administration workspace can install, update, enable and disable
extensions; create subscriptions; inspect recent delivery state; and invoke or
replay delivery processing. Continuous worker scheduling, production secret
management, external receiver acceptance, monitoring, alerting and egress
policy verification are deployment acceptance work.

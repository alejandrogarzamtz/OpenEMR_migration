# Portal billing and payments

OpenRM separates statement visibility, payment processing, and accounting. A
claim is not visible merely because it belongs to the authenticated patient;
authorized staff must explicitly release it. Revocation is refused while a
payment is processing.

## Statement boundary

`GET /api/v1/portal/billing/statement` selects released claims using the
authenticated portal account's internal patient identifier. It calculates each
claim and aggregate charge, payment, and balance value using decimal database
amounts. Another patient receives no indication that a claim UUID exists.

This initial statement represents normalized claims and their payments. Legacy
adjustments, payer/patient allocation, unapplied credits, aging and payment
plans remain explicit parity work and must not be inferred from the current
balance response.

## Payment intent lifecycle

`POST /api/v1/portal/billing/payment-intents` requires an `Idempotency-Key` and
a released claim. The key is unique per portal account. Repeating the same key
and request returns the original intent; changing the claim or amount produces
a conflict. Processing intents reserve their amount when availability is
checked.

The client sends only an opaque, short-lived payment-method token created by a
provider-hosted field or SDK. OpenRM passes that token to the adapter and never
stores it. The database retains the request fingerprint, amount, currency,
state, failure code and processor reference. A `claim_payment` is created only
after the processor reports success. Failed or unavailable processing never
reduces the patient balance.

The production-safe default is:

```text
PAYMENT_PROVIDER=disabled
```

The deterministic `test` adapter accepts only `tok_test_*` values and is usable
only when `DEPLOYMENT_ENVIRONMENT=test`; setting it in development or production
still produces an unavailable-processor result. It must never be used to
represent a real charge.

## Production adapter requirements

A Stripe, Authorize.Net or other adapter is not complete until it provides:

- provider-hosted tokenization so PAN and CVV never enter OpenRM;
- the OpenRM intent UUID as the processor idempotency key;
- bounded timeouts and redacted structured logs;
- signed, replay-protected webhook handling;
- recovery for an interrupted request after an external success;
- refund, dispute and reconciliation records;
- sandbox contract tests and operator runbooks.

Selecting a provider and obtaining sandbox credentials are external decisions.
The adapter, webhooks and reconciliation remain internal engineering work and
are not marked complete merely because credentials are absent.

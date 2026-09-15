# External integrations

| Integration | Legacy behavior | Replacement/configuration | Test/blocker state |
|---|---|---|---|
| SMTP/email and queues | PHPMailer, templates and `email_queue` | durable `communication_deliveries` outbox with preference-aware, PHI-free notices and one-time recovery links; the processor has explicit disabled/test modes and a production adapter will use secret-managed SMTP configuration | enqueue, inspection/retry, deterministic processing and legacy queue/log import are implemented; SMTP transport and live verification require deployment credentials |
| SMS/voice notifications | configurable notification providers and CLI command | provider adapter with signed callbacks and secret env vars | provider credentials block live verification only |
| Clearinghouses/X12 | 837/835 generation/import and partner transport | deterministic X12 engine plus SFTP/API adapters | partner sandbox credentials block transport, not file golden tests |
| Eligibility | payer eligibility requests and stored responses | payer adapter and auditable request/result records | payer credentials block live verification |
| eRx/EPCS | pharmacy routing, controlled-drug workflows and logs | certified network adapter; strict clinician/MFA policy | certification and vendor credentials block live verification |
| Labs | procedure orders/results and vendor/HL7 exchange | HL7/file/API adapters with idempotency | vendor endpoints and credentials block live exchange |
| FHIR/SMART/OAuth | R4 US Core API, launches, scopes and bulk export | FastAPI FHIR module plus SMART 2.2 standalone/EHR/patient launch, Authorization Code + PKCE, OIDC, asymmetric backend clients, compartment scopes, replay protection, introspection and revocation | automated backend and interactive contract tests implemented; Bulk Data and formal deployment-profile validation remain FHIR work |
| C-CDA/CCR/EHI | document generation, import, validation and patient export | background export/import jobs and validators | no external blocker for fixture tests |
| Direct messaging | secure messaging and delivery log | internal patient portal messaging is implemented; Direct/HISP remains a separate adapter with immutable delivery state | internal isolation is tested; adapter implementation remains and HISP credentials block live verification |
| Payments | Authorize.Net/Stripe/Omnipay plus historical Sphere audit/reversals | released statements, provider-neutral idempotent token-only intents and lossless gateway-audit/reversal history exist; production adapters require hosted tokenization, signed webhooks and reconciliation; never store token, PAN or CVV | disabled and deterministic test adapters are verified; historical encrypted audit detail requires the source installation keys, and live Sphere void/credit or replacement-provider charges require provider selection, sandbox credentials and a webhook endpoint |
| Google services | API client for configured workflows | optional OAuth client adapter | credentials block live verification |
| RingCentral | messaging/telephony client | optional provider adapter | credentials block live verification |
| Document/object storage | local/flysystem backends | encrypted local/S3-compatible storage abstraction | object-store credentials block remote verification |
| DICOM/imaging | external viewers and image handling | viewer/PACS adapter; no PHI in URLs/logs | PACS endpoint blocks live verification |

Secrets belong only in environment/secret stores. All adapters require bounded
timeouts, retry/idempotency policy, redacted structured logs and mocked contract
tests before live credentials are used.

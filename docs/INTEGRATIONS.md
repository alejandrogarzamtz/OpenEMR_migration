# External integrations

| Integration | Legacy behavior | Replacement/configuration | Test/blocker state |
|---|---|---|---|
| SMTP/email and queues | PHPMailer, templates and `email_queue` | transactional outbox; SMTP host/port/TLS/user/password/from env vars | implementation pending; delivery verification requires test SMTP |
| SMS/voice notifications | configurable notification providers and CLI command | provider adapter with signed callbacks and secret env vars | provider credentials block live verification only |
| Clearinghouses/X12 | 837/835 generation/import and partner transport | deterministic X12 engine plus SFTP/API adapters | partner sandbox credentials block transport, not file golden tests |
| Eligibility | payer eligibility requests and stored responses | payer adapter and auditable request/result records | payer credentials block live verification |
| eRx/EPCS | pharmacy routing, controlled-drug workflows and logs | certified network adapter; strict clinician/MFA policy | certification and vendor credentials block live verification |
| Labs | procedure orders/results and vendor/HL7 exchange | HL7/file/API adapters with idempotency | vendor endpoints and credentials block live exchange |
| FHIR/SMART/OAuth | R4 US Core API, launches, scopes and bulk export | FastAPI standards module and OAuth authorization server | conformance implementation pending |
| C-CDA/CCR/EHI | document generation, import, validation and patient export | background export/import jobs and validators | no external blocker for fixture tests |
| Direct messaging | secure messaging and delivery log | Direct/HISP adapter and immutable status log | HISP credentials block live verification |
| Payments | Authorize.Net/Stripe/Omnipay | token-only payment adapter; webhook signatures; never store PAN | sandbox credentials block live charges |
| Google services | API client for configured workflows | optional OAuth client adapter | credentials block live verification |
| RingCentral | messaging/telephony client | optional provider adapter | credentials block live verification |
| Document/object storage | local/flysystem backends | encrypted local/S3-compatible storage abstraction | object-store credentials block remote verification |
| DICOM/imaging | external viewers and image handling | viewer/PACS adapter; no PHI in URLs/logs | PACS endpoint blocks live verification |

Secrets belong only in environment/secret stores. All adapters require bounded
timeouts, retry/idempotency policy, redacted structured logs and mocked contract
tests before live credentials are used.


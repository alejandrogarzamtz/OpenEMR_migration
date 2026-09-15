# Patient engagement

OpenRM separates patient and staff identities while supporting coordinated, auditable communication around a patient record.

Patients and authorized representatives can use explicit patient-context grants to exchange secure messages, complete questionnaires assigned by clinical staff, receive an in-application notification inbox, and control channel and event preferences. Questionnaire submissions are patient-scoped, validated against the assigned definition, scored on the server, and recorded with the portal identity that submitted them. A completed assignment cannot be submitted again.

The staff workspace supports patient messaging, questionnaire assignment, staff group threads, replies, read state, and thread closure. These operations use role-based authorization and the clinical audit trail.

## Delivery boundary

Email and SMS messages use the durable `communication_deliveries` outbox. `NOTIFICATION_DELIVERY_MODE=disabled` retains pending deliveries without claiming transport; `test` completes deliveries without contacting an external provider. Production SMTP, SMS, and Direct adapters require deployment-specific credentials and are intentionally not represented as live integrations.

Legacy `questionnaire_repository`, `questionnaire_response`, `notification_log`, `email_queue`, portal messages, and clinical tasks are covered by the idempotent import path. Original source rows remain available in `legacy_payload` for reconciliation.

## Main API groups

- `/api/v1/patients/{patient_uuid}/questionnaire-assignments`
- `/api/v1/portal/questionnaires`
- `/api/v1/portal/notifications` and `/api/v1/portal/notification-preferences`
- `/api/v1/staff-message-threads`
- `/api/v1/communications/outbox` and `/api/v1/communications/outbox/process`

Portal feature switches and delivery mode are documented in `.env.example`.

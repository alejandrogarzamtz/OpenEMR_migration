# OpenRM

OpenRM is a community-oriented, open-source platform for managing longitudinal
health records and the operational workflows around care delivery. Its purpose
is to give clinics, practitioners, administrators, patients, and integrators a
durable system for clinical documentation, scheduling, communication, billing,
reporting, and standards-based health-data exchange.

Healthcare software must preserve years of clinically and financially
significant behavior while remaining safe and practical to maintain as
technology, regulations, and interoperability standards evolve. OpenRM is
addressing that problem by building a modern application architecture around
the proven domain knowledge in OpenEMR. The preserved OpenEMR application is the
behavioral and data reference; OpenRM is being developed as a modular platform
with explicit APIs, testable business rules, and an approachable contributor
experience.

This is an active modernization effort. It is not yet a drop-in production
replacement for every OpenEMR workflow. Progress is measured against a
repository-derived functional parity ledger, and incomplete functionality is
identified rather than presented as finished.

## Why OpenRM is being modernized

OpenEMR contains decades of healthcare workflow knowledge, extensive
configuration options, and broad interoperability support. It also reflects the
architecture of a large server-rendered PHP application: request logic,
database access, session state, templates, and UI behavior are frequently
coupled. That raises the cost of testing, extending, operating, and onboarding
contributors.

OpenRM is moving these capabilities to a modern, maintainable stack while
preserving the behavior and data relationships that healthcare organizations
depend on. The modernization is intended to provide:

- explicit, versioned API contracts for first-party and external clients;
- backend-enforced authorization and auditable access to protected data;
- independently testable domain services and business rules;
- a responsive, accessible frontend built from reusable feature modules;
- repeatable database migrations and lossless legacy-data reconciliation;
- reproducible local and production-oriented container workflows;
- clear extension points for integrations and community-developed modules.

## Architecture

OpenRM uses a separated web and API architecture:

| Layer | Technology | Responsibility |
|---|---|---|
| Web application | React 19, TypeScript, Vite | Feature-oriented workflows, forms, navigation, validation, and API consumption |
| Application API | Python 3.13, FastAPI, Pydantic | Versioned REST resources, validation, authentication, authorization, and OpenAPI contracts |
| Domain and data access | SQLAlchemy 2 | Transactions, repositories, services, and explicit persistence models |
| Schema evolution | Alembic | Ordered, reviewable database migrations and rollback paths |
| Primary database | PostgreSQL 17 | New application data and constraints |
| Legacy compatibility | MySQL/MariaDB adapters | Idempotent import, stable legacy identifiers, lossless staging, and reconciliation |
| Interoperability | REST and FHIR modules | Standards-based exchange and compatibility contracts as parity advances |
| Development runtime | Docker Compose | Reproducible database, API, and frontend services |

The repository keeps the original application under `openemr-legacy/`. It is
reference material for discovering routes, schema, authorization, forms,
reports, jobs, and business rules. New code lives in `backend/` and `frontend/`;
migration controls and architectural records live in `docs/`.

```text
.
├── backend/          FastAPI application, SQLAlchemy models, Alembic, tests
├── frontend/         React and TypeScript application and tests
├── docs/             Architecture, parity, database, and integration records
├── scripts/          Repeatable discovery and verification utilities
└── openemr-legacy/   Preserved OpenEMR behavioral reference
```

## What is available today

The current implementation provides a tested foundation and several initial
end-to-end healthcare workflows:

- Argon2 password authentication with short-lived JWT access tokens, persistent
  server-side sessions, rotating `HttpOnly` refresh cookies, replay detection,
  immediate logout revocation, non-enumerating one-time password recovery, and
  encrypted TOTP MFA with one-use recovery codes;
- backend-enforced, OpenEMR-compatible ACL section/value grants;
- expanded patient search, demographics, address, communication consent, and
  lossless legacy-data preservation;
- resource-aware appointment creation, filtering, conflict detection, status
  transitions, cancellation, and legacy appointment import;
- a live patient-flow board with immutable arrival, room, and status history
  synchronized with scheduled appointments;
- medication and supply inventory with warehouse lots, expiration-aware FEFO
  dispensing, stock movements, destruction records, and lossless legacy import;
- administration of facilities, practitioners and warehouses, with explicit
  facility/warehouse assignments enforced by scheduling and inventory APIs;
- a permission-aware report catalog with reproducible stored runs, totals,
  checksums and authenticated CSV exports for migrated report families;
- separate staff and patient identities, secure patient-bound message threads,
  forced replacement of temporary portal passwords, lockout protection,
  non-enumerating one-time portal recovery, encrypted patient TOTP MFA with
  one-use recovery codes, clinical tasks, consent-aware generic email notices,
  and a durable outbox;
- an isolated patient portal for owned appointments and explicitly released
  final laboratory results, documents, and signed visit forms, with revocation
  controls and identity-linked access auditing;
- explicitly released patient statements and idempotent, token-only portal
  payment intents that never record a payment without processor confirmation;
- encounters, clinical summaries, problems, allergies, medications, laboratory
  orders/results, documents, insurance, charges, claims, payments,
  immunizations, vital signs, prescriptions, signable clinical forms,
  questionnaires, and an initial FHIR surface;
- audit events around implemented reads and mutations;
- containerized PostgreSQL, API, and web development services.

These capabilities do not imply full OpenEMR parity. Specialized clinical
forms, patient relationships, recurrence rules, broader portal workflows,
remaining reports, advanced inventory, billing exchanges, FHIR resources, integrations, administrative
tools, and background services are still being implemented. The authoritative
status is maintained in [Functional Parity](docs/FUNCTIONAL_PARITY.md) and the
generated [Legacy API Inventory](docs/LEGACY_API_INVENTORY.md).

## Project direction

OpenRM is being designed for long-term use rather than a one-time conversion.
The direction of the project is to make each healthcare capability:

- **Maintainable:** cohesive feature modules, typed contracts, explicit
  dependencies, and reviewable schema changes;
- **Extensible:** stable APIs and integration boundaries that do not require
  modifying unrelated clinical code;
- **Reliable:** business-rule, authorization, import-reconciliation, contract,
  and user-flow tests proportionate to healthcare risk;
- **Performant:** bounded queries, pagination, asynchronous work where justified,
  and observable runtime behavior;
- **Approachable:** one reproducible workflow, useful documentation, predictable
  conventions, and actionable test failures;
- **Community-ready:** transparent parity tracking, documented decisions, and
  space for clinics, implementers, developers, and standards experts to shape
  behavior with evidence from real workflows.

A capability is considered verified only when its data mapping, API, UI,
authorization, tests, and legacy behavior comparison are accounted for.
External services requiring vendor credentials are tracked separately from
implementation work.

## Getting started

### Prerequisites

- Docker Desktop or another Docker Engine with Compose v2
- Git
- At least 4 GB of memory available to the development stack

### Run the development stack

```bash
git clone https://github.com/alejandrogarzamtz/OpenEMR_migration.git
cd OpenEMR_migration
cp .env.example .env
docker compose up --build
```

Local services:

- Web application: <http://localhost:5173>
- Patient portal: <http://localhost:5173/portal>
- REST/OpenAPI documentation: <http://localhost:8000/docs>
- API health endpoint: <http://localhost:8000/health>
- PostgreSQL: port `5432` inside the Compose environment

The Compose environment supplies local-only bootstrap credentials:

```text
admin@example.com
change-me-now
```

Production deployments must omit bootstrap credentials, provide a unique JWT
secret through a secret manager, and provision administrators through a
controlled process.

Set `SECURE_COOKIES=true` whenever HTTPS is used. Refresh credentials are kept
in identity-specific `HttpOnly`, `SameSite=Strict` cookies; access tokens remain
in browser memory, are rotated by the web client, and every authenticated
request is checked against a revocable server-side session. Password recovery queues a one-time link in the
communication outbox and requires a configured email delivery worker for live
use.

Patient portal accounts are created by authorized staff for patients whose
portal access has been enabled. Temporary passwords must be replaced before a
patient can access protected information. Representatives use separate portal
identities and explicit patient grants with recorded relationship, authority,
validity, and least-privilege scopes; a relationship alone does not confer
access. The portal provides a patient-context switcher, and revocation is
enforced on the next request without waiting for the login session to expire.
Appointments are restricted to the resolved patient context. Clinical results, documents, and visit forms remain
private until authorized staff explicitly release them; only final or corrected
results and signed forms are eligible. Staff can revoke access immediately, and
portal record reads and downloads are recorded against the portal identity.
Each record area can be disabled with the corresponding `PORTAL_*_ENABLED`
environment setting. Live email delivery additionally requires a configured
provider; the internal outbox remains available without one for local
development and integration testing. See [Patient Portal](docs/PATIENT_PORTAL.md)
for the release and isolation contract.

Patients can recover access through a non-enumerating email flow at
`/portal/reset-password` and enable authenticator-app MFA from the signed-in
portal. Reset links are hashed, expire, work once, and revoke existing portal
sessions; recovery does not silently remove an enrolled second factor.

Online payments are disabled by default. OpenRM stores payment-intent state and
processor references, but never card numbers, security codes, or payment-method
tokens. A real charge requires a separately configured and verified processor
adapter; see [Portal Billing and Payments](docs/PAYMENTS.md).

Stop services without deleting the database volume:

```bash
docker compose down
```

### Database migrations

The API container applies Alembic migrations before startup. They can also be
managed explicitly:

```bash
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic current
docker compose run --rm api alembic history
```

Never run target migrations against a production OpenEMR database. Legacy data
is read through compatibility adapters and reconciled into the new schema. Read
[Database Migration](docs/DATABASE_MIGRATION.md) before working with real data.

## Development and verification

Build images after dependencies or source files change:

```bash
docker compose build api web
```

Run backend tests:

```bash
docker compose run --rm --no-deps api pytest -q
```

Run frontend tests, type checking, and the production build:

```bash
docker compose run --rm --no-deps web npm test
docker compose run --rm --no-deps web npm run typecheck
docker compose run --rm --no-deps web npm run build
```

Regenerate the deterministic legacy inventories:

```bash
python3 scripts/audit_legacy.py
```

Generated changes should be reviewed and committed with the source change that
caused them. A green test suite proves only the behavior covered by those tests;
it does not by itself prove complete functional parity.

## Understanding the system

Start with these documents:

- [Functional Parity](docs/FUNCTIONAL_PARITY.md) — binding migration and
  verification ledger;
- [Legacy System Map](docs/LEGACY_SYSTEM_MAP.md) — technology, workflows, and
  architectural risks in the reference application;
- [Legacy API Inventory](docs/LEGACY_API_INVENTORY.md) — every discovered legacy
  REST, portal, and FHIR route with replacement and test status;
- [Report Parity Ledger](docs/REPORT_PARITY.md) — every discovered legacy report
  and its individual migration status;
- [Database Migration](docs/DATABASE_MIGRATION.md) — preservation, mapping,
  reconciliation, and cutover rules;
- [Authentication](docs/AUTHENTICATION.md) — staff/portal identity separation,
  token lifecycle, revocation, recovery, and production controls;
- [Patient Portal](docs/PATIENT_PORTAL.md) — record publication, patient
  isolation, auditing, and deployment controls;
- [Portal Billing and Payments](docs/PAYMENTS.md) — statement release,
  idempotency, token handling, accounting, and processor boundaries;
- [Integrations](docs/INTEGRATIONS.md) — external systems, configuration,
  verification strategy, and credential-dependent blockers;
- [Migration Strategy](docs/MIGRATION.md) — architectural decisions and staged
  delivery approach;
- [FHIR Notes](docs/FHIR.md) — current standards implementation and limitations.

## Contributing

Contributions are welcome as the project develops its governance and formal
contributor guide. A useful contribution starts with a specific legacy behavior
and carries that behavior through the full stack.

1. Find or add the feature in `docs/FUNCTIONAL_PARITY.md` and its exact legacy
   route or implementation in the generated inventories.
2. Read the relevant legacy controller, service, schema, template, JavaScript,
   ACL checks, and tests.
3. Implement the domain rule and persistence behavior outside the route handler,
   then expose it through a typed, versioned FastAPI contract.
4. Add the corresponding React workflow, including loading, empty, validation,
   error, and permission states.
5. Add tests for successful behavior, validation failures, authorization denial,
   and legacy-data reconciliation.
6. Run backend tests, frontend tests, type checking, the production build, and
   the legacy audit.
7. Update parity and architecture documentation with evidence. Do not mark a
   feature `VERIFIED` until its complete workflow and legacy outcome have been
   compared.

Keep changes focused and avoid committing secrets, production health data,
runtime databases, dependency folders, or build output. Changes affecting
authentication, authorization, clinical signing, financial calculations, data
import, or destructive migrations require especially clear tests and rollback
reasoning.

## Security and health data

OpenRM handles data that may be highly sensitive. The repository and demo stack
are not substitutes for an organization's security, privacy, compliance,
backup, and disaster-recovery program. Do not use real patient data in
development fixtures. Report suspected vulnerabilities privately to repository
maintainers rather than opening a public issue containing exploit or patient
information.

The security/compliance parity row remains open until controls are implemented
and verified across the complete application.

## License and upstream heritage

The preserved OpenEMR source is licensed under GPL-3.0-or-later; see
`openemr-legacy/LICENSE`. New contributions must remain compatible with the
repository's applicable license and retain attribution for behavior or code
derived from upstream OpenEMR.

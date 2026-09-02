# OpenEMR FastAPI + React migration

Incremental replacement for OpenEMR. The original application is kept in
`openemr-legacy/` as the compatibility reference; new code lives in `backend/`
and `frontend/`.

## Run locally

```bash
docker compose up --build
```

Database migrations run automatically before FastAPI starts. To inspect the
current revision use `docker compose exec api alembic current`.

- React: http://localhost:5173
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health

The development stack uses its own PostgreSQL database. Production migration
must use the adapters and reconciliation process described in
[`docs/MIGRATION.md`](docs/MIGRATION.md), never a one-shot database rewrite.

Demo credentials: `admin@example.com` / `change-me-now`.

Full OpenEMR parity is tracked in
[`docs/PARITY_MATRIX.md`](docs/PARITY_MATRIX.md). Integration consumers must use
the contracts described in [`docs/INTEGRATION.md`](docs/INTEGRATION.md).

## First vertical slice

- JWT authentication with role checks
- patient list, search, create and detail
- immutable audit events for reads and writes
- API and UI tests
- Docker-based local environment

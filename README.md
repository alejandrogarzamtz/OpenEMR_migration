# OpenEMR FastAPI + React migration

Incremental replacement for OpenEMR. The original application is kept in
`openemr-legacy/` as the compatibility reference; new code lives in `backend/`
and `frontend/`.

## Run locally

```bash
docker compose up --build
```

- React: http://localhost:5173
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health

The development stack uses its own PostgreSQL database. Production migration
must use the adapters and reconciliation process described in
[`docs/MIGRATION.md`](docs/MIGRATION.md), never a one-shot database rewrite.

Demo credentials: `admin@example.com` / `change-me-now`.

## First vertical slice

- JWT authentication with role checks
- patient list, search, create and detail
- immutable audit events for reads and writes
- API and UI tests
- Docker-based local environment


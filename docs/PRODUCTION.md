# Production operations and cutover

OpenRM provides a fail-closed production configuration, hardened container
images, deterministic reconciliation gates, encrypted backup/restore tooling
and non-destructive deployment acceptance checks. These controls make a release
reviewable; they do not replace an organization's privacy, security, clinical,
legal or regulatory approval.

## Production architecture

`docker-compose.production.yml` runs PostgreSQL on an internal-only network, a
one-shot Alembic migration, non-root read-only API and worker containers, and a
non-root static web/proxy container bound to loopback. A separately managed TLS
ingress is required in front of port 8080. The database is never published to
the host, and migration completes before API or worker startup.

The API refuses production startup unless PostgreSQL, independent strong JWT
and Fernet secrets, secure cookies, explicit HTTPS URLs and CORS origins,
explicit allowed hosts, a persistent SMART RSA key, and disabled development
bootstrap/test adapters are configured. `/health/live` reports process health;
`/health/ready` also verifies database access, the exact Alembic head and
restrictive SMART key permissions. API responses carry no-store, anti-sniff,
anti-frame, referrer, permissions, CSP and HSTS headers.

Copy `.env.production.example` to a protected location and replace every
example host and file path. Secret files must be readable only by the deployment
operator. Generate values independently:

```bash
openssl rand -base64 64 > /secure/openrm/jwt-secret
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > /secure/openrm/mfa-fernet-key
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out /secure/openrm/smart-oidc-private.pem
chmod 0600 /secure/openrm/*
```

The database URL secret contains the full SQLAlchemy PostgreSQL URL. Keep the
password independently in the PostgreSQL password file as well. Start a pinned
release only after backup and reconciliation evidence exists:

```bash
docker compose --env-file /secure/openrm/production.env \
  -f docker-compose.production.yml pull
docker compose --env-file /secure/openrm/production.env \
  -f docker-compose.production.yml up -d
```

For multi-host or orchestrated deployment, translate the same health checks,
secret mounts, internal network, one-shot migration and non-root/read-only
constraints rather than weakening them.

## Backup and restore drill

The operations image streams a PostgreSQL custom-format dump directly through
`age`; an unencrypted database dump is never written to disk. It records the
encrypted file checksum, byte count and Alembic revision in a sidecar manifest.

```bash
docker compose --env-file /secure/openrm/production.env \
  -f docker-compose.production.yml --profile operations run --rm backup
```

Copy both files to immutable off-site storage. Retention, RPO and RTO are
organization decisions and must be monitored. A backup is not accepted until a
separate restore environment has verified its checksum and completed:

```bash
export DATABASE_URL='postgresql://openrm:...@restore-db/openrm_restore'
export AGE_IDENTITY_FILE=/secure/offline/backup-identity
export CONFIRM_EMPTY_DATABASE_RESTORE=YES
ops/restore.sh backup.dump.age backup.dump.age.manifest.json
```

Restore deliberately refuses a non-empty public schema. After restoration run
Alembic check, application acceptance, row reconciliation and clinical/
financial sampling. Never rehearse against the live database.

## Production-source reconciliation

Take a consistent read-only source snapshot and preserve its identifiers and
time boundary. Run the importer once with `--commit`, then run it again without
`--commit` against the same snapshot and capture JSON. The second pass must be
idempotent: no rows may remain insertable, every source row must be accounted
for, and demographic typed/payload comparisons must match.

```bash
python -m app.import_legacy --source "$LEGACY_DATABASE_URL" --commit
python -m app.import_legacy --source "$LEGACY_DATABASE_URL" > reconciliation.json
python scripts/reconciliation_gate.py reconciliation.json --output reconciliation-evidence.json
```

Unresolved records fail the gate by default. A temporary exception requires an
exact domain/count argument such as `--allow-rejected documents=2`; the
allowance is embedded in evidence and must link to reviewed remediation. It is
never permission to discard the source rows.

## Acceptance, release evidence and cutover

After deployment behind HTTPS, run non-destructive readiness, security-header,
OpenAPI and bounded concurrency checks:

```bash
python scripts/acceptance.py --base-url https://ehr.example.org \
  --release v1.0.0 --requests 100 --output acceptance.json
python scripts/cutover_manifest.py --release v1.0.0 \
  --reconciliation reconciliation-evidence.json \
  --acceptance acceptance.json \
  --backup-manifest backup.dump.age.manifest.json \
  --output cutover-v1.0.0.json
```

The manifest binds the Git commit, source reconciliation, deployed acceptance,
encrypted backup and schema revision. Store it with approval records. Before
switching traffic, clinical and financial owners must compare representative
parallel-run outcomes, verify external integrations, confirm monitoring and
alerting, record the rollback owner, and freeze legacy writes for the final
delta import.

Rollback means stopping new traffic, preserving the failed target for evidence,
restoring the prior application route and resuming the authoritative legacy
system according to the rehearsed time boundary. Do not reverse a database
migration after new clinical writes unless that exact downgrade and data-loss
impact was tested and approved.

## Release supply chain

CI builds both development and production images, validates shell and Compose
contracts, runs reconciliation-gate tests, applies every migration and executes
the backend/frontend suites. CodeQL runs on pushes, pull requests and weekly.
Version tags or an explicit manual release build publish API and web images to
GHCR with GitHub provenance attestations. Put those immutable digests in
`OPENRM_API_IMAGE` and `OPENRM_WEB_IMAGE`; do not deploy mutable tags.

Live SMTP/SMS, payment, clearinghouse, laboratory and other vendor acceptance
still requires the organization's chosen providers and credentials. The
repository does not claim those external systems passed merely because the
application and deployment gates pass.

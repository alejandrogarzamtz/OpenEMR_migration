#!/usr/bin/env python3
"""Static guard for production artifacts that must move together."""
from pathlib import Path
import subprocess

root=Path(__file__).parents[1]
required=["docker-compose.production.yml",".env.production.example",".github/workflows/security.yml",".github/workflows/release.yml","backend/Dockerfile.production","backend/requirements.production.txt","backend/production-entrypoint.sh","backend/app/operational.py","backend/app/worker.py","frontend/Dockerfile.production","frontend/nginx.production.conf","ops/Dockerfile","ops/backup.sh","ops/restore.sh","ops/test_backup_restore.sh","scripts/reconciliation_gate.py","scripts/acceptance.py","scripts/cutover_manifest.py","docs/PRODUCTION.md"]
missing=[name for name in required if not (root/name).is_file()]
if missing:raise SystemExit("missing production artifacts: "+", ".join(missing))
compose=(root/"docker-compose.production.yml").read_text()
for forbidden in ("local-development-secret-change-me","change-me-now","SECURE_COOKIES: \"false\"","0.0.0.0:${OPENRM_HTTP_PORT"):
    if forbidden in compose:raise SystemExit(f"unsafe production compose value: {forbidden}")
for script in ("backend/production-entrypoint.sh","ops/backup.sh","ops/restore.sh","ops/test_backup_restore.sh"):
    subprocess.run(["bash","-n",str(root/script)],check=True)
print("production bundle contract verified")

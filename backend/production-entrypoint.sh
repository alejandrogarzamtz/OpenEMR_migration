#!/bin/sh
set -eu

load_secret() {
  variable="$1"
  file_variable="${variable}_FILE"
  eval "secret_file=\${$file_variable:-}"
  if [ -n "$secret_file" ]; then
    value=$(sed -e 's/[[:space:]]*$//' "$secret_file")
    export "$variable=$value"
  fi
}

load_secret DATABASE_URL
load_secret JWT_SECRET
load_secret MFA_ENCRYPTION_KEY

case "${1:-api}" in
  api) exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips "${TRUSTED_PROXY_IPS:?TRUSTED_PROXY_IPS is required}" ;;
  migrate) exec alembic upgrade head ;;
  worker) shift; exec python -m app.worker "$@" ;;
  *) exec "$@" ;;
esac

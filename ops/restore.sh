#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${AGE_IDENTITY_FILE:?AGE_IDENTITY_FILE is required}"
: "${CONFIRM_EMPTY_DATABASE_RESTORE:?set CONFIRM_EMPTY_DATABASE_RESTORE=YES}"
test "$CONFIRM_EMPTY_DATABASE_RESTORE" = YES
backup="${1:?usage: restore.sh BACKUP.age MANIFEST.json}"
manifest="${2:?usage: restore.sh BACKUP.age MANIFEST.json}"
expected=$(sed -n 's/.*"sha256":"\([a-f0-9]\{64\}\)".*/\1/p' "$manifest")
test -n "$expected"
printf '%s  %s\n' "$expected" "$backup" | sha256sum -c
tables=$(psql "$DATABASE_URL" -XAtc "select count(*) from pg_catalog.pg_tables where schemaname='public'")
test "$tables" = 0 || { echo "target public schema is not empty" >&2; exit 1; }
age --decrypt --identity "$AGE_IDENTITY_FILE" "$backup" | pg_restore --dbname "$DATABASE_URL" --exit-on-error --single-transaction --no-owner --no-acl
psql "$DATABASE_URL" -XAtc 'select version_num from alembic_version'

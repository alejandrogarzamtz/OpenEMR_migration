#!/usr/bin/env bash
set -euo pipefail
: "${ADMIN_DATABASE_URL:?ADMIN_DATABASE_URL is required}"
source_database=openrm_backup_test_source
target_database=openrm_backup_test_target
source_url="${ADMIN_DATABASE_URL%/*}/$source_database"
target_url="${ADMIN_DATABASE_URL%/*}/$target_database"
cleanup() {
  dropdb --if-exists --force --maintenance-db="$ADMIN_DATABASE_URL" "$source_database" >/dev/null
  dropdb --if-exists --force --maintenance-db="$ADMIN_DATABASE_URL" "$target_database" >/dev/null
}
trap cleanup EXIT
cleanup
createdb --maintenance-db="$ADMIN_DATABASE_URL" "$source_database"
createdb --maintenance-db="$ADMIN_DATABASE_URL" "$target_database"
psql "$source_url" -Xv ON_ERROR_STOP=1 -c 'create table alembic_version(version_num varchar(32) primary key); create table recovery_probe(id integer primary key, value text not null); insert into alembic_version values ('"'"'20261111_0072'"'"'); insert into recovery_probe values (1,'"'"'verified'"'"');'
age-keygen --output /tmp/openrm-backup-test-key >/dev/null 2>&1
recipient=$(age-keygen -y /tmp/openrm-backup-test-key)
mkdir -p /tmp/openrm-backup-test
DATABASE_URL="$source_url" AGE_RECIPIENT="$recipient" /usr/local/bin/backup.sh /tmp/openrm-backup-test
backup=$(find /tmp/openrm-backup-test -name '*.dump.age' -type f -print -quit)
DATABASE_URL="$target_url" AGE_IDENTITY_FILE=/tmp/openrm-backup-test-key CONFIRM_EMPTY_DATABASE_RESTORE=YES /usr/local/bin/restore.sh "$backup" "$backup.manifest.json"
test "$(psql "$target_url" -XAtc 'select value from recovery_probe where id=1')" = verified
echo "encrypted backup and empty-target restore verified"

#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT is required}"
output_dir="${1:?usage: backup.sh OUTPUT_DIRECTORY}"
mkdir -p "$output_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="$output_dir/openrm-$timestamp.dump.age"
revision=$(psql "$DATABASE_URL" -XAtc 'select version_num from alembic_version' | tr -d '[:space:]')
test -n "$revision"
pg_dump "$DATABASE_URL" --format=custom --no-owner --no-acl | age --recipient "$AGE_RECIPIENT" --output "$backup"
checksum=$(sha256sum "$backup" | awk '{print $1}')
bytes=$(wc -c < "$backup" | tr -d '[:space:]')
printf '{"created_at":"%s","file":"%s","sha256":"%s","bytes":%s,"schema_revision":"%s"}\n' "$timestamp" "$(basename "$backup")" "$checksum" "$bytes" "$revision" > "$backup.manifest.json"
chmod 0600 "$backup" "$backup.manifest.json"
sha256sum -c <(printf '%s  %s\n' "$checksum" "$backup")

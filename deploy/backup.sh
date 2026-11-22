#!/usr/bin/env bash
# Nightly database backup. Example crontab entry (as the user that runs docker):
#   17 3 * * * cd /opt/shadowtrace && ./deploy/backup.sh >> backups/backup.log 2>&1
# Restore:
#   docker compose exec -T db pg_restore -U shadowtrace -d shadowtrace --clean --if-exists < backups/<file>.dump
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p backups
file="backups/shadowtrace-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U shadowtrace -d shadowtrace -Fc > "$file.tmp"
mv "$file.tmp" "$file"
find backups -name 'shadowtrace-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -u +%FT%TZ) backup written: $file ($(du -h "$file" | cut -f1))"

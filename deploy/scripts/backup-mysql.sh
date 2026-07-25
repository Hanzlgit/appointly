#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
FILENAME="${BACKUP_DIR}/appointly_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

mysqldump \
  -h "${MYSQL_HOST:-mysql}" \
  -u"${MYSQL_USER}" \
  -p"${MYSQL_PASSWORD}" \
  "${MYSQL_DATABASE}" \
  | gzip > "$FILENAME"

find "$BACKUP_DIR" -name "appointly_*.sql.gz" -mtime +14 -delete

echo "Backup saved to ${FILENAME}"

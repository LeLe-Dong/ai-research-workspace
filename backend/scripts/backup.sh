#!/usr/bin/env bash
# AI Research Workspace — daily SQLite backup
# Dumps airw.db to backups/ with rotation (keep 7 days)
set -euo pipefail

DB_PATH="/root/workspace/ai-research-workspace/backend/storage/airw.db"
BACKUP_DIR="/root/workspace/ai-research-workspace/backend/backups"
DATE=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=7

if [ ! -f "$DB_PATH" ]; then
    echo "DB not found: $DB_PATH" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
DEST="$BACKUP_DIR/airw_$DATE.db"

# Use sqlite3 .backup for hot backup (no downtime, no WAL issues)
sqlite3 "$DB_PATH" ".backup '$DEST'" 2>/dev/null || {
    # Fallback: cp if sqlite3 .backup fails
    cp -f "$DB_PATH" "$DEST"
}

# Compress old backups
find "$BACKUP_DIR" -name "airw_*.db" -mtime +1 -exec gzip -f {} \; 2>/dev/null || true

# Rotate: delete gz older than KEEP_DAYS
find "$BACKUP_DIR" -name "airw_*.db.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null || true

# Keep at least 1 uncompressed recent
LATEST=$(ls -t "$BACKUP_DIR"/airw_*.db 2>/dev/null | head -1)
if [ -n "$LATEST" ] && [ "$(find "$LATEST" -mtime +0)" ]; then
    gzip -f "$LATEST" 2>/dev/null || true
fi

echo "backup done: $DEST ($(du -h "$DEST" 2>/dev/null | cut -f1))"
ls -lh "$BACKUP_DIR"/ | tail -5

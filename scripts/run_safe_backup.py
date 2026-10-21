import sqlite3
import sys
from pathlib import Path

src_path = Path("data/ucc_database.db").resolve()
dst_path = Path("backups/sqlite_pre_migration/ucc_database_backup_20261012.db").resolve()

print(f"Source: {src_path}")
print(f"Destination: {dst_path}")

dst_path.parent.mkdir(parents=True, exist_ok=True)

# Open source in read-only URI mode to ensure no write locks or modifications
src_uri = f"file:{src_path.as_posix()}?mode=ro"
src_conn = sqlite3.connect(src_uri, uri=True)
dst_conn = sqlite3.connect(str(dst_path))

try:
    print("Initiating SQLite online backup API...")
    with dst_conn:
        src_conn.backup(dst_conn, pages=100)
    print("Backup completed successfully via sqlite3.backup() API.")
finally:
    src_conn.close()
    dst_conn.close()

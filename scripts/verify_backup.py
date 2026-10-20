import sqlite3
import hashlib
from pathlib import Path
import json

src_path = Path("data/ucc_database.db").resolve()
dst_path = Path("backups/sqlite_pre_migration/ucc_database_backup_20261012.db").resolve()

# 1. SHA256 Checksums
def calc_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

src_sha = calc_sha256(src_path)
dst_sha = calc_sha256(dst_path)

# 2. Check original file size and timestamp
src_stat = src_path.stat()
dst_stat = dst_path.stat()

# 3. Integrity Check on Backup
dst_conn = sqlite3.connect(f"file:{dst_path.as_posix()}?mode=ro", uri=True)
dst_cur = dst_conn.cursor()

dst_cur.execute("PRAGMA integrity_check;")
integrity_results = [r[0] for r in dst_cur.fetchall()]

# 4. Table and Row Count Verification
src_conn = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
src_cur = src_conn.cursor()

src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
src_tables = [r[0] for r in src_cur.fetchall()]

dst_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
dst_tables = [r[0] for r in dst_cur.fetchall()]

table_matches = (src_tables == dst_tables)

row_counts = {}
all_counts_match = True
for t in src_tables:
    s_cnt = src_cur.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
    d_cnt = dst_cur.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
    row_counts[t] = {"source": s_cnt, "backup": d_cnt, "match": (s_cnt == d_cnt)}
    if s_cnt != d_cnt:
        all_counts_match = False

# 5. Primary Key checks on critical tables (drawings, comments, users, categories, departments)
pk_checks = {}
for t in ["drawings", "comments", "users", "categories", "engineering_departments", "audit_logs"]:
    s_pks = set(r[0] for r in src_cur.execute(f'SELECT id FROM "{t}"').fetchall())
    d_pks = set(r[0] for r in dst_cur.execute(f'SELECT id FROM "{t}"').fetchall())
    pk_checks[t] = {
        "count": len(s_pks),
        "match": (s_pks == d_pks),
        "diff": list(s_pks.symmetric_difference(d_pks))
    }

src_conn.close()
dst_conn.close()

manifest = {
    "source_path": str(src_path),
    "source_size_bytes": src_stat.st_size,
    "source_sha256": src_sha,
    "source_mtime": src_stat.st_mtime,
    "backup_path": str(dst_path),
    "backup_size_bytes": dst_stat.st_size,
    "backup_sha256": dst_sha,
    "backup_mtime": dst_stat.st_mtime,
    "integrity_check": integrity_results,
    "table_names_match": table_matches,
    "row_counts": row_counts,
    "primary_key_checks": pk_checks
}

print(json.dumps(manifest, indent=2))
with open("backups/sqlite_pre_migration/backup_manifest.json", "w", encoding="utf-8") as mf:
    json.dump(manifest, mf, indent=2)

print("\nVerification completed successfully.")

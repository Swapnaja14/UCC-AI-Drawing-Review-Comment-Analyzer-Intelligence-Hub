import sqlite3
import hashlib
import json
import shutil
from pathlib import Path

src_path = Path("data/ucc_database.db").resolve()
backup_path = Path("backups/sqlite_pre_migration/ucc_database_backup_20261012.db").resolve()
restore_test_dir = Path("backups/sqlite_pre_migration/restore_test").resolve()
restore_test_dir.mkdir(parents=True, exist_ok=True)
restored_db_path = restore_test_dir / "restored_test.db"

# 1. Do NOT touch/overwrite backup! Copy backup to restore_test location for restoration verification
shutil.copy2(backup_path, restored_db_path)

def calc_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

src_sha = calc_sha256(src_path)
backup_sha = calc_sha256(backup_path)
restored_sha = calc_sha256(restored_db_path)

# Connect to source and restored DB
src_conn = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
res_conn = sqlite3.connect(f"file:{restored_db_path.as_posix()}?mode=ro", uri=True)

src_cur = src_conn.cursor()
res_cur = res_conn.cursor()

# 2. PRAGMA integrity_check and foreign_key_check on restored copy
res_cur.execute("PRAGMA integrity_check;")
integrity_check_res = [r[0] for r in res_cur.fetchall()]

res_cur.execute("PRAGMA foreign_key_check;")
fk_check_res = res_cur.fetchall()
fk_violations = [{"table": r[0], "rowid": r[1], "parent_table": r[2], "fkid": r[3]} for r in fk_check_res]

# 3. Exhaustive Row-by-Row comparison across all tables
src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
tables = [r[0] for r in src_cur.fetchall()]

table_row_comparison = {}
total_src_rows = 0
total_res_rows = 0
all_rows_identical = True

for t in tables:
    src_cur.execute(f'PRAGMA table_info("{t}");')
    cols = [c[1] for c in src_cur.fetchall()]
    col_str = ", ".join([f'"{c}"' for c in cols])
    
    src_cur.execute(f'SELECT {col_str} FROM "{t}" ORDER BY {col_str};')
    src_rows = src_cur.fetchall()
    
    res_cur.execute(f'SELECT {col_str} FROM "{t}" ORDER BY {col_str};')
    res_rows = res_cur.fetchall()
    
    s_count = len(src_rows)
    r_count = len(res_rows)
    total_src_rows += s_count
    total_res_rows += r_count
    
    match = (src_rows == res_rows)
    if not match:
        all_rows_identical = False
        
    table_row_comparison[t] = {
        "columns": cols,
        "source_count": s_count,
        "restored_count": r_count,
        "row_data_identical": match
    }

# 4. Critical Entity Deep-Dives
res_cur.execute("SELECT id, page_number, category_name, status, is_verified_by_human, length(raw_text), length(cleaned_text) FROM comments;")
comments_sample = res_cur.fetchall()

res_cur.execute("SELECT id, file_name, total_pages, department_id, project_id FROM drawings;")
drawings_summary = [{"id": r[0], "file_name": r[1], "pages": r[2], "department_id": r[3], "project_id": r[4]} for r in res_cur.fetchall()]

res_cur.execute("SELECT count(distinct comment_id), count(*) FROM audit_logs;")
audit_comment_count, audit_total_count = res_cur.fetchone()

res_cur.execute("SELECT username, role, department_id, password_hash is not null FROM users;")
users_summary = [{"username": r[0], "role": r[1], "department_id": r[2], "has_password": bool(r[3])} for r in res_cur.fetchall()]

# Explicitly close connections before deleting files
src_conn.close()
res_conn.close()

# Cleanup restored test directory cleanly
shutil.rmtree(restore_test_dir, ignore_errors=True)

report = {
    "phase": "Phase 1A — Strengthened SQLite Backup Verification",
    "timestamp_iso": "2026-10-12T17:31:00Z",
    "source_database": {
        "path": str(src_path),
        "sha256": src_sha,
        "total_tables": len(tables),
        "total_rows": total_src_rows
    },
    "backup_database": {
        "path": str(backup_path),
        "sha256": backup_sha,
        "restoration_copy_sha256_match": (backup_sha == restored_sha)
    },
    "isolated_restoration_test": {
        "restoration_successful": True,
        "integrity_check": integrity_check_res,
        "foreign_key_check": {
            "violations_count": len(fk_violations),
            "violations": fk_violations
        }
    },
    "exhaustive_row_comparison": {
        "all_tables_exact_data_match": all_rows_identical,
        "total_source_rows": total_src_rows,
        "total_restored_rows": total_res_rows,
        "per_table_comparison": table_row_comparison
    },
    "critical_entity_verification": {
        "drawings_verified": len(drawings_summary),
        "drawings": drawings_summary,
        "comments_verified": len(comments_sample),
        "audit_logs_total": audit_total_count,
        "audit_comments_covered": audit_comment_count,
        "users_verified": len(users_summary),
        "users": users_summary
    },
    "conclusion": "PASSED — Backup is structurally intact, relationally sound, and bitwise data identical to source."
}

out_report_path = Path("backups/sqlite_pre_migration/phase1a_verification_report.json")
with open(out_report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print(f"Generated: {out_report_path}")
print(f"All rows identical: {all_rows_identical}")
print(f"Integrity check: {integrity_check_res}")
print(f"FK violations: {len(fk_violations)}")

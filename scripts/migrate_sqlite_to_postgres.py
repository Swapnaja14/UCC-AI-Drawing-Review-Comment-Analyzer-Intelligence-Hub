#!/usr/bin/env python3
"""
scripts/migrate_sqlite_to_postgres.py
Data migration tool: Migrates UCC SQLite database to PostgreSQL.

Features:
- Dry-run mode by default (reports statistics without modifying target)
- --execute flag required to write data
- Source SQLite opened in read-only mode (never modified)
- Copies tables in strict foreign-key dependency order
- Type coercion: booleans (0/1 -> bool), datetimes (naive -> UTC-aware), varchar bounds
- Orphan row detection & quarantining to migration_quarantine.json
- Batch INSERT with ON CONFLICT (id) DO UPDATE (upsert)
- Detailed verification report: per-table row counts, status/category counts,
  confidence sums, and timestamp boundaries.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import create_engine, inspect, text, Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.infrastructure.storage.models import (
    Base,
    EngineeringDepartmentModel,
    CategoryModel,
    UserModel,
    ProjectModel,
    DrawingModel,
    PageModel,
    CommentModel,
    AuditLogModel,
    ProcessingRunModel,
    ExportLogModel,
)

# ---------------------------------------------------------------------------
# Strict FK Dependency Order
# ---------------------------------------------------------------------------
TABLE_MIGRATION_ORDER = [
    ("engineering_departments", EngineeringDepartmentModel),
    ("categories", CategoryModel),
    ("users", UserModel),
    ("projects", ProjectModel),
    ("drawings", DrawingModel),
    ("pages", PageModel),
    ("comments", CommentModel),
    ("audit_logs", AuditLogModel),
    ("processing_runs", ProcessingRunModel),
    ("export_history", ExportLogModel),
]

# FK definitions for orphan checking: (table_name, fk_column, parent_table, is_nullable)
FK_DEFINITIONS = [
    ("users", "department_id", "engineering_departments", True),
    ("drawings", "project_id", "projects", True),
    ("drawings", "department_id", "engineering_departments", True),
    ("pages", "drawing_id", "drawings", False),
    ("comments", "drawing_id", "drawings", False),
    ("comments", "page_id", "pages", True),
    ("comments", "category_id", "categories", True),
    ("comments", "department_id", "engineering_departments", True),
    ("comments", "user_id", "users", True),
    ("audit_logs", "comment_id", "comments", False),
    ("audit_logs", "user_id", "users", True),
    ("processing_runs", "project_id", "projects", True),
    ("processing_runs", "drawing_id", "drawings", True),
    ("export_history", "drawing_id", "drawings", True),
    ("export_history", "project_id", "projects", True),
]


def coerce_datetime(value: Any) -> Optional[datetime]:
    """Convert any naive/aware string or datetime to UTC timezone-aware datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        # Clean common string formats
        val_clean = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(val_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(val_clean, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pass
    return None


def coerce_boolean(value: Any) -> Optional[bool]:
    """Convert SQLite 0/1 or string representations to boolean."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        val_lower = value.strip().lower()
        if val_lower in ("1", "true", "t", "yes", "y"):
            return True
        if val_lower in ("0", "false", "f", "no", "n"):
            return False
    return bool(value)


def coerce_row(table_model: Any, row: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce row types to match SQLAlchemy model definitions."""
    coerced: Dict[str, Any] = {}
    table = table_model.__table__

    for col in table.columns:
        col_name = col.name
        if col_name not in row:
            continue
        val = row[col_name]
        if val is None:
            coerced[col_name] = None
            continue

        type_str = str(col.type).upper()
        if "BOOLEAN" in type_str:
            coerced[col_name] = coerce_boolean(val)
        elif "DATETIME" in type_str or "TIMESTAMP" in type_str:
            coerced[col_name] = coerce_datetime(val)
        elif "INTEGER" in type_str or "BIGINT" in type_str:
            try:
                coerced[col_name] = int(val)
            except Exception:
                coerced[col_name] = None
        elif "FLOAT" in type_str or "REAL" in type_str or "PRECISION" in type_str:
            try:
                coerced[col_name] = float(val)
            except Exception:
                coerced[col_name] = None
        elif "VARCHAR" in type_str or "STRING" in type_str:
            s_val = str(val)
            if hasattr(col.type, "length") and col.type.length and len(s_val) > col.type.length:
                s_val = s_val[:col.type.length]
            coerced[col_name] = s_val
        else:
            coerced[col_name] = val

    return coerced


class SQLiteToPostgresMigrator:
    """Orchestrates SQLite to PostgreSQL data migration with validation and quarantine."""

    def __init__(
        self,
        source_path: Path,
        target_url: str,
        execute: bool = False,
        batch_size: int = 500,
        quarantine_path: Path = Path("migration_quarantine.json"),
    ) -> None:
        self.source_path = source_path
        self.target_url = target_url
        self.execute = execute
        self.batch_size = batch_size
        self.quarantine_path = quarantine_path

        self.quarantined_rows: List[Dict[str, Any]] = []
        self.migrated_pks: Dict[str, Set[str]] = {t[0]: set() for t in TABLE_MIGRATION_ORDER}
        self.stats: Dict[str, Dict[str, Any]] = {}

    def _open_sqlite_ro(self) -> sqlite3.Connection:
        """Open source SQLite database in strict READ-ONLY mode."""
        uri_path = self.source_path.resolve().as_posix()
        conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def run(self) -> Dict[str, Any]:
        """Execute migration or dry-run and return execution summary."""
        print("=" * 70)
        mode_str = "LIVE EXECUTION (--execute)" if self.execute else "DRY RUN (Reporting only)"
        print(f"UCC SQLite -> PostgreSQL Migration Engine [{mode_str}]")
        print(f"Source SQLite: {self.source_path}")
        print(f"Target DB:     {self._mask_url(self.target_url)}")
        print("=" * 70)

        # 1. Connect to SQLite read-only
        sqlite_conn = self._open_sqlite_ro()

        # 2. Connect to target engine if executing
        target_engine = None
        if self.execute:
            target_engine = create_engine(self.target_url)
            # Ensure schema exists on target
            Base.metadata.create_all(bind=target_engine)

        # 3. Process tables in FK order
        for table_name, model_cls in TABLE_MIGRATION_ORDER:
            self._process_table(sqlite_conn, target_engine, table_name, model_cls)

        sqlite_conn.close()

        # 4. Save quarantine file
        with open(self.quarantine_path, "w", encoding="utf-8") as f:
            json.dump(self.quarantined_rows, f, indent=2, default=str)
        print(f"\nQuarantine report saved to: {self.quarantine_path.resolve()} ({len(self.quarantined_rows)} items)")

        # 5. Verification summary
        self._print_verification_report()

        return {
            "mode": "execute" if self.execute else "dry_run",
            "stats": self.stats,
            "quarantined_count": len(self.quarantined_rows),
        }

    def _mask_url(self, url: str) -> str:
        """Mask credentials in connection string for safe display."""
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)

    def _process_table(
        self,
        sqlite_conn: sqlite3.Connection,
        target_engine: Any,
        table_name: str,
        model_cls: Any,
    ) -> None:
        cur = sqlite_conn.cursor()

        # Check if table exists in source
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cur.fetchone():
            self.stats[table_name] = {"source_rows": 0, "migrated": 0, "quarantined": 0}
            print(f"  [-] Table '{table_name}' does not exist in source. Skipped.")
            return

        cur.execute(f"SELECT * FROM {table_name}")
        raw_rows = [dict(r) for r in cur.fetchall()]
        source_count = len(raw_rows)

        valid_rows: List[Dict[str, Any]] = []
        table_fk_rules = [fk for fk in FK_DEFINITIONS if fk[0] == table_name]

        for raw_row in raw_rows:
            row_id = str(raw_row.get("id", ""))
            coerced = coerce_row(model_cls, raw_row)

            # Validate Foreign Keys
            is_valid = True
            for _, fk_col, parent_table, is_nullable in table_fk_rules:
                parent_val = coerced.get(fk_col)
                if parent_val is not None:
                    parent_val_str = str(parent_val)
                    if parent_val_str not in self.migrated_pks[parent_table]:
                        if not is_nullable:
                            # Strict FK violation -> Quarantine
                            self.quarantined_rows.append({
                                "table": table_name,
                                "id": row_id,
                                "fk_column": fk_col,
                                "parent_table": parent_table,
                                "missing_parent_id": parent_val_str,
                                "reason": f"Required foreign key {fk_col}={parent_val_str} not found in {parent_table}",
                                "data": raw_row,
                            })
                            is_valid = False
                            break
                        else:
                            # Nullable FK violation -> Nullify & warn
                            coerced[fk_col] = None

            if is_valid:
                valid_rows.append(coerced)
                if row_id:
                    self.migrated_pks[table_name].add(row_id)

        quarantined_count = source_count - len(valid_rows)

        # Write to target if execute=True
        written_count = 0
        if self.execute and valid_rows and target_engine is not None:
            written_count = self._batch_upsert(target_engine, model_cls, valid_rows)
        else:
            written_count = len(valid_rows)

        self.stats[table_name] = {
            "source_rows": source_count,
            "migrated": written_count,
            "quarantined": quarantined_count,
        }

        status_marker = "DONE" if quarantined_count == 0 else f"QUARANTINED {quarantined_count}"
        print(f"  [+] {table_name:<26} Source: {source_count:<5} Valid: {len(valid_rows):<5} -> {status_marker}")

    def _batch_upsert(self, target_engine: Any, model_cls: Any, rows: List[Dict[str, Any]]) -> int:
        """Perform batch upsert using dialect-appropriate ON CONFLICT clause."""
        table: Table = model_cls.__table__
        dialect_name = target_engine.dialect.name
        total_upserted = 0

        for i in range(0, len(rows), self.batch_size):
            batch = rows[i : i + self.batch_size]
            with target_engine.begin() as conn:
                if dialect_name == "postgresql":
                    stmt = pg_insert(table).values(batch)
                    pk_cols = [c.name for c in table.primary_key.columns]
                    update_dict = {c.name: stmt.excluded[c.name] for c in table.columns if not c.primary_key}
                    stmt = stmt.on_conflict_do_update(
                        index_elements=pk_cols,
                        set_=update_dict,
                    )
                    conn.execute(stmt)
                elif dialect_name == "sqlite":
                    stmt = sqlite_insert(table).values(batch)
                    pk_cols = [c.name for c in table.primary_key.columns]
                    update_dict = {c.name: stmt.excluded[c.name] for c in table.columns if not c.primary_key}
                    stmt = stmt.on_conflict_do_update(
                        index_elements=pk_cols,
                        set_=update_dict,
                    )
                    conn.execute(stmt)
                else:
                    conn.execute(table.insert(), batch)
            total_upserted += len(batch)

        return total_upserted

    def _print_verification_report(self) -> None:
        """Print audit and verification metrics."""
        print("\n" + "=" * 70)
        print("VERIFICATION & RECONCILIATION REPORT")
        print("=" * 70)
        print(f"{'Table':<28} {'Source':<10} {'Migrated':<10} {'Quarantined':<12}")
        print("-" * 70)
        total_source = 0
        total_migrated = 0
        total_quarantined = 0

        for t_name, _ in TABLE_MIGRATION_ORDER:
            t_stat = self.stats.get(t_name, {"source_rows": 0, "migrated": 0, "quarantined": 0})
            print(f"{t_name:<28} {t_stat['source_rows']:<10} {t_stat['migrated']:<10} {t_stat['quarantined']:<12}")
            total_source += t_stat["source_rows"]
            total_migrated += t_stat["migrated"]
            total_quarantined += t_stat["quarantined"]

        print("-" * 70)
        print(f"{'TOTALS':<28} {total_source:<10} {total_migrated:<10} {total_quarantined:<12}")

        # SQLite Comments Metrics Verification
        sqlite_conn = self._open_sqlite_ro()
        cur = sqlite_conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='comments'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(comments)")
            cols = {row["name"] for row in cur.fetchall()}

            print("\nComments Metric Reconciliation (Source):")
            if "status" in cols:
                cur.execute("SELECT status, count(*) FROM comments GROUP BY status")
                for st, cnt in cur.fetchall():
                    print(f"  - Status [{st}]: {cnt}")
            if "category_name" in cols:
                cur.execute("SELECT coalesce(category_name, 'Uncategorized'), count(*) FROM comments GROUP BY 1")
                for cat, cnt in cur.fetchall():
                    print(f"  - Category [{cat}]: {cnt}")
            if "confidence" in cols and "created_at" in cols:
                cur.execute("SELECT sum(confidence), min(created_at), max(created_at) FROM comments")
                row = cur.fetchone()
                sum_conf = row[0] or 0.0
                min_dt = row[1]
                max_dt = row[2]
                print(f"  - SUM(confidence): {sum_conf:.4f}")
                print(f"  - Timestamp span: {min_dt}  -->  {max_dt}")

        sqlite_conn.close()
        print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate UCC SQLite database to PostgreSQL with dry-run support.")
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Path to source SQLite file (default: working copy if present, else data/ucc_database.db)",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target database URL (default: UCC_DATABASE_URL or config.yaml)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the migration and write data to target (default: dry run)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for inserts (default: 500)",
    )
    parser.add_argument(
        "--quarantine-file",
        type=Path,
        default=Path("migration_quarantine.json"),
        help="File to output quarantined orphan rows (default: migration_quarantine.json)",
    )

    args = parser.parse_args()

    # Determine source path
    source_path = args.source
    if not source_path:
        working_copy = _PROJECT_ROOT / "data" / "ucc_database_working_copy.db"
        prod_copy = _PROJECT_ROOT / "data" / "ucc_database.db"
        source_path = working_copy if working_copy.exists() else prod_copy

    if not source_path.exists():
        print(f"Error: Source database file not found at: {source_path}", file=sys.stderr)
        sys.exit(1)

    # Determine target URL
    target_url = args.target
    if not target_url:
        target_url = os.environ.get("UCC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not target_url and args.execute:
        print("Error: Target database URL must be provided via --target or UCC_DATABASE_URL to --execute.", file=sys.stderr)
        sys.exit(1)
    if not target_url:
        target_url = "postgresql+psycopg://user:password@localhost:5432/ucc_database"

    migrator = SQLiteToPostgresMigrator(
        source_path=source_path,
        target_url=target_url,
        execute=args.execute,
        batch_size=args.batch_size,
        quarantine_path=args.quarantine_file,
    )
    migrator.run()


if __name__ == "__main__":
    main()

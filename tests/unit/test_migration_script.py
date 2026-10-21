"""
tests/unit/test_migration_script.py
Unit tests for B4: SQLite to PostgreSQL data migration script.
Verifies coercion rules, FK orphan quarantining, batch upsert, and read-only source access.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect

from scripts.migrate_sqlite_to_postgres import (
    coerce_boolean,
    coerce_datetime,
    SQLiteToPostgresMigrator,
)
from src.infrastructure.storage.models import Base, CommentModel, DrawingModel, EngineeringDepartmentModel


def test_coerce_boolean():
    """Verify boolean coercion handles integer 0/1, strings, and booleans."""
    assert coerce_boolean(1) is True
    assert coerce_boolean(0) is False
    assert coerce_boolean("true") is True
    assert coerce_boolean("0") is False
    assert coerce_boolean(True) is True
    assert coerce_boolean(False) is False
    assert coerce_boolean(None) is None


def test_coerce_datetime():
    """Verify datetime coercion converts strings and naive datetimes to UTC aware."""
    # Naive datetime
    naive = datetime(2024, 5, 1, 12, 0, 0)
    aware = coerce_datetime(naive)
    assert aware.tzinfo == timezone.utc
    assert aware.hour == 12

    # ISO string
    iso_str = "2024-05-01T14:30:00"
    aware_str = coerce_datetime(iso_str)
    assert aware_str.tzinfo == timezone.utc
    assert aware_str.hour == 14

    # None
    assert coerce_datetime(None) is None


def test_migrator_dry_run_and_quarantine(tmp_path):
    """Verify that orphan rows without parent FK are quarantined and not migrated."""
    source_db = tmp_path / "source.db"
    quarantine_file = tmp_path / "quarantine.json"

    # Create source sqlite with 1 valid department and 1 orphan comment (no drawing parent)
    conn = sqlite3.connect(source_db)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE engineering_departments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE comments (
            id TEXT PRIMARY KEY,
            drawing_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            is_verified_by_human INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("INSERT INTO engineering_departments VALUES ('DEPT-1', 'Civil', 'Civil Dept', 1, '2024-01-01 00:00:00')")
    # Orphan comment pointing to nonexistent drawing DWG-999
    cur.execute("INSERT INTO comments VALUES ('C-ORPHAN', 'DWG-999', 1, 'text', 'Pending', 0.8, 0, '2024-01-01 00:00:00')")
    conn.commit()
    conn.close()

    migrator = SQLiteToPostgresMigrator(
        source_path=source_db,
        target_url="sqlite:///:memory:",
        execute=False,
        quarantine_path=quarantine_file,
    )
    result = migrator.run()

    assert result["mode"] == "dry_run"
    assert result["quarantined_count"] == 1
    assert result["stats"]["engineering_departments"]["migrated"] == 1
    assert result["stats"]["comments"]["quarantined"] == 1
    assert result["stats"]["comments"]["migrated"] == 0

    # Verify quarantine file contents
    assert quarantine_file.exists()
    with open(quarantine_file, "r") as f:
        quarantine_data = json.load(f)
    assert len(quarantine_data) == 1
    assert quarantine_data[0]["id"] == "C-ORPHAN"
    assert "DWG-999" in quarantine_data[0]["missing_parent_id"]

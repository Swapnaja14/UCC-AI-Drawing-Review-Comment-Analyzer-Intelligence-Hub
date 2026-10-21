"""
tests/unit/test_alembic_and_timestamps.py
Tests for B2: Alembic baseline migration and timezone-aware timestamp handling.
"""
import os
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect

from src.infrastructure.storage.models import (
    Base,
    CommentModel,
    UserModel,
    DrawingModel,
    PageModel,
    ProjectModel,
    CategoryModel,
    EngineeringDepartmentModel,
    AuditLogModel,
    ExportLogModel,
    ProcessingRunModel,
    utc_now,
)


def test_utc_now_returns_timezone_aware():
    """Verify that utc_now() returns timezone-aware UTC datetime."""
    now = utc_now()
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc


def test_models_datetime_columns_have_timezone_true():
    """Verify all DateTime columns in ORM models have timezone=True."""
    models_to_check = [
        UserModel,
        EngineeringDepartmentModel,
        CategoryModel,
        ProjectModel,
        DrawingModel,
        PageModel,
        CommentModel,
        AuditLogModel,
        ExportLogModel,
        ProcessingRunModel,
    ]
    for model in models_to_check:
        for col in model.__table__.columns:
            if hasattr(col.type, "timezone"):
                assert col.type.timezone is True, f"{model.__name__}.{col.name} missing timezone=True"


def test_alembic_upgrade_on_sqlite(tmp_path):
    """Verify that Alembic can execute the baseline migration on a fresh SQLite database."""
    from alembic.config import Config
    from alembic import command

    db_file = tmp_path / "alembic_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade head
    command.upgrade(alembic_cfg, "head")

    # Verify tables were created
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected_tables = {
        "categories",
        "engineering_departments",
        "projects",
        "drawings",
        "pages",
        "comments",
        "users",
        "audit_logs",
        "export_history",
        "processing_runs",
        "alembic_version",
    }
    assert expected_tables.issubset(set(tables))

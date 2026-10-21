"""
Unit tests for B1: Config and DatabaseEngine dual-backend support (SQLite and PostgreSQL).
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy import text
from src.config.app_config import DatabaseConfig
from src.infrastructure.storage.repository import DatabaseEngine


def test_database_config_defaults():
    cfg = DatabaseConfig()
    assert cfg.backend == "sqlite"
    assert cfg.url is None
    assert "ucc_database.db" in cfg.get_url()
    assert cfg.get_backend() == "sqlite"


def test_database_config_env_override(monkeypatch):
    monkeypatch.setenv("UCC_DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
    cfg = DatabaseConfig()
    assert cfg.get_url() == "postgresql+psycopg://user:pass@localhost:5432/test_db"
    assert cfg.get_backend() == "postgresql"


def test_database_engine_sqlite_behavior(tmp_path):
    db_file = tmp_path / "sqlite_test.db"
    db_engine = DatabaseEngine(db_path=db_file)
    assert db_engine.backend == "sqlite"
    assert db_engine.engine.dialect.name == "sqlite"
    with db_engine.get_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_database_engine_postgres_missing_url_raises():
    with pytest.raises(ValueError, match="PostgreSQL backend selected but no database URL provided"):
        DatabaseEngine(backend="postgresql")


def test_database_engine_postgres_pooled_config(monkeypatch):
    # Mock create_engine to verify pool arguments without connecting to live network
    with patch("src.infrastructure.storage.repository.create_engine") as mock_create_engine, \
         patch.object(DatabaseEngine, "_init_db"):
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        pg_url = "postgresql+psycopg://ucc_user:secret@localhost:5432/ucc_db"
        engine = DatabaseEngine(url=pg_url, pool_size=10, max_overflow=20)

        assert engine.backend == "postgresql"
        mock_create_engine.assert_called_once()
        _, kwargs = mock_create_engine.call_args
        assert kwargs["pool_size"] == 10
        assert kwargs["max_overflow"] == 20
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_recycle"] == 1800

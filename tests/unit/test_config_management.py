"""
tests/unit/test_config_management.py
Unit tests for Centralized Configuration Management System.
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest

from src.config.app_config import (
    AppConfig,
    DatabaseConfig,
    LoggingConfig,
    PDFConfig,
    OCRConfig,
    AIConfig,
    UIConfig,
    ExportConfig,
)
from src.config import (
    get_config,
    reload_config,
    save_config,
    set_config,
)


def test_default_config_instantiation():
    """Verify default configuration objects contain expected fields and default values."""
    config = AppConfig()
    
    assert config.app_name == "UCC AI Drawing Review Comment Analyzer"
    assert config.version == "1.0.0"
    assert config.environment == "development"
    
    # Database Config
    assert isinstance(config.database, DatabaseConfig)
    assert config.database.db_path == "data/ucc_database.db"
    assert config.database.wal_mode is True
    assert config.database.timeout_seconds == 30.0
    
    # Logging Config
    assert isinstance(config.logging, LoggingConfig)
    assert config.logging.log_level == "INFO"
    assert config.logging.log_to_console is True
    assert config.logging.log_to_file is True
    assert config.logging.log_file_path == "data/logs/ucc_app.log"
    
    # PDF Config
    assert isinstance(config.pdf, PDFConfig)
    assert config.pdf.display_dpi == 150
    assert config.pdf.ocr_dpi == 300
    assert config.pdf.max_file_size_mb == 500
    assert ".pdf" in config.pdf.allowed_extensions
    
    # OCR Config
    assert isinstance(config.ocr, OCRConfig)
    assert config.ocr.engine == "auto"
    assert config.ocr.confidence_threshold == 0.50
    
    # AI Config
    assert isinstance(config.ai, AIConfig)
    assert config.ai.classifier_type == "hybrid_nlp"
    assert config.ai.confidence_threshold == 0.70
    assert config.ai.auto_approve_high_confidence is True
    assert config.ai.auto_approve_threshold == 0.85
    
    # UI Config
    assert isinstance(config.ui, UIConfig)
    assert config.ui.theme == "dark"
    assert config.ui.language == "English (US)"
    assert config.ui.rows_per_page == 25
    assert config.ui.auto_save is True
    assert config.ui.enable_notifications is True
    
    # Export Config
    assert isinstance(config.export, ExportConfig)
    assert config.export.default_format == "Excel"
    assert config.export.include_summary_sheet is True


def test_config_to_dict_and_from_dict():
    """Verify dictionary serialization and deserialization."""
    config = AppConfig()
    config.ui.theme = "light"
    config.logging.log_level = "DEBUG"
    config.ocr.engine = "trocr"
    
    data = config.to_dict()
    assert isinstance(data, dict)
    assert data["ui"]["theme"] == "light"
    assert data["logging"]["log_level"] == "DEBUG"
    assert data["ocr"]["engine"] == "trocr"
    assert data["app_name"] == config.app_name
    
    restored = AppConfig.from_dict(data)
    assert restored.ui.theme == "light"
    assert restored.logging.log_level == "DEBUG"
    assert restored.ocr.engine == "trocr"
    assert restored.database.wal_mode is True


def test_yaml_save_and_load(tmp_path: Path):
    """Verify YAML persistence roundtrip."""
    yaml_file = tmp_path / "test_config.yaml"
    
    cfg = AppConfig()
    cfg.app_name = "Custom UCC Suite"
    cfg.pdf.display_dpi = 200
    cfg.ui.rows_per_page = 50
    
    saved_path = cfg.save_to_yaml(yaml_file)
    assert saved_path.exists()
    
    loaded = AppConfig.load_from_yaml(yaml_file)
    assert loaded.app_name == "Custom UCC Suite"
    assert loaded.pdf.display_dpi == 200
    assert loaded.ui.rows_per_page == 50
    assert loaded.database.db_path == "data/ucc_database.db"


def test_json_save_and_load(tmp_path: Path):
    """Verify JSON persistence roundtrip."""
    json_file = tmp_path / "test_config.json"
    
    cfg = AppConfig()
    cfg.environment = "production"
    cfg.ai.confidence_threshold = 0.85
    
    saved_path = cfg.save_to_json(json_file)
    assert saved_path.exists()
    
    loaded = AppConfig.load_from_json(json_file)
    assert loaded.environment == "production"
    assert loaded.ai.confidence_threshold == 0.85


def test_environment_variable_overrides(monkeypatch: pytest.MonkeyPatch):
    """Verify environment variable overrides with UCC_ prefix."""
    monkeypatch.setenv("UCC_ENV", "staging")
    monkeypatch.setenv("UCC_DATABASE_DB_PATH", "custom/test.db")
    monkeypatch.setenv("UCC_DATABASE_WAL_MODE", "false")
    monkeypatch.setenv("UCC_LOGGING_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("UCC_PDF_DISPLAY_DPI", "250")
    monkeypatch.setenv("UCC_OCR_CONFIDENCE_THRESHOLD", "0.65")
    monkeypatch.setenv("UCC_UI_THEME", "light")
    monkeypatch.setenv("UCC_UI_AUTO_SAVE", "0")
    monkeypatch.setenv("UCC_EXPORT_DEFAULT_FORMAT", "JSON")
    
    cfg = AppConfig()
    cfg.apply_env_overrides()
    
    assert cfg.environment == "staging"
    assert cfg.database.db_path == "custom/test.db"
    assert cfg.database.wal_mode is False
    assert cfg.logging.log_level == "WARNING"
    assert cfg.pdf.display_dpi == 250
    assert cfg.ocr.confidence_threshold == 0.65
    assert cfg.ui.theme == "light"
    assert cfg.ui.auto_save is False
    assert cfg.export.default_format == "JSON"


def test_malformed_env_variable_handling(monkeypatch: pytest.MonkeyPatch):
    """Verify malformed environment variable does not crash configuration loader."""
    monkeypatch.setenv("UCC_PDF_DISPLAY_DPI", "not_a_valid_number")
    
    cfg = AppConfig()
    # Should not raise exception
    cfg.apply_env_overrides()
    assert cfg.pdf.display_dpi == 150  # preserved default


def test_path_resolution(tmp_path: Path):
    """Verify path resolution helpers for relative and absolute paths."""
    cfg = AppConfig()
    
    # Test DB path resolution
    resolved_db = cfg.database.get_resolved_db_path(root=tmp_path)
    assert resolved_db == (tmp_path / "data" / "ucc_database.db").resolve()
    
    # Test Log file resolution and parent directory creation
    resolved_log = cfg.logging.get_resolved_log_file(root=tmp_path)
    assert resolved_log.parent.exists()
    assert resolved_log == (tmp_path / "data" / "logs" / "ucc_app.log").resolve()
    
    # Test Projects dir resolution
    resolved_proj = cfg.ui.get_resolved_projects_dir(root=tmp_path)
    assert resolved_proj == (tmp_path / "dataset" / "raw_drawings").resolve()
    
    # Test Export dir resolution and directory creation
    resolved_exp = cfg.export.get_resolved_export_dir(root=tmp_path)
    assert resolved_exp.exists()
    assert resolved_exp == (tmp_path / "exports").resolve()


def test_missing_config_fallback(tmp_path: Path):
    """Verify that loading from a missing file safely returns default configuration."""
    missing_yaml = tmp_path / "does_not_exist.yaml"
    cfg = AppConfig.load_from_yaml(missing_yaml)
    assert cfg.app_name == "UCC AI Drawing Review Comment Analyzer"
    assert cfg.ui.theme == "dark"


def test_singleton_lifecycle(tmp_path: Path):
    """Verify get_config, set_config, save_config, and reload_config operations."""
    custom_cfg = AppConfig(app_name="Singleton Suite")
    set_config(custom_cfg)
    
    active = get_config()
    assert active.app_name == "Singleton Suite"
    
    target_yaml = tmp_path / "singleton_test.yaml"
    custom_cfg.ui.rows_per_page = 100
    save_config(custom_cfg, config_path=target_yaml)
    
    reloaded = reload_config(config_path=target_yaml)
    assert reloaded.ui.rows_per_page == 100

"""
src/config/app_config.py
Centralized Configuration Management System for UCC AI Drawing Review Comment Analyzer.

Provides typed configuration models, YAML/JSON persistence, environment variable
overrides, and application-wide singleton access.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

# Resolve project root directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


@dataclass
class DatabaseConfig:
    """Configuration for SQLite storage engine and SQLAlchemy ORM."""
    db_path: str = "data/ucc_database.db"
    wal_mode: bool = True
    echo_sql: bool = False
    timeout_seconds: float = 30.0
    pool_size: int = 5

    def get_resolved_db_path(self, root: Optional[Path] = None) -> Path:
        base = root or PROJECT_ROOT
        path = Path(self.db_path)
        return path if path.is_absolute() else (base / path).resolve()


@dataclass
class LoggingConfig:
    """Configuration for centralized application logging."""
    log_level: str = "INFO"
    log_to_console: bool = True
    log_to_file: bool = True
    log_file_path: str = "data/logs/ucc_app.log"
    max_bytes: int = 10 * 1024 * 1024  # 10 MB
    backup_count: int = 5
    log_format: str = "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"

    def get_resolved_log_file(self, root: Optional[Path] = None) -> Path:
        base = root or PROJECT_ROOT
        path = Path(self.log_file_path)
        resolved = path if path.is_absolute() else (base / path).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved


@dataclass
class PDFConfig:
    """Configuration for PDF parsing, rendering DPIs, and document validation."""
    display_dpi: int = 150
    ocr_dpi: int = 300
    thumbnail_dpi: int = 30
    max_file_size_mb: int = 500
    allowed_extensions: List[str] = field(default_factory=lambda: [".pdf"])


@dataclass
class OCRConfig:
    """Configuration for OCR extraction, annotation detection, and processing engines."""
    engine: str = "auto"  # "auto", "tesseract", "trocr", "hybrid"
    tesseract_psm: int = 6
    fallback_psm: int = 11
    confidence_threshold: float = 0.50
    annotation_method: str = "hybrid"  # "hybrid", "color", "native"
    filter_template_regions: bool = False


@dataclass
class AIConfig:
    """Configuration for AI comment classification and NLP models."""
    classifier_type: str = "hybrid_nlp"  # "hybrid_nlp", "distilbert", "rule_fallback"
    model_path: str = "models/distilbert_classifier"
    confidence_threshold: float = 0.70
    fallback_to_rules: bool = True
    auto_approve_high_confidence: bool = True
    auto_approve_threshold: float = 0.85


@dataclass
class UIConfig:
    """Configuration for PySide6 Desktop GUI appearance and user preferences."""
    theme: str = "dark"  # "dark", "light"
    language: str = "English (US)"
    font_family: str = "Segoe UI Variable"
    font_size_scale: int = 1  # 0: Small, 1: Medium, 2: Large
    default_projects_dir: str = "dataset/raw_drawings"
    rows_per_page: int = 25
    auto_save: bool = True
    enable_notifications: bool = True
    window_maximized: bool = True

    def get_resolved_projects_dir(self, root: Optional[Path] = None) -> Path:
        base = root or PROJECT_ROOT
        path = Path(self.default_projects_dir)
        return path if path.is_absolute() else (base / path).resolve()


@dataclass
class ExportConfig:
    """Configuration for reporting and data export defaults."""
    default_format: str = "Excel"  # "Excel", "JSON", "CSV"
    include_summary_sheet: bool = True
    include_confidence_scores: bool = True
    default_export_dir: str = "exports"

    def get_resolved_export_dir(self, root: Optional[Path] = None) -> Path:
        base = root or PROJECT_ROOT
        path = Path(self.default_export_dir)
        resolved = path if path.is_absolute() else (base / path).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved


@dataclass
class AppConfig:
    """
    Root application configuration container.
    """
    app_name: str = "UCC AI Drawing Review Comment Analyzer"
    version: str = "1.0.0"
    environment: str = "development"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    pdf: PDFConfig = field(default_factory=PDFConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    export: ExportConfig = field(default_factory=ExportConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration hierarchy into a nested dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppConfig:
        """Create AppConfig from nested dictionary with safe defaults."""
        if not data:
            return cls()

        data = dict(data)
        db_data = data.pop("database", {})
        log_data = data.pop("logging", {})
        pdf_data = data.pop("pdf", {})
        ocr_data = data.pop("ocr", {})
        ai_data = data.pop("ai", {})
        ui_data = data.pop("ui", {})
        exp_data = data.pop("export", {})

        return cls(
            app_name=data.get("app_name", "UCC AI Drawing Review Comment Analyzer"),
            version=data.get("version", "1.0.0"),
            environment=data.get("environment", "development"),
            database=DatabaseConfig(**db_data) if isinstance(db_data, dict) else DatabaseConfig(),
            logging=LoggingConfig(**log_data) if isinstance(log_data, dict) else LoggingConfig(),
            pdf=PDFConfig(**pdf_data) if isinstance(pdf_data, dict) else PDFConfig(),
            ocr=OCRConfig(**ocr_data) if isinstance(ocr_data, dict) else OCRConfig(),
            ai=AIConfig(**ai_data) if isinstance(ai_data, dict) else AIConfig(),
            ui=UIConfig(**ui_data) if isinstance(ui_data, dict) else UIConfig(),
            export=ExportConfig(**exp_data) if isinstance(exp_data, dict) else ExportConfig(),
        )

    def apply_env_overrides(self) -> None:
        """
        Apply environment variable overrides with prefix 'UCC_'.
        Examples:
            UCC_DATABASE_DB_PATH -> database.db_path
            UCC_LOGGING_LOG_LEVEL -> logging.log_level
            UCC_UI_THEME -> ui.theme
            UCC_OCR_ENGINE -> ocr.engine
        """
        mapping = {
            "UCC_ENV": ("environment", str),
            "UCC_DATABASE_DB_PATH": ("database.db_path", str),
            "UCC_DATABASE_WAL_MODE": ("database.wal_mode", lambda v: v.lower() in ("1", "true", "yes")),
            "UCC_DATABASE_ECHO_SQL": ("database.echo_sql", lambda v: v.lower() in ("1", "true", "yes")),
            "UCC_LOGGING_LOG_LEVEL": ("logging.log_level", str),
            "UCC_LOGGING_LOG_TO_CONSOLE": ("logging.log_to_console", lambda v: v.lower() in ("1", "true", "yes")),
            "UCC_LOGGING_LOG_TO_FILE": ("logging.log_to_file", lambda v: v.lower() in ("1", "true", "yes")),
            "UCC_LOGGING_LOG_FILE_PATH": ("logging.log_file_path", str),
            "UCC_PDF_DISPLAY_DPI": ("pdf.display_dpi", int),
            "UCC_PDF_OCR_DPI": ("pdf.ocr_dpi", int),
            "UCC_OCR_ENGINE": ("ocr.engine", str),
            "UCC_OCR_CONFIDENCE_THRESHOLD": ("ocr.confidence_threshold", float),
            "UCC_AI_CLASSIFIER_TYPE": ("ai.classifier_type", str),
            "UCC_AI_MODEL_PATH": ("ai.model_path", str),
            "UCC_AI_AUTO_APPROVE": ("ai.auto_approve_high_confidence", lambda v: v.lower() in ("1", "true", "yes")),
            "UCC_AI_AUTO_APPROVE_THRESHOLD": ("ai.auto_approve_threshold", float),
            "UCC_UI_THEME": ("ui.theme", str),
            "UCC_UI_LANGUAGE": ("ui.language", str),
            "UCC_UI_DEFAULT_PROJECTS_DIR": ("ui.default_projects_dir", str),
            "UCC_UI_ROWS_PER_PAGE": ("ui.rows_per_page", int),
            "UCC_UI_AUTO_SAVE": ("ui.auto_save", lambda v: v.lower() in ("1", "true", "yes")),
            "UCC_UI_ENABLE_NOTIFICATIONS": ("ui.enable_notifications", lambda v: v.lower() in ("1", "true", "yes")),
            "UCC_EXPORT_DEFAULT_FORMAT": ("export.default_format", str),
        }

        for env_key, (path_attr, cast_fn) in mapping.items():
            val = os.environ.get(env_key)
            if val is not None:
                try:
                    typed_val = cast_fn(val)
                    parts = path_attr.split(".")
                    obj = self
                    for p in parts[:-1]:
                        obj = getattr(obj, p)
                    setattr(obj, parts[-1], typed_val)
                except Exception:
                    pass

    def save_to_yaml(self, file_path: Optional[Path | str] = None) -> Path:
        """Save configuration to a YAML file."""
        target = Path(file_path) if file_path else DEFAULT_CONFIG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return target

    def save_to_json(self, file_path: Optional[Path | str] = None) -> Path:
        """Save configuration to a JSON file."""
        target = Path(file_path) if file_path else (PROJECT_ROOT / "config" / "config.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return target

    @classmethod
    def load_from_yaml(cls, file_path: Path | str) -> AppConfig:
        """Load configuration from a YAML file with fallback to defaults."""
        path = Path(file_path)
        if not path.exists():
            config = cls()
            config.apply_env_overrides()
            return config

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = cls.from_dict(data)
        config.apply_env_overrides()
        return config

    @classmethod
    def load_from_json(cls, file_path: Path | str) -> AppConfig:
        """Load configuration from a JSON file with fallback to defaults."""
        path = Path(file_path)
        if not path.exists():
            config = cls()
            config.apply_env_overrides()
            return config

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}

        config = cls.from_dict(data)
        config.apply_env_overrides()
        return config

"""
settings_screen.py — Settings screen.

Provides:
    SettingsPage(QWidget)
        Multi-tab settings panel: Appearance / Application / AI & Processing / About.
        Uses a left-side tab list and a stacked content area on the right.
        Directly integrated with the centralized Configuration Management system.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame,
    QLabel, QListWidget, QListWidgetItem,
    QStackedWidget, QComboBox, QSlider,
    QCheckBox, QLineEdit, QToolButton,
    QPushButton, QFormLayout, QButtonGroup,
    QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from app.components.dialogs import open_folder
from src.config import get_config, save_config, reload_config, AppConfig, DEFAULT_CONFIG_PATH

_TABS = ["Appearance", "Application", "AI & Processing", "Categories", "About"]


# ── Segmented control ─────────────────────────────────────────────────────────

class _SegmentedControl(QWidget):
    """Horizontal group of mutually-exclusive toggle buttons."""

    def __init__(self, options: list[str], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for i, opt in enumerate(options):
            btn = QPushButton(opt)
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            if i == 0:
                radius_style = "border-radius: 8px 0 0 8px;"
            elif i == len(options) - 1:
                radius_style = "border-radius: 0 8px 8px 0;"
            else:
                radius_style = "border-radius: 0;"
            btn.setStyleSheet(
                f"QPushButton {{ background:#26272B; color:#A6A9B1;"
                f" border:1px solid #3A3C42; {radius_style}"
                f" padding:0 16px; font-size:13px; }}"
                f"QPushButton:checked {{ background:#3E9BFF;"
                f" color:#fff; border-color:#3E9BFF; }}"
            )
            self._group.addButton(btn, i)
            lay.addWidget(btn)
        if options:
            self._group.button(0).setChecked(True)

    @property
    def group(self) -> QButtonGroup:
        return self._group


# ── SettingsPage ──────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    """
    Settings — tabbed interface for Appearance, Application, AI & Processing, and About.
    Fully connected to Centralized Configuration Management (AppConfig).
    """

    def __init__(self, theme_manager=None, controller=None, parent=None):
        super().__init__(parent)
        self._theme = theme_manager
        self._controller = controller
        self._config: AppConfig = get_config()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tab list (left) ───────────────────────────────────────
        tab_list = QListWidget()
        tab_list.setObjectName("NavList")
        tab_list.setFixedWidth(220)
        tab_list.setStyleSheet(
            "#NavList { background: #26272B; border-right:1px solid #3A3C42; }"
            "#NavList::item { height:44px; padding-left:20px; border-radius:6px;"
            " margin:4px 8px; color:#A6A9B1; font-size:13px; }"
            "#NavList::item:selected { background:#3E9BFF2A;"
            " color:#3E9BFF; font-weight:600; }"
        )

        icons = ["🎨", "⚙", "🤖", "🏷", "ℹ"]
        for tab, icon in zip(_TABS, icons):
            item = QListWidgetItem(f"  {icon}   {tab}")
            item.setSizeHint(QSize(220, 44))
            tab_list.addItem(item)
        tab_list.setCurrentRow(0)

        # ── Content stack (right) ─────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_appearance())
        self._stack.addWidget(self._build_application())
        self._stack.addWidget(self._build_processing())
        self._stack.addWidget(self._build_categories())
        self._stack.addWidget(self._build_about())

        tab_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        root.addWidget(tab_list)
        root.addWidget(self._stack, 1)

    def _persist(self) -> None:
        """Helper to save active configuration to disk."""
        try:
            save_config(self._config)
        except Exception:
            pass

    # ── Tab pages ─────────────────────────────────────────────────

    def _build_appearance(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(28)
        lay.addWidget(self._section_title("Appearance"))

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        # Theme selector
        theme_ctrl = _SegmentedControl(["Light", "Dark", "System"])
        current_theme = self._config.ui.theme.lower()
        if current_theme == "light":
            theme_ctrl.group.button(0).setChecked(True)
        elif current_theme == "dark":
            theme_ctrl.group.button(1).setChecked(True)
        else:
            theme_ctrl.group.button(2).setChecked(True)

        def _on_theme(id_: int) -> None:
            theme_name = "light" if id_ == 0 else ("dark" if id_ == 1 else "system")
            self._config.ui.theme = theme_name
            self._persist()
            if self._theme and theme_name in ("light", "dark"):
                self._theme.apply(theme_name)

        theme_ctrl.group.idClicked.connect(_on_theme)
        form.addRow(self._form_label("Theme:"), theme_ctrl)

        # Language
        lang = QComboBox()
        lang_items = ["English (US)", "Hindi", "German", "French", "Spanish"]
        lang.addItems(lang_items)
        if self._config.ui.language in lang_items:
            lang.setCurrentText(self._config.ui.language)
        lang.setFixedHeight(36)
        lang.currentTextChanged.connect(self._on_language_changed)
        form.addRow(self._form_label("Language:"), lang)

        # Font size slider
        font_slider = QSlider(Qt.Orientation.Horizontal)
        font_slider.setRange(0, 2)
        font_slider.setValue(self._config.ui.font_size_scale)
        font_slider.setTickInterval(1)
        font_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        font_slider.setFixedWidth(200)
        font_slider.valueChanged.connect(self._on_font_scale_changed)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Small"))
        font_row.addWidget(font_slider)
        font_row.addWidget(QLabel("Large"))
        font_row.addStretch()
        form.addRow(self._form_label("Font Size:"), font_row)

        lay.addLayout(form)
        lay.addStretch()
        return page

    def _on_language_changed(self, text: str) -> None:
        self._config.ui.language = text
        self._persist()

    def _on_font_scale_changed(self, val: int) -> None:
        self._config.ui.font_size_scale = val
        self._persist()

    def _build_application(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(28)
        lay.addWidget(self._section_title("Application & Storage"))

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        # Default folder
        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit(self._config.ui.default_projects_dir)
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setFixedHeight(36)
        folder_row.addWidget(self._folder_edit, 1)
        browse = QToolButton()
        browse.setText("Browse…")
        browse.setFixedHeight(36)
        browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse)
        form.addRow(self._form_label("Default Folder:"), folder_row)

        # Database Path
        db_path_edit = QLineEdit(self._config.database.db_path)
        db_path_edit.setReadOnly(True)
        db_path_edit.setFixedHeight(36)
        db_path_edit.setToolTip(f"Resolved Path: {self._config.database.get_resolved_db_path()}")
        form.addRow(self._form_label("Database Path:"), db_path_edit)

        # Auto save
        auto_save = QCheckBox("Auto-save review progress and modifications")
        auto_save.setChecked(self._config.ui.auto_save)
        auto_save.toggled.connect(self._on_auto_save_toggled)
        form.addRow(self._form_label("Auto-Save:"), auto_save)

        # Notifications
        notif = QCheckBox("Enable desktop notifications for background processing")
        notif.setChecked(self._config.ui.enable_notifications)
        notif.toggled.connect(self._on_notif_toggled)
        form.addRow(self._form_label("Notifications:"), notif)

        # Page size
        page_size = QComboBox()
        page_size.addItems(["10", "25", "50", "100"])
        page_size.setCurrentText(str(self._config.ui.rows_per_page))
        page_size.setFixedHeight(36)
        page_size.setFixedWidth(120)
        page_size.currentTextChanged.connect(self._on_rows_per_page_changed)
        form.addRow(self._form_label("Rows per Page:"), page_size)

        # Log Level
        log_level_combo = QComboBox()
        log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        log_level_combo.setCurrentText(self._config.logging.log_level)
        log_level_combo.setFixedHeight(36)
        log_level_combo.setFixedWidth(120)
        log_level_combo.currentTextChanged.connect(self._on_log_level_changed)
        form.addRow(self._form_label("Log Level:"), log_level_combo)

        lay.addLayout(form)
        lay.addStretch()
        return page

    def _on_auto_save_toggled(self, checked: bool) -> None:
        self._config.ui.auto_save = checked
        self._persist()

    def _on_notif_toggled(self, checked: bool) -> None:
        self._config.ui.enable_notifications = checked
        self._persist()

    def _on_rows_per_page_changed(self, text: str) -> None:
        try:
            self._config.ui.rows_per_page = int(text)
            self._persist()
        except ValueError:
            pass

    def _on_log_level_changed(self, text: str) -> None:
        self._config.logging.log_level = text
        self._persist()

    def _build_processing(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(28)
        lay.addWidget(self._section_title("AI & Processing Engines"))

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        # OCR Engine
        ocr_combo = QComboBox()
        ocr_combo.addItems(["auto", "tesseract", "trocr", "hybrid"])
        ocr_combo.setCurrentText(self._config.ocr.engine)
        ocr_combo.setFixedHeight(36)
        ocr_combo.setFixedWidth(200)
        ocr_combo.currentTextChanged.connect(self._on_ocr_engine_changed)
        form.addRow(self._form_label("OCR Engine:"), ocr_combo)

        # PDF Display DPI
        dpi_combo = QComboBox()
        dpi_combo.addItems(["100", "150", "200", "300"])
        dpi_combo.setCurrentText(str(self._config.pdf.display_dpi))
        dpi_combo.setFixedHeight(36)
        dpi_combo.setFixedWidth(200)
        dpi_combo.currentTextChanged.connect(self._on_pdf_dpi_changed)
        form.addRow(self._form_label("PDF Display DPI:"), dpi_combo)

        # AI Classifier
        ai_combo = QComboBox()
        ai_combo.addItems(["hybrid_nlp", "distilbert", "rule_fallback"])
        ai_combo.setCurrentText(self._config.ai.classifier_type)
        ai_combo.setFixedHeight(36)
        ai_combo.setFixedWidth(200)
        ai_combo.currentTextChanged.connect(self._on_ai_classifier_changed)
        form.addRow(self._form_label("AI Classifier:"), ai_combo)

        # Default Export Format
        export_combo = QComboBox()
        export_combo.addItems(["Excel", "JSON", "CSV"])
        export_combo.setCurrentText(self._config.export.default_format)
        export_combo.setFixedHeight(36)
        export_combo.setFixedWidth(200)
        export_combo.currentTextChanged.connect(self._on_export_format_changed)
        form.addRow(self._form_label("Export Format:"), export_combo)

        lay.addLayout(form)
        lay.addStretch()
        return page

    def _on_ocr_engine_changed(self, text: str) -> None:
        self._config.ocr.engine = text
        self._persist()

    def _on_pdf_dpi_changed(self, text: str) -> None:
        try:
            self._config.pdf.display_dpi = int(text)
            self._persist()
        except ValueError:
            pass

    def _on_ai_classifier_changed(self, text: str) -> None:
        self._config.ai.classifier_type = text
        self._persist()

    def _on_export_format_changed(self, text: str) -> None:
        self._config.export.default_format = text
        self._persist()

    def _build_categories(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(16)
        lay.addWidget(self._section_title("Error Classifications"))
        
        desc = QLabel("Manage the dynamic error categories used by the AI classifier.")
        desc.setObjectName("SubCaption")
        lay.addWidget(desc)
        
        # Add new category form
        form = QHBoxLayout()
        self._new_cat_name = QLineEdit()
        self._new_cat_name.setPlaceholderText("New Category Name...")
        self._new_cat_name.setFixedHeight(36)
        
        add_btn = QPushButton("Add Category")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.setFixedHeight(36)
        add_btn.clicked.connect(self._on_add_category)
        
        form.addWidget(self._new_cat_name)
        form.addWidget(add_btn)
        lay.addLayout(form)
        
        # List widget to show categories
        self._cat_list = QListWidget()
        self._cat_list.setStyleSheet(
            "QListWidget { background: #1B1C1F; border: 1px solid #3A3C42; border-radius: 6px; padding: 4px; }"
            "QListWidget::item { padding: 12px; border-bottom: 1px solid #26272B; color: #E5E7EB; }"
        )
        lay.addWidget(self._cat_list, 1)
        
        self._refresh_categories()
        
        return page

    def _on_add_category(self) -> None:
        name = self._new_cat_name.text().strip()
        if not name:
            return
        if self._controller:
            self._controller.add_category(name)
            self._new_cat_name.clear()
            self._refresh_categories()
            QMessageBox.information(self, "Success", f"Category '{name}' added successfully.")
            
    def _refresh_categories(self) -> None:
        self._cat_list.clear()
        if self._controller:
            cats = self._controller.get_all_categories()
            for c in cats:
                name = c.get("name", "Unknown")
                self._cat_list.addItem(name)

    def _build_about(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(16)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        logo = QLabel("🔍")
        logo.setFont(QFont("Segoe UI", 52))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        name = QLabel(self._config.app_name)
        name.setFont(QFont("Segoe UI Variable", 18, QFont.Weight.Bold))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)

        ver = QLabel(f"Version {self._config.version}  ·  Environment: {self._config.environment}")
        ver.setObjectName("SubCaption")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        config_path_str = str(DEFAULT_CONFIG_PATH)
        for key, val in [
            ("Technology Stack", "PySide6 6.7+, Python 3.12, QtCharts"),
            ("OCR Engine",       "PaddleOCR / TrOCR / Tesseract (hybrid backend)"),
            ("Classifier",       "DistilBERT / Hybrid NLP Pipeline"),
            ("Config File",      config_path_str),
            ("License",          "MIT License — © 2026 UCC Engineering"),
        ]:
            row_lbl = QLabel(f"<b>{key}:</b>  {val}")
            row_lbl.setFont(QFont("Segoe UI", 13))
            row_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(row_lbl)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(12)

        reload_btn = QPushButton("  🔄  Reload Config")
        reload_btn.setObjectName("SecondaryBtn")
        reload_btn.setFixedHeight(36)
        reload_btn.setFixedWidth(160)
        reload_btn.clicked.connect(self._on_reload_config)
        btn_row.addWidget(reload_btn)

        updates_btn = QPushButton("  ⚡  Check for Updates")
        updates_btn.setObjectName("SecondaryBtn")
        updates_btn.setFixedHeight(36)
        updates_btn.setFixedWidth(180)
        btn_row.addWidget(updates_btn)

        lay.addSpacing(12)
        lay.addLayout(btn_row)
        lay.addStretch()
        return page

    def _on_reload_config(self) -> None:
        self._config = reload_config()
        self._folder_edit.setText(self._config.ui.default_projects_dir)
        QMessageBox.information(
            self,
            "Configuration Reloaded",
            "Application configuration has been reloaded from config.yaml.",
        )

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI Variable", 22, QFont.Weight.Bold))
        return lbl

    @staticmethod
    def _form_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        return lbl

    def _browse_folder(self) -> None:
        path = open_folder(self)
        if path:
            self._folder_edit.setText(path)
            self._config.ui.default_projects_dir = path
            self._persist()

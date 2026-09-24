"""
settings_screen.py — Settings screen.

Provides:
    SettingsPage(QWidget)
<<<<<<< HEAD
        Multi-tab settings panel: Appearance / Application / AI & Processing / About.
        Uses a left-side tab list and a stacked content area on the right.
        Directly integrated with the centralized Configuration Management system.
=======
        Three-tab settings panel: Appearance / Application / About.
        Uses a left-side tab list card and stacked container on the right.
>>>>>>> origin/feature/ui-overhaul
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
    """Horizontal group of mutually-exclusive toggle buttons inside a modern light card."""

    def __init__(self, options: list[str], parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for i, opt in enumerate(options):
            btn = QPushButton(opt)
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #64748B;
                    border: none;
                    border-radius: 6px;
                    padding: 0 16px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    color: #1E293B;
                }
                QPushButton:checked {
                    background: #0284C7;
                    color: #FFFFFF;
                    font-weight: 600;
                }
            """)
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
<<<<<<< HEAD
    Settings — tabbed interface for Appearance, Application, AI & Processing, and About.
    Fully connected to Centralized Configuration Management (AppConfig).
=======
    Settings — tabbed interface for Appearance, Application, and About matching modern UI design.
>>>>>>> origin/feature/ui-overhaul
    """

    def __init__(self, theme_manager=None, controller=None, parent=None):
        super().__init__(parent)
        self._theme = theme_manager
        self._controller = controller
        self._config: AppConfig = get_config()

        # Global page light background styling
        self.setStyleSheet("""
            SettingsPage {
                background-color: #F8FAFC;
            }
            QLabel {
                color: #0F172A;
            }
            QComboBox {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 12px;
                color: #0F172A;
                font-size: 13px;
            }
            QComboBox:hover {
                border-color: #94A3B8;
            }
            QLineEdit {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 12px;
                color: #0F172A;
                font-size: 13px;
            }
            QCheckBox {
                color: #334155;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                background: #FFFFFF;
            }
            QCheckBox::indicator:checked {
                background: #0284C7;
                border-color: #0284C7;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #E2E8F0;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0284C7;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0284C7;
                border: 2px solid #FFFFFF;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(24)

        # ── Tab list card (left) ──────────────────────────────────
        nav_container = QFrame()
        nav_container.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
        """)
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(12, 16, 12, 16)

        tab_list = QListWidget()
        tab_list.setObjectName("NavList")
        tab_list.setFixedWidth(220)
<<<<<<< HEAD
        tab_list.setStyleSheet(
            "#NavList { background: #26272B; border-right:1px solid #3A3C42; }"
            "#NavList::item { height:44px; padding-left:20px; border-radius:6px;"
            " margin:4px 8px; color:#A6A9B1; font-size:13px; }"
            "#NavList::item:selected { background:#3E9BFF2A;"
            " color:#3E9BFF; font-weight:600; }"
        )
=======
        tab_list.setStyleSheet("""
            #NavList {
                background: transparent;
                border: none;
                outline: none;
            }
            #NavList::item {
                height: 40px;
                padding-left: 12px;
                border-radius: 8px;
                margin: 2px 0px;
                color: #475569;
                font-size: 14px;
                font-weight: 500;
            }
            #NavList::item:hover {
                background: #F1F5F9;
                color: #0F172A;
            }
            #NavList::item:selected {
                background: #E0F2FE;
                color: #0284C7;
                font-weight: 600;
            }
        """)
>>>>>>> origin/feature/ui-overhaul

        icons = ["🎨", "⚙", "🤖", "🏷", "ℹ"]
        for tab, icon in zip(_TABS, icons):
            item = QListWidgetItem(f"  {icon}   {tab}")
            item.setSizeHint(QSize(220, 40))
            tab_list.addItem(item)
        tab_list.setCurrentRow(0)
        nav_layout.addWidget(tab_list)

        # ── Content stack (right) ─────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_appearance())
        self._stack.addWidget(self._build_application())
        self._stack.addWidget(self._build_processing())
        self._stack.addWidget(self._build_categories())
        self._stack.addWidget(self._build_about())

        tab_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        root.addWidget(nav_container)
        root.addWidget(self._stack, 1)

    def _persist(self) -> None:
        """Helper to save active configuration to disk."""
        try:
            save_config(self._config)
        except Exception:
            pass

    # ── Tab pages ─────────────────────────────────────────────────

    def _build_appearance(self) -> QWidget:
        page = QFrame()
        page.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
        """)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 32, 32, 32)
        lay.setSpacing(24)
        lay.addWidget(self._section_title("Appearance"))

        form = QFormLayout()
        form.setSpacing(20)
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
<<<<<<< HEAD
        font_slider.valueChanged.connect(self._on_font_scale_changed)
=======

        small_lbl = QLabel("Small")
        small_lbl.setStyleSheet("color: #64748B; font-size: 12px;")
        large_lbl = QLabel("Large")
        large_lbl.setStyleSheet("color: #64748B; font-size: 12px;")
>>>>>>> origin/feature/ui-overhaul

        font_row = QHBoxLayout()
        font_row.setSpacing(12)
        font_row.addWidget(small_lbl)
        font_row.addWidget(font_slider)
        font_row.addWidget(large_lbl)
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
<<<<<<< HEAD
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(28)
        lay.addWidget(self._section_title("Application & Storage"))
=======
        page = QFrame()
        page.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
        """)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 32, 32, 32)
        lay.setSpacing(24)
        lay.addWidget(self._section_title("Application"))
>>>>>>> origin/feature/ui-overhaul

        form = QFormLayout()
        form.setSpacing(20)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        # Default folder
        folder_row = QHBoxLayout()
<<<<<<< HEAD
        self._folder_edit = QLineEdit(self._config.ui.default_projects_dir)
=======
        folder_row.setSpacing(8)
        self._folder_edit = QLineEdit("D:\\UCC\\Projects")
>>>>>>> origin/feature/ui-overhaul
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setFixedHeight(36)
        folder_row.addWidget(self._folder_edit, 1)

        browse = QToolButton()
        browse.setText("Browse…")
        browse.setFixedHeight(36)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.setStyleSheet("""
            QToolButton {
                background: #F1F5F9;
                color: #334155;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: 500;
            }
            QToolButton:hover {
                background: #E2E8F0;
                color: #0F172A;
            }
        """)
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

        # AI Auto-Approval for High Confidence
        auto_chk = QCheckBox("Automatically mark high-confidence comments as Approved")
        auto_chk.setChecked(getattr(self._config.ai, "auto_approve_high_confidence", True))
        auto_chk.toggled.connect(self._on_auto_approve_toggled)
        form.addRow(self._form_label("Auto-Approval:"), auto_chk)

        thresh_combo = QComboBox()
        thresh_combo.addItems(["75%", "80%", "85%", "90%", "95%"])
        cur_pct = f"{int(getattr(self._config.ai, 'auto_approve_threshold', 0.85) * 100)}%"
        thresh_combo.setCurrentText(cur_pct if cur_pct in ["75%", "80%", "85%", "90%", "95%"] else "85%")
        thresh_combo.setFixedHeight(36)
        thresh_combo.setFixedWidth(200)
        thresh_combo.currentTextChanged.connect(self._on_auto_approve_threshold_changed)
        form.addRow(self._form_label("Auto-Approve Threshold:"), thresh_combo)

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

    def _on_auto_approve_toggled(self, checked: bool) -> None:
        self._config.ai.auto_approve_high_confidence = checked
        self._persist()

    def _on_auto_approve_threshold_changed(self, text: str) -> None:
        try:
            val = float(text.replace("%", "").strip()) / 100.0
            self._config.ai.auto_approve_threshold = val
            self._persist()
        except ValueError:
            pass

    def reload_data(self) -> None:
        """Auto-refresh settings data and dynamic category list from database."""
        self._refresh_categories()

    def _build_categories(self) -> QWidget:
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(14)
        
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(self._section_title("Error Classifications"))
        hdr_row.addStretch()
        self._cat_count_lbl = QLabel("0 Categories")
        self._cat_count_lbl.setStyleSheet("color: #4ADE80; font-weight: 600; font-size: 13px;")
        hdr_row.addWidget(self._cat_count_lbl)
        lay.addLayout(hdr_row)
        
        desc = QLabel(
            "Configure the master error categories, department scope, and trigger keywords "
            "used by AI and rule-based classifiers."
        )
        desc.setObjectName("SubCaption")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        
        # Add new category form container
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background-color: #1A1D24;
                border: 1px solid #2E333D;
                border-radius: 8px;
            }
        """)
        form_lay = QVBoxLayout(form_frame)
        form_lay.setSpacing(10)
        form_lay.setContentsMargins(14, 14, 14, 14)

        # Row 1: Category Name + Department Scope dropdown
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        name_box = QVBoxLayout()
        name_box.setSpacing(4)
        lbl_name = QLabel("Category Name:")
        lbl_name.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 600;")
        name_box.addWidget(lbl_name)
        self._new_cat_name = QLineEdit()
        self._new_cat_name.setPlaceholderText("e.g. Flange Rating Mismatch, Cable Tray Clash...")
        self._new_cat_name.setFixedHeight(36)
        self._new_cat_name.setStyleSheet("background-color: #12141A; color: #F8FAFC; border: 1px solid #334155; border-radius: 6px; padding: 0 10px;")
        self._new_cat_name.returnPressed.connect(self._on_add_category)
        name_box.addWidget(self._new_cat_name)
        row1.addLayout(name_box, 6)

        scope_box = QVBoxLayout()
        scope_box.setSpacing(4)
        lbl_scope = QLabel("Department Scope:")
        lbl_scope.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 600;")
        scope_box.addWidget(lbl_scope)
        self._new_cat_dept = QComboBox()
        self._new_cat_dept.setFixedHeight(36)
        self._new_cat_dept.setStyleSheet("background-color: #12141A; color: #F8FAFC; border: 1px solid #334155; border-radius: 6px; padding: 0 10px;")
        self._populate_scope_combo()
        scope_box.addWidget(self._new_cat_dept)
        row1.addLayout(scope_box, 4)

        form_lay.addLayout(row1)

        # Row 2: Trigger Keywords / Phrases + Action Buttons
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        kw_box = QVBoxLayout()
        kw_box.setSpacing(4)
        lbl_kw = QLabel("Identifying Trigger Keywords / Phrases (Comma-separated):")
        lbl_kw.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 600;")
        kw_box.addWidget(lbl_kw)
        self._new_cat_keywords = QLineEdit()
        self._new_cat_keywords.setPlaceholderText("e.g. flange rating, class 150, class 300, #150, #300, rtj...")
        self._new_cat_keywords.setFixedHeight(36)
        self._new_cat_keywords.setStyleSheet("background-color: #12141A; color: #F8FAFC; border: 1px solid #334155; border-radius: 6px; padding: 0 10px;")
        self._new_cat_keywords.returnPressed.connect(self._on_add_category)
        kw_box.addWidget(self._new_cat_keywords)
        row2.addLayout(kw_box, 7)

        btn_box = QVBoxLayout()
        btn_box.setSpacing(4)
        lbl_btn = QLabel(" ")
        btn_box.addWidget(lbl_btn)
        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        add_btn = QPushButton("  ➕  Add Category")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.setFixedHeight(36)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: #FFFFFF;
                font-weight: 600;
                border-radius: 6px;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #0369A1; }
            QPushButton:pressed { background-color: #075985; }
        """)
        add_btn.clicked.connect(self._on_add_category)
        btns_row.addWidget(add_btn)

        del_btn = QPushButton("  🗑  Delete Selected")
        del_btn.setObjectName("SecondaryBtn")
        del_btn.setFixedHeight(36)
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: #26272B;
                color: #EF4444;
                border: 1px solid #3A3C42;
                font-weight: 600;
                border-radius: 6px;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #EF444422; border-color: #EF4444; }
        """)
        del_btn.clicked.connect(self._on_delete_category)
        btns_row.addWidget(del_btn)

        btn_box.addLayout(btns_row)
        row2.addLayout(btn_box, 3)

        form_lay.addLayout(row2)

        kw_help = QLabel("💡 Scope determines which drawing departments use this category. Trigger keywords enable AI & rules to auto-classify Column 9 OCR text into this Category in Column 10.")
        kw_help.setStyleSheet("color: #64748B; font-size: 11px; padding: 2px 2px 0 2px;")
        form_lay.addWidget(kw_help)

        lay.addWidget(form_frame)

        # Department Filter for Categories List
        filter_row = QHBoxLayout()
        filter_lbl = QLabel("Filter Categories by Scope:")
        filter_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600;")
        filter_row.addWidget(filter_lbl)

        self._filter_dept_combo = QComboBox()
        self._filter_dept_combo.setFixedHeight(30)
        self._filter_dept_combo.setStyleSheet("background-color: #161922; color: #E2E8F0; border: 1px solid #334155; border-radius: 4px; padding: 0 8px;")
        self._filter_dept_combo.addItem("Show All Categories")
        self._filter_dept_combo.addItem("All Departments (Universal Only)")
        for dept in ["Piping Engineering", "Electrical Engineering", "Pipe Support Engineering", "Structural & Physical Design", "System Engineering", "GPD", "Plakon"]:
            self._filter_dept_combo.addItem(dept)
        self._filter_dept_combo.currentTextChanged.connect(self._refresh_categories)
        filter_row.addWidget(self._filter_dept_combo)
        filter_row.addStretch()

        lay.addLayout(filter_row)
        
        # List widget to show categories
        self._cat_list = QListWidget()
        self._cat_list.setStyleSheet(
            "QListWidget { background: #12141A; border: 1px solid #282D37; border-radius: 8px; padding: 6px; }"
            "QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #1E222B; color: #E5E7EB; font-size: 13px; }"
            "QListWidget::item:selected { background: rgba(2, 132, 199, 0.25); color: #38BDF8; font-weight: 600; border-radius: 6px; }"
        )
        lay.addWidget(self._cat_list, 1)
        
        self._refresh_categories()
        
        return page

    def _populate_scope_combo(self) -> None:
        self._new_cat_dept.clear()
        self._new_cat_dept.addItem("🌐 All Departments (Universal)")
        depts = []
        if self._controller and hasattr(self._controller, "department_repo"):
            try:
                dept_rows = self._controller.department_repo.get_all_departments()
                depts = [d.get("name") for d in dept_rows if d.get("name")]
            except Exception:
                pass
        if not depts:
            depts = [
                "Piping Engineering", "Electrical Engineering",
                "Pipe Support Engineering", "Structural & Physical Design",
                "System Engineering", "GPD", "Plakon"
            ]
        for d in depts:
            self._new_cat_dept.addItem(f"📁 {d}")

    def _on_add_category(self) -> None:
        name = self._new_cat_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Input Required", "Please enter a category name.")
            return

        scope_text = self._new_cat_dept.currentText().strip()
        dept_name = None
        if "All Departments" not in scope_text:
            dept_name = scope_text.replace("📁", "").strip()

        keywords = self._new_cat_keywords.text().strip()

        if self._controller:
            self._controller.add_category(name=name, department_name=dept_name, keywords=keywords)
            self._new_cat_name.clear()
            self._new_cat_keywords.clear()
            self._refresh_categories()
            scope_desc = f"for '{dept_name}'" if dept_name else "across 'All Departments'"
            QMessageBox.information(self, "Success", f"Category '{name}' added successfully {scope_desc}.")
        else:
            QMessageBox.warning(self, "Error", "Database controller is not connected.")

    def _on_delete_category(self) -> None:
        item = self._cat_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Selection Required", "Please select a category from the list to delete.")
            return

        cat_data = item.data(Qt.ItemDataRole.UserRole)
        cat_name = cat_data.get("name") if isinstance(cat_data, dict) else str(cat_data)
        dept_name = cat_data.get("department_name") if isinstance(cat_data, dict) else None

        # Standard categories check
        from src.infrastructure.storage.repository import CategoryRepository
        if cat_name in CategoryRepository.DEFAULT_CATEGORIES and not dept_name:
            reply = QMessageBox.question(
                self,
                "Standard Category",
                f"'{cat_name}' is a universal standard category. Are you sure you want to remove it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        else:
            scope_desc = f"from {dept_name}" if dept_name else "across all departments"
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete category '{cat_name}' {scope_desc}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if self._controller:
            success = self._controller.delete_category(cat_name, department_name=dept_name)
            if success:
                self._refresh_categories()
                QMessageBox.information(self, "Deleted", f"Category '{cat_name}' has been deleted.")
            else:
                QMessageBox.warning(self, "Error", f"Failed to delete category '{cat_name}'.")
            
    def _refresh_categories(self) -> None:
        if not hasattr(self, "_cat_list"):
            return
        self._cat_list.clear()
        if self._controller:
            cats = self._controller.get_all_categories()
            if not cats and hasattr(self._controller, "category_repo"):
                try:
                    self._controller.category_repo.seed_default_categories()
                    cats = self._controller.get_all_categories()
                except Exception:
                    pass

            # Filter if selected
            filter_val = self._filter_dept_combo.currentText().strip() if hasattr(self, "_filter_dept_combo") else "Show All Categories"
            if filter_val == "All Departments (Universal Only)":
                cats = [c for c in cats if not c.get("department_name")]
            elif filter_val not in ("Show All Categories", ""):
                cats = [c for c in cats if c.get("department_name") == filter_val]

            for c in cats:
                name = c.get("name", "Unknown")
                dept = c.get("department_name")
                kws = c.get("keywords") or ""

                if dept:
                    label_str = f"🏷  {name}   [📁 {dept}]"
                    item = QListWidgetItem(label_str)
                    tip = f"Custom Category: {name}\nScope: {dept}"
                    if kws:
                        tip += f"\nTrigger Keywords: {kws}"
                    item.setToolTip(tip)
                else:
                    label_str = f"🔒  {name}   [🌐 All Departments]"
                    item = QListWidgetItem(label_str)
                    tip = f"Universal Category: {name}\nScope: All Departments"
                    if kws:
                        tip += f"\nTrigger Keywords: {kws}"
                    item.setToolTip(tip)

                item.setData(Qt.ItemDataRole.UserRole, {"name": name, "department_name": dept, "keywords": kws})
                self._cat_list.addItem(item)

            if hasattr(self, "_cat_count_lbl"):
                self._cat_count_lbl.setText(f"{len(cats)} Categories")

    def _build_about(self) -> QWidget:
        page = QFrame()
        page.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
        """)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 32, 32, 32)
        lay.setSpacing(16)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        logo = QLabel("🔍")
        logo.setFont(QFont("Segoe UI", 48))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        name = QLabel(self._config.app_name)
        name.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        name.setStyleSheet("color: #0F172A;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)

        ver = QLabel(f"Version {self._config.version}  ·  Environment: {self._config.environment}")
        ver.setStyleSheet("color: #64748B; font-size: 13px;")
        ver.setObjectName("SubCaption")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none;")
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
            row_lbl.setStyleSheet("color: #334155;")
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
        lbl.setFont(QFont("Segoe UI Variable", 20, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #0F172A;")
        return lbl

    @staticmethod
    def _form_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
        lbl.setStyleSheet("color: #475569;")
        return lbl

    def _browse_folder(self) -> None:
        path = open_folder(self)
        if path:
            self._folder_edit.setText(path)
            self._config.ui.default_projects_dir = path
            self._persist()

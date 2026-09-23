"""
settings_screen.py — Settings screen.

Provides:
    SettingsPage(QWidget)
        Three-tab settings panel: Appearance / Application / About.
        Uses a left-side tab list card and stacked container on the right.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFrame,
                                QLabel, QListWidget, QListWidgetItem,
                                QStackedWidget, QComboBox, QSlider,
                                QCheckBox, QLineEdit, QToolButton,
                                QPushButton, QFormLayout, QButtonGroup)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from app.components.dialogs import open_folder

_TABS = ["Appearance", "Application", "About"]


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
        self._group.button(0).setChecked(True)

    @property
    def group(self) -> QButtonGroup:
        return self._group


# ── SettingsPage ──────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    """
    Settings — tabbed interface for Appearance, Application, and About matching modern UI design.
    """

    def __init__(self, theme_manager=None, parent=None):
        super().__init__(parent)
        self._theme = theme_manager

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

        icons = ["🎨", "⚙", "ℹ"]
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
        self._stack.addWidget(self._build_about())

        tab_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        root.addWidget(nav_container)
        root.addWidget(self._stack, 1)

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
        if self._theme and self._theme.current == "dark":
            theme_ctrl.group.button(1).setChecked(True)

        def _on_theme(id_: int) -> None:
            if self._theme:
                self._theme.apply("light" if id_ == 0 else "dark")

        theme_ctrl.group.idClicked.connect(_on_theme)
        form.addRow(self._form_label("Theme:"), theme_ctrl)

        # Language
        lang = QComboBox()
        lang.addItems(["English (US)", "Hindi", "German", "French", "Spanish"])
        lang.setFixedHeight(36)
        form.addRow(self._form_label("Language:"), lang)

        # Font size slider
        font_slider = QSlider(Qt.Orientation.Horizontal)
        font_slider.setRange(0, 2)
        font_slider.setValue(1)
        font_slider.setTickInterval(1)
        font_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        font_slider.setFixedWidth(200)

        small_lbl = QLabel("Small")
        small_lbl.setStyleSheet("color: #64748B; font-size: 12px;")
        large_lbl = QLabel("Large")
        large_lbl.setStyleSheet("color: #64748B; font-size: 12px;")

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

    def _build_application(self) -> QWidget:
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

        form = QFormLayout()
        form.setSpacing(20)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        # Default folder
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self._folder_edit = QLineEdit("D:\\UCC\\Projects")
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

        # Auto save
        auto_save = QCheckBox("Auto-save review progress")
        auto_save.setChecked(True)
        form.addRow(self._form_label("Auto-Save:"), auto_save)

        # Notifications
        notif = QCheckBox("Enable desktop notifications")
        notif.setChecked(True)
        form.addRow(self._form_label("Notifications:"), notif)

        # Page size
        page_size = QComboBox()
        page_size.addItems(["10", "25", "50", "100"])
        page_size.setCurrentText("25")
        page_size.setFixedHeight(36)
        page_size.setFixedWidth(100)
        form.addRow(self._form_label("Rows per Page:"), page_size)

        lay.addLayout(form)
        lay.addStretch()
        return page

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

        name = QLabel("UCC AI Drawing Review Comment Analyzer")
        name.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        name.setStyleSheet("color: #0F172A;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)

        ver = QLabel("Version 1.0.0  ·  Build 2026.08.04")
        ver.setStyleSheet("color: #64748B; font-size: 13px;")
        ver.setObjectName("SubCaption")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #E2E8F0; max-height: 1px; border: none;")
        lay.addWidget(sep)

        for key, val in [
            ("Technology Stack", "PySide6 6.7+, Python 3.12, QtCharts"),
            ("OCR Engine",       "PaddleOCR / TrOCR (backend)"),
            ("Classifier",       "DistilBERT (backend)"),
            ("License",          "MIT License — © 2026 UCC Engineering"),
        ]:
            row_lbl = QLabel(f"<b>{key}:</b>  {val}")
            row_lbl.setFont(QFont("Segoe UI", 13))
            row_lbl.setStyleSheet("color: #334155;")
            row_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(row_lbl)

        updates_btn = QPushButton("  🔄   Check for Updates")
        updates_btn.setObjectName("SecondaryBtn")
        updates_btn.setFixedHeight(38)
        updates_btn.setFixedWidth(220)
        updates_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        updates_btn.setStyleSheet("""
            QPushButton {
                background: #F1F5F9;
                color: #0284C7;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #E0F2FE;
                border-color: #0284C7;
            }
        """)
        lay.addSpacing(8)
        lay.addWidget(updates_btn, 0, Qt.AlignmentFlag.AlignCenter)

        lay.addStretch()
        return page

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
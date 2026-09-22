"""
export_screen.py — Redesigned Export screen.

Provides:
    ExportPage(QWidget)
        Format selector cards (Excel / JSON / CSV), scope radio buttons with
        dynamic date range controls, export progress, and export history table.
"""
from __future__ import annotations
from datetime import date as _date
from pathlib import Path
from typing import Optional, Any

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                                QLabel, QPushButton, QRadioButton, QButtonGroup,
                                QProgressBar, QTableView, QHeaderView,
                                QAbstractItemView, QFileDialog, QMessageBox,
                                QDateEdit, QSizePolicy, QScrollArea)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PySide6.QtCore import Qt, QTimer, QDate

from src.core.dtos.export_dtos import ExportConfigDTO, ExportFormat
from app import mock_data as md

# ── Format definitions ────────────────────────────────────────────────────────

_FORMATS = [
    ("📊", "Excel", ".xlsx", "Full comment register with metadata, sheets, and formatting", "#10B981"),
    ("📜", "JSON",  ".json", "Structured machine-readable format for API & model pipelines", "#3B82F6"),
    ("📋", "CSV",   ".csv",  "Raw tabular comma-separated values for data analysis",       "#F59E0B"),
]


class _FormatCard(QFrame):
    """Selectable export-format card with content-driven responsive layout."""

    def __init__(self, icon: str, name: str, ext: str,
                 desc: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(210)
        self.setMinimumWidth(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False
        self._color    = color
        self._name     = name

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 22)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon
        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFont(QFont("Segoe UI Emoji", 34))
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._icon_lbl)

        # Name
        self._name_lbl = QLabel(name)
        self._name_lbl.setFont(QFont("Inter", 18, QFont.Weight.Bold))
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_lbl.setStyleSheet("background: transparent; color: #F3F4F6;")
        lay.addWidget(self._name_lbl)

        # Extension Badge
        self._ext_badge = QLabel(ext.upper())
        self._ext_badge.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        self._ext_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ext_badge.setStyleSheet(
            f"color: {color}; background-color: {color}22;"
            f"border: 1px solid {color}55; border-radius: 6px; padding: 3px 10px;"
        )
        lay.addWidget(self._ext_badge, 0, Qt.AlignmentFlag.AlignCenter)

        # Description
        self._desc_lbl = QLabel(desc)
        self._desc_lbl.setObjectName("SubCaption")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_lbl.setStyleSheet("background: transparent; color: #9CA3AF; font-size: 13px; line-height: 1.4;")
        lay.addWidget(self._desc_lbl)

        lay.addSpacing(4)

        # Selection Indicator Pill
        self._indicator = QLabel("Select Format")
        self._indicator.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._indicator.setStyleSheet(
            "color: #9CA3AF; background-color: #282E3B; border-radius: 6px; padding: 4px 12px;"
        )
        lay.addWidget(self._indicator, 0, Qt.AlignmentFlag.AlignCenter)

    def set_selected(self, v: bool) -> None:
        self._selected = v
        if v:
            self.setStyleSheet(
                f"#Card {{ border: 2px solid {self._color};"
                f" border-radius: 12px;"
                f" background-color: #EFF6FF; }}"
            )
            self._indicator.setText("✓ Selected")
            self._indicator.setStyleSheet(
                f"color: #FFFFFF; background-color: {self._color};"
                f"border-radius: 6px; padding: 4px 14px; font-weight: bold;"
            )
        else:
            self.setStyleSheet(
                "#Card { border: 1px solid #E2E8F0;"
                " border-radius: 12px;"
                " background-color: #FFFFFF; }"
                "#Card:hover { border-color: #2563EB; background-color: #F8FAFC; }"
            )
            self._indicator.setText("Click to Select")
            self._indicator.setStyleSheet(
                "color: #64748B; background-color: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px; padding: 4px 12px;"
            )


class ExportPage(QWidget):
    """
    Export — format selection cards, scope options with date range,
    animated export progress bar, and historical export audit table.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller       = controller
        self._selected_format  = "Excel"
        self._format_cards: list[_FormatCard] = []
        self._progress         = 0

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(24)

        # ── Page Header ──────────────────────────────────────────
        hdr_box = QVBoxLayout()
        hdr_box.setSpacing(4)
        title = QLabel("Export Drawing Reviews")
        title.setFont(QFont("Inter", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #F3F4F6;")
        hdr_box.addWidget(title)

        subtitle = QLabel("Generate and download drawing review reports, comment registers, and structured metadata.")
        subtitle.setObjectName("PageSubtitle")
        hdr_box.addWidget(subtitle)
        root.addLayout(hdr_box)

        # ── Format Cards Section ──────────────────────────────────
        fmt_section = QVBoxLayout()
        fmt_section.setSpacing(12)
        fmt_lbl = QLabel("SELECT EXPORT FORMAT")
        fmt_lbl.setObjectName("FormLabel")
        fmt_section.addWidget(fmt_lbl)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(20)
        for icon, name, ext, desc, color in _FORMATS:
            card = _FormatCard(icon, name, ext, desc, color)
            card.mousePressEvent = self._make_select_handler(card, name)
            self._format_cards.append(card)
            fmt_row.addWidget(card, 1)

        self._format_cards[0].set_selected(True)
        fmt_section.addLayout(fmt_row)
        root.addLayout(fmt_section)

        # ── Scope Options Card ────────────────────────────────────
        scope_card = QFrame()
        scope_card.setObjectName("Card")
        scope_lay = QVBoxLayout(scope_card)
        scope_lay.setContentsMargins(24, 20, 24, 20)
        scope_lay.setSpacing(14)

        scope_title = QLabel("EXPORT SCOPE")
        scope_title.setObjectName("FormLabel")
        scope_lay.addWidget(scope_title)

        self._scope_grp = QButtonGroup(self)
        self._rb_curr = QRadioButton("Current Active Drawing & Comments")
        self._rb_curr.setChecked(True)
        self._scope_grp.addButton(self._rb_curr)
        scope_lay.addWidget(self._rb_curr)

        self._rb_date = QRadioButton("Date Range")
        self._scope_grp.addButton(self._rb_date)
        scope_lay.addWidget(self._rb_date)

        # Dynamic Date Range Container
        self._date_container = QWidget()
        date_lay = QHBoxLayout(self._date_container)
        date_lay.setContentsMargins(28, 0, 0, 8)
        date_lay.setSpacing(16)

        d1_lbl = QLabel("From:")
        d1_lbl.setObjectName("SubCaption")
        date_lay.addWidget(d1_lbl)
        self._date_start = QDateEdit(QDate.currentDate().addDays(-30))
        self._date_start.setCalendarPopup(True)
        self._date_start.setFixedHeight(38)
        date_lay.addWidget(self._date_start)

        d2_lbl = QLabel("To:")
        d2_lbl.setObjectName("SubCaption")
        date_lay.addWidget(d2_lbl)
        self._date_end = QDateEdit(QDate.currentDate())
        self._date_end.setCalendarPopup(True)
        self._date_end.setFixedHeight(38)
        date_lay.addWidget(self._date_end)
        date_lay.addStretch()

        self._date_container.hide()
        scope_lay.addWidget(self._date_container)

        self._rb_all = QRadioButton("All Projects & Comment Archives")
        self._scope_grp.addButton(self._rb_all)
        scope_lay.addWidget(self._rb_all)

        self._rb_date.toggled.connect(self._date_container.setVisible)
        root.addWidget(scope_card)

        # ── Export Action Row ─────────────────────────────────────
        act_row = QHBoxLayout()
        act_row.setSpacing(16)

        self._export_btn = QPushButton("  ↑  Export Report Now")
        self._export_btn.setObjectName("PrimaryBtn")
        self._export_btn.setFixedHeight(48)
        self._export_btn.setMinimumWidth(220)
        self._export_btn.clicked.connect(self._start_export)
        act_row.addWidget(self._export_btn)

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setFixedHeight(10)
        self._prog_bar.hide()
        act_row.addWidget(self._prog_bar, 1)

        self._status_msg = QLabel("")
        self._status_msg.setFont(QFont("Inter", 13))
        self._status_msg.setStyleSheet("color: #10B981;")
        self._status_msg.hide()
        act_row.addWidget(self._status_msg)

        act_row.addStretch()
        root.addLayout(act_row)

        # ── Export History Card ───────────────────────────────────
        hist_card = QFrame()
        hist_card.setObjectName("Card")
        hist_lay = QVBoxLayout(hist_card)
        hist_lay.setContentsMargins(20, 18, 20, 20)
        hist_lay.setSpacing(12)

        hist_title = QLabel("RECENT EXPORT HISTORY")
        hist_title.setObjectName("FormLabel")
        hist_lay.addWidget(hist_title)

        self._hist_table = self._build_history_table()
        hist_lay.addWidget(self._hist_table)
        root.addWidget(hist_card)

        scroll.setWidget(container)

        page_lay = QVBoxLayout(self)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)

    # ── Helpers ───────────────────────────────────────────────────

    def _make_select_handler(self, card: _FormatCard, name: str):
        def handler(e):
            for c in self._format_cards:
                c.set_selected(False)
            card.set_selected(True)
            self._selected_format = name
        return handler

    def _get_format_details(self) -> tuple[str, str, str]:
        fmt = self._selected_format
        if fmt == "JSON":
            return (ExportFormat.JSON, "JSON Files (*.json);;All Files (*)", ".json")
        elif fmt == "CSV":
            return (ExportFormat.CSV, "CSV Files (*.csv);;All Files (*)", ".csv")
        else:
            return (ExportFormat.EXCEL, "Excel Files (*.xlsx);;All Files (*)", ".xlsx")

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _start_export(self) -> None:
        fmt_code, filter_str, ext = self._get_format_details()
        today_str = _date.today().isoformat()

        drawing_no = "Comments"
        if self._controller and getattr(self._controller, "current_document", None):
            doc = self._controller.current_document
            if hasattr(doc, "file_name") and doc.file_name:
                drawing_no = doc.file_name.rsplit(".", 1)[0]

        default_filename = f"{drawing_no}_Export_{today_str}{ext}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {self._selected_format} File",
            default_filename,
            filter_str,
        )

        if not file_path:
            return

        out_path = Path(file_path)

        if self._controller is None:
            QMessageBox.critical(
                self,
                "Export Error",
                "Backend controller is not connected.",
            )
            return

        scope = "all"
        if self._rb_curr.isChecked():
            scope = "current"
        elif self._rb_date.isChecked():
            scope = "date_range"

        cfg = ExportConfigDTO(
            format=fmt_code,
            scope=scope,
            output_path=out_path,
        )

        self._export_btn.setEnabled(False)
        self._export_btn.setText("Generating Report...")
        self._prog_bar.show()
        self._prog_bar.setValue(25)

        try:
            res = self._controller.export_service.export_comments(cfg)
            self._prog_bar.setValue(100)

            if res.success:
                fsize = self._format_size(res.file_size_bytes)
                self._status_msg.setText(f"✓ Exported {res.record_count} comments successfully ({fsize})")
                self._status_msg.show()

                model = self._hist_table.model()
                new_row = [
                    QStandardItem(out_path.name),
                    QStandardItem(self._selected_format),
                    QStandardItem(today_str),
                    QStandardItem(fsize),
                ]
                for item in new_row:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
                model.insertRow(0, new_row)
            else:
                QMessageBox.warning(
                    self,
                    "Export Incomplete",
                    f"Export completed with warnings: {res.error_message}",
                )

        except Exception as exc:
            self._prog_bar.hide()
            QMessageBox.critical(
                self,
                "Export Failed",
                f"An error occurred while generating the export:\n{exc}",
            )
        finally:
            self._export_btn.setEnabled(True)
            self._export_btn.setText("  ↑  Export Report Now")

    def _build_history_table(self) -> QTableView:
        tbl = QTableView()
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setShowGrid(False)
        tbl.verticalHeader().hide()
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # NOTE: per-section setSectionResizeMode must come after setModel()
        tbl.setMinimumHeight(180)

        headers = ["File Name", "Format", "Date", "Size"]
        model = QStandardItemModel(0, len(headers))
        model.setHorizontalHeaderLabels(headers)

        rows = [
            ("PRJ-003_Review_Report_2026-07-10.xlsx", "Excel", "2026-07-10", "1.2 MB"),
            ("PRJ-001_Comments_Dataset_2026-07-28.csv",  "CSV",   "2026-07-28", "84 KB"),
            ("PRJ-002_Annotations_Dump_2026-07-25.json", "JSON",  "2026-07-25", "340 KB"),
        ]
        for fn, fmt, dt, sz in rows:
            items = [
                QStandardItem(fn),
                QStandardItem(fmt),
                QStandardItem(dt),
                QStandardItem(sz),
            ]
            for it in items:
                it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
            model.appendRow(items)

        tbl.setModel(model)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return tbl

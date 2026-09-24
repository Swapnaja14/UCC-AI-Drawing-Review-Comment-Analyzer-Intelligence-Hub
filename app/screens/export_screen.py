"""
export_screen.py — Redesigned Export screen matching modern light Enterprise theme.

Provides:
    ExportPage(QWidget)
        Responsive, scrollable layout with format selector cards (Excel / JSON / CSV),
        Standard Input metadata fields for the Error Tracker Sheet, scope options with date range,
        progress feedback, and export history table with double-click file opening.
"""
from __future__ import annotations
from datetime import date as _date
from pathlib import Path
from typing import Optional, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QProgressBar,
    QTableView,
    QHeaderView,
    QAbstractItemView,
    QFileDialog,
    QMessageBox,
    QDateEdit,
    QSizePolicy,
    QScrollArea,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PySide6.QtCore import Qt, QTimer, QDate

from src.core.dtos.export_dtos import ExportConfigDTO, ExportFormat
from app import mock_data as md

# ── Format definitions ────────────────────────────────────────────────────────

_FORMATS = [
    (
        "📊",
        "Excel Workbook",
        ".xlsx",
        "Full engineering audit dataset formatted with summary KPI sheets, category pivot tables, and high-res annotation snapshots.",
        "Includes Formulas & Formatting",
        "Excel",
    ),
    (
        "{}",
        "Structured JSON",
        ".json",
        "Hierarchical machine-readable payload containing bounding-box coordinates, OCR tokens, and confidence scores.",
        "API & Pipeline Ready",
        "JSON",
    ),
    (
        "📋",
        "Raw CSV Dataset",
        ".csv",
        "Flat tabular representation suitable for importing into external business intelligence tools, PowerBI, or Revit.",
        "Universal Compatibility",
        "CSV",
    ),
]


def _card(parent=None) -> QFrame:
    """Creates a light rounded card with subtle shadow matching UI style."""
    f = QFrame(parent)
    f.setObjectName("StitchCard")
    f.setStyleSheet(
        """
        QFrame#StitchCard {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
        }
        """
    )
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(8)
    shadow.setColor(QColor(15, 23, 42, 8))
    shadow.setOffset(0, 2)
    f.setGraphicsEffect(shadow)
    return f


class _FormatCard(QFrame):
    """Selectable export-format card with light enterprise theme and radio indicator."""

    def __init__(
        self,
        icon: str,
        title: str,
        ext: str,
        desc: str,
        footer: str,
        internal_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("FormatCard")
        self.setMinimumHeight(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False
        self.internal_name = internal_name

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        # Top Row: Icon + Badge + Select Indicator
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        icon_box = QFrame()
        icon_box.setFixedSize(36, 36)
        icon_box.setStyleSheet(
            "background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px;"
        )
        ib_lay = QHBoxLayout(icon_box)
        ib_lay.setContentsMargins(0, 0, 0, 0)
        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFont(QFont("Inter", 12))
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ib_lay.addWidget(self._icon_lbl)
        top_row.addWidget(icon_box)

        top_row.addStretch()

        self._ext_badge = QLabel(ext.upper())
        self._ext_badge.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        self._ext_badge.setStyleSheet(
            "color: #0284C7; background-color: #E0F2FE; "
            "border: 1px solid #BAE6FD; border-radius: 4px; padding: 2px 6px;"
        )
        top_row.addWidget(self._ext_badge)

        self._radio_ind = QLabel("○")
        self._radio_ind.setFont(QFont("Inter", 12))
        self._radio_ind.setStyleSheet("color: #94A3B8;")
        top_row.addWidget(self._radio_ind)

        lay.addLayout(top_row)

        self._name_lbl = QLabel(title)
        self._name_lbl.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet("color: #0F172A;")
        lay.addWidget(self._name_lbl)

        self._desc_lbl = QLabel(desc)
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(
            "color: #64748B; font-size: 11px; line-height: 1.4;"
        )
        lay.addWidget(self._desc_lbl)

        lay.addStretch()

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background-color: #F1F5F9;")
        lay.addWidget(div)

        self._footer_lbl = QLabel(f"⚙  {footer}")
        self._footer_lbl.setFont(QFont("Inter", 8, QFont.Weight.Medium))
        self._footer_lbl.setStyleSheet("color: #64748B;")
        lay.addWidget(self._footer_lbl)

        self.set_selected(False)

    def set_selected(self, v: bool) -> None:
        self._selected = v
        if v:
            self.setStyleSheet(
                "QFrame#FormatCard {"
                " background-color: #F0F9FF;"
                " border: 2px solid #0284C7;"
                " border-radius: 8px;"
                "}"
            )
            self._radio_ind.setText("●")
            self._radio_ind.setStyleSheet("color: #0284C7;")
        else:
            self.setStyleSheet(
                "QFrame#FormatCard {"
                " background-color: #FFFFFF;"
                " border: 1px solid #E2E8F0;"
                " border-radius: 8px;"
                "}"
                "QFrame#FormatCard:hover {"
                " border-color: #CBD5E1;"
                " background-color: #F8FAFC;"
                "}"
            )
            self._radio_ind.setText("○")
            self._radio_ind.setStyleSheet("color: #94A3B8;")


class ExportPage(QWidget):
    """
    Export — format selection cards, scope options with date range,
    Standard Input metadata fields for Error Tracker, animated export progress bar,
    and historical export audit table.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._selected_format = "Excel"
        self._format_cards: list[_FormatCard] = []
        self._progress = 0

        self.setObjectName("ExportPageRoot")
        self.setStyleSheet(
            """
            QWidget#ExportPageRoot {
                background-color: #F8FAFC;
            }
            QRadioButton {
                font-family: 'Inter';
                font-size: 11px;
                font-weight: 600;
                color: #0F172A;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
            }
            QCheckBox {
                font-family: 'Inter';
                font-size: 11px;
                font-weight: 600;
                color: #0F172A;
                spacing: 8px;
            }
            """
        )

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; }")

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        root = QVBoxLayout(container)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(18)

        # ── Page Header ──────────────────────────────────────────
        hdr_box = QVBoxLayout()
        hdr_box.setSpacing(4)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)

        tag1 = QLabel("● DATA PIPELINE")
        tag1.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        tag1.setStyleSheet("color: #0284C7;")

        tag2 = QLabel("• Export Engine v2.4")
        tag2.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        tag2.setStyleSheet("color: #059669; background: #ECFDF5; border-radius: 3px; padding: 1px 5px;")

        tag_row.addWidget(tag1)
        tag_row.addWidget(tag2)
        tag_row.addStretch()

        hdr_top = QHBoxLayout()
        hdr_top.addLayout(tag_row)

        quota_box = QFrame()
        quota_box.setStyleSheet("background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 4px 10px;")
        qb_lay = QHBoxLayout(quota_box)
        qb_lay.setContentsMargins(0, 0, 0, 0)
        lbl_quota = QLabel("💾  Storage Quota:  <b>48.6 / 250 GB</b>")
        lbl_quota.setFont(QFont("Inter", 8))
        lbl_quota.setStyleSheet("color: #475569;")
        qb_lay.addWidget(lbl_quota)
        hdr_top.addWidget(quota_box)

        hdr_box.addLayout(hdr_top)

        title = QLabel("Export Drawing Review Data")
        title.setFont(QFont("Inter", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #0F172A;")
        hdr_box.addWidget(title)

        subtitle = QLabel(
            "Generate customized audit reports, structured CAD annotation datasets, and compliance spreadsheets."
        )
        subtitle.setFont(QFont("Inter", 9))
        subtitle.setStyleSheet("color: #64748B;")
        hdr_box.addWidget(subtitle)
        root.addLayout(hdr_box)

        # ── Format Cards Section ──────────────────────────────────
        fmt_section = QVBoxLayout()
        fmt_section.setSpacing(10)

        fmt_hdr = QHBoxLayout()
        fmt_lbl = QLabel("● Select Export Format")
        fmt_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        fmt_lbl.setStyleSheet("color: #0F172A;")

        step1 = QLabel("Step 1 of 3")
        step1.setFont(QFont("Inter", 8))
        step1.setStyleSheet("color: #94A3B8;")

        fmt_hdr.addWidget(fmt_lbl)
        fmt_hdr.addStretch()
        fmt_hdr.addWidget(step1)
        fmt_section.addLayout(fmt_hdr)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(14)
        for icon, name, ext, desc, footer, internal_name in _FORMATS:
            card = _FormatCard(icon, name, ext, desc, footer, internal_name)
            card.mousePressEvent = self._make_select_handler(card, internal_name)
            self._format_cards.append(card)
            fmt_row.addWidget(card, 1)

        self._format_cards[0].set_selected(True)
        fmt_section.addLayout(fmt_row)
        root.addLayout(fmt_section)

        # ── Standard Input Fields (Error Tracker Metadata) ────────
        meta_section = QVBoxLayout()
        meta_section.setSpacing(10)

        meta_hdr = QHBoxLayout()
        meta_lbl = QLabel("● Standard Input Fields (Error Tracker Metadata)")
        meta_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        meta_lbl.setStyleSheet("color: #0F172A;")

        badge_lbl = QLabel("🟧 Error Tracker Input Metadata")
        badge_lbl.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        badge_lbl.setStyleSheet(
            "color: #D97706; background-color: #FEF3C7; "
            "border: 1px solid #FDE68A; border-radius: 4px; padding: 2px 6px;"
        )

        meta_hdr.addWidget(meta_lbl)
        meta_hdr.addWidget(badge_lbl)
        meta_hdr.addStretch()
        meta_section.addLayout(meta_hdr)

        meta_card = _card()
        meta_lay = QVBoxLayout(meta_card)
        meta_lay.setContentsMargins(16, 16, 16, 16)
        meta_lay.setSpacing(14)

        input_style = """
            QLineEdit {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                font-family: 'Inter', Arial;
            }
            QLineEdit:hover {
                border-color: #94A3B8;
            }
            QLineEdit:focus {
                border-color: #0284C7;
                background-color: #F8FAFC;
            }
        """

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)

        # Contract # & Plant Name
        c_box = QVBoxLayout()
        c_box.setSpacing(4)
        c_lbl = QLabel("Contract # (Column 2):")
        c_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        c_lbl.setStyleSheet("color: #475569;")
        self._contract_input = QLineEdit("CTR-2026-01")
        self._contract_input.setStyleSheet(input_style)
        self._contract_input.setPlaceholderText("e.g. CTR-2026-01")
        c_box.addWidget(c_lbl)
        c_box.addWidget(self._contract_input)
        grid.addLayout(c_box, 0, 0)

        p_box = QVBoxLayout()
        p_box.setSpacing(4)
        p_lbl = QLabel("Plant Name (Column 3):")
        p_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        p_lbl.setStyleSheet("color: #475569;")
        self._plant_input = QLineEdit("Austin Substation")
        self._plant_input.setStyleSheet(input_style)
        self._plant_input.setPlaceholderText("e.g. Austin Substation")
        p_box.addWidget(p_lbl)
        p_box.addWidget(self._plant_input)
        grid.addLayout(p_box, 0, 1)

        # E-Pod WO # & UCC-I Designer
        w_box = QVBoxLayout()
        w_box.setSpacing(4)
        w_lbl = QLabel("E-Pod WO # (Column 4):")
        w_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        w_lbl.setStyleSheet("color: #475569;")
        self._epod_input = QLineEdit("WO-440192")
        self._epod_input.setStyleSheet(input_style)
        self._epod_input.setPlaceholderText("e.g. WO-440192")
        w_box.addWidget(w_lbl)
        w_box.addWidget(self._epod_input)
        grid.addLayout(w_box, 1, 0)

        d_box = QVBoxLayout()
        d_box.setSpacing(4)
        d_lbl = QLabel("UCC-I Designer (Column 6):")
        d_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        d_lbl.setStyleSheet("color: #475569;")
        self._designer_input = QLineEdit("Lead Reviewer")
        self._designer_input.setStyleSheet(input_style)
        self._designer_input.setPlaceholderText("e.g. Lead Reviewer")
        d_box.addWidget(d_lbl)
        d_box.addWidget(self._designer_input)
        grid.addLayout(d_box, 1, 1)

        # Review Date & Engineering Department
        dt_box = QVBoxLayout()
        dt_box.setSpacing(4)
        dt_lbl = QLabel("Review Date (Column 1):")
        dt_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        dt_lbl.setStyleSheet("color: #475569;")
        self._date_input = QLineEdit(_date.today().strftime("%Y-%m-%d"))
        self._date_input.setStyleSheet(input_style)
        self._date_input.setPlaceholderText("YYYY-MM-DD")
        dt_box.addWidget(dt_lbl)
        dt_box.addWidget(self._date_input)
        grid.addLayout(dt_box, 2, 0)

        dept_box = QVBoxLayout()
        dept_box.setSpacing(4)
        dept_lbl = QLabel("Engineering Department (Column 10):")
        dept_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        dept_lbl.setStyleSheet("color: #475569;")
        self._dept_combo = QComboBox()
        self._dept_combo.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 6px 28px 6px 10px;
                font-size: 12px;
                font-family: 'Inter', Arial;
            }
            QComboBox:hover {
                border-color: #94A3B8;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                color: #0F172A;
                selection-background-color: #EFF6FF;
                selection-color: #0F172A;
                border: 1px solid #CBD5E1;
            }
        """)
        ucc_depts = [
            "Electrical Engineering",
            "GPD",
            "Pipe Support Engineering",
            "Piping Engineering",
            "Plakon",
            "Structural & Physical Design",
            "System Engineering",
        ]
        self._dept_combo.addItems(ucc_depts)
        self._dept_combo.setCurrentText("Piping Engineering")
        dept_box.addWidget(dept_lbl)
        dept_box.addWidget(self._dept_combo)
        grid.addLayout(dept_box, 2, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        meta_lay.addLayout(grid)
        meta_section.addWidget(meta_card)
        root.addLayout(meta_section)

        # ── Scope & Parameters Options Card ──────────────────────
        scope_section = QVBoxLayout()
        scope_section.setSpacing(10)

        scope_hdr = QHBoxLayout()
        scope_lbl = QLabel("● Export Scope & Parameters")
        scope_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        scope_lbl.setStyleSheet("color: #0F172A;")

        step2 = QLabel("Step 3 of 3")
        step2.setFont(QFont("Inter", 8))
        step2.setStyleSheet("color: #94A3B8;")

        scope_hdr.addWidget(scope_lbl)
        scope_hdr.addStretch()
        scope_hdr.addWidget(step2)
        scope_section.addLayout(scope_hdr)

        scope_card = _card()
        scope_lay = QVBoxLayout(scope_card)
        scope_lay.setContentsMargins(16, 16, 16, 16)
        scope_lay.setSpacing(12)

        lbl_sec_scope = QLabel("Scope of Export")
        lbl_sec_scope.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        lbl_sec_scope.setStyleSheet("color: #64748B;")
        scope_lay.addWidget(lbl_sec_scope)

        self._scope_grp = QButtonGroup(self)

        # Radio Option 1: Current Loaded Drawing
        opt1_card = QFrame()
        opt1_card.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;")
        opt1_lay = QVBoxLayout(opt1_card)
        opt1_lay.setContentsMargins(12, 10, 12, 10)
        self._rb_curr = QRadioButton("Current Loaded Drawing")
        self._rb_curr.setChecked(True)
        self._scope_grp.addButton(self._rb_curr)

        self._dwg_scope_lbl = QLabel("No drawing is currently loaded")
        self._dwg_scope_lbl.setFont(QFont("Inter", 8, QFont.Weight.Medium))
        self._dwg_scope_lbl.setStyleSheet("color: #EF4444; margin-left: 22px;")

        opt1_lay.addWidget(self._rb_curr)
        opt1_lay.addWidget(self._dwg_scope_lbl)
        scope_lay.addWidget(opt1_card)

        # Radio Option 2: Date Range
        opt2_card = QFrame()
        opt2_card.setStyleSheet("background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px;")
        opt2_lay = QVBoxLayout(opt2_card)
        opt2_lay.setContentsMargins(12, 10, 12, 10)
        self._rb_date = QRadioButton("Date Range")
        self._scope_grp.addButton(self._rb_date)

        lbl_sub_date = QLabel("Filter review logs and comment revisions within a specified timeframe")
        lbl_sub_date.setFont(QFont("Inter", 8))
        lbl_sub_date.setStyleSheet("color: #64748B; margin-left: 22px;")

        opt2_lay.addWidget(self._rb_date)
        opt2_lay.addWidget(lbl_sub_date)

        self._date_container = QWidget()
        date_lay = QHBoxLayout(self._date_container)
        date_lay.setContentsMargins(22, 6, 0, 4)
        date_lay.setSpacing(12)

        d1_lbl = QLabel("From:")
        d1_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        d1_lbl.setStyleSheet("color: #475569;")
        date_lay.addWidget(d1_lbl)
        self._date_start = QDateEdit(QDate.currentDate().addDays(-30))
        self._date_start.setCalendarPopup(True)
        self._date_start.setFixedHeight(30)
        self._date_start.setStyleSheet("QDateEdit { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 0 6px; font-size: 10px; }")
        date_lay.addWidget(self._date_start)

        d2_lbl = QLabel("To:")
        d2_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        d2_lbl.setStyleSheet("color: #475569;")
        date_lay.addWidget(d2_lbl)
        self._date_end = QDateEdit(QDate.currentDate())
        self._date_end.setCalendarPopup(True)
        self._date_end.setFixedHeight(30)
        self._date_end.setStyleSheet("QDateEdit { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 0 6px; font-size: 10px; }")
        date_lay.addWidget(self._date_end)
        date_lay.addStretch()

        self._date_container.hide()
        opt2_lay.addWidget(self._date_container)
        scope_lay.addWidget(opt2_card)

        # Radio Option 3: All Historical Comments
        opt3_card = QFrame()
        opt3_card.setStyleSheet("background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px;")
        opt3_lay = QVBoxLayout(opt3_card)
        opt3_lay.setContentsMargins(12, 10, 12, 10)
        self._rb_all = QRadioButton("All Historical Comments across Enterprise Account")
        self._scope_grp.addButton(self._rb_all)

        self._hist_scope_lbl = QLabel("Persisted Database: 0 Projects • 0 Drawings • 0 Comments")
        self._hist_scope_lbl.setFont(QFont("Inter", 8))
        self._hist_scope_lbl.setStyleSheet("color: #64748B; margin-left: 22px;")

        opt3_lay.addWidget(self._rb_all)
        opt3_lay.addWidget(self._hist_scope_lbl)
        scope_lay.addWidget(opt3_card)

        self._rb_date.toggled.connect(self._date_container.setVisible)

        # Checkbox Row Options
        lbl_attr = QLabel("Data Attributes to Include")
        lbl_attr.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        lbl_attr.setStyleSheet("color: #64748B; margin-top: 4px;")
        scope_lay.addWidget(lbl_attr)

        attr_row = QHBoxLayout()
        attr_row.setSpacing(12)

        cb1_box = QFrame()
        cb1_box.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;")
        cb1_lay = QVBoxLayout(cb1_box)
        cb1_lay.setContentsMargins(10, 8, 10, 8)
        cb1 = QCheckBox("OCR Confidence Scores")
        cb1.setChecked(True)
        cb1_sub = QLabel("Includes token-level AI probabilities")
        cb1_sub.setFont(QFont("Inter", 7.5))
        cb1_sub.setStyleSheet("color: #64748B; margin-left: 20px;")
        cb1_lay.addWidget(cb1)
        cb1_lay.addWidget(cb1_sub)

        cb2_box = QFrame()
        cb2_box.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;")
        cb2_lay = QVBoxLayout(cb2_box)
        cb2_lay.setContentsMargins(10, 8, 10, 8)
        cb2 = QCheckBox("Audit Trail & Reviewer Notes")
        cb2.setChecked(True)
        cb2_sub = QLabel("Detailed reviewer changes & resolutions")
        cb2_sub.setFont(QFont("Inter", 7.5))
        cb2_sub.setStyleSheet("color: #64748B; margin-left: 20px;")
        cb2_lay.addWidget(cb2)
        cb2_lay.addWidget(cb2_sub)

        cb3_box = QFrame()
        cb3_box.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;")
        cb3_lay = QVBoxLayout(cb3_box)
        cb3_lay.setContentsMargins(10, 8, 10, 8)
        cb3 = QCheckBox("Vector CAD Bounding Boxes")
        cb3.setChecked(True)
        cb3_sub = QLabel("Precise [x,y,w,h] normalized polygons")
        cb3_sub.setFont(QFont("Inter", 7.5))
        cb3_sub.setStyleSheet("color: #64748B; margin-left: 20px;")
        cb3_lay.addWidget(cb3)
        cb3_lay.addWidget(cb3_sub)

        attr_row.addWidget(cb1_box, 1)
        attr_row.addWidget(cb2_box, 1)
        attr_row.addWidget(cb3_box, 1)

        scope_lay.addLayout(attr_row)

        # Export Action Bar Inside Scope Box
        act_row = QHBoxLayout()
        act_row.setSpacing(12)

        self._export_btn = QPushButton("📥 Export Now")
        self._export_btn.setFixedHeight(36)
        self._export_btn.setMinimumWidth(140)
        self._export_btn.setStyleSheet(
            "QPushButton { background: #0284C7; border: none; border-radius: 6px; color: #FFFFFF; font-size: 11px; font-weight: 600; padding: 0 16px; }"
            "QPushButton:hover { background: #0369A1; }"
            "QPushButton:disabled { background: #94A3B8; }"
        )
        self._export_btn.clicked.connect(self._start_export)
        act_row.addWidget(self._export_btn)

        btn_sched = QPushButton("Schedule Automated Export")
        btn_sched.setFixedHeight(34)
        btn_sched.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #0284C7; font-size: 10px; font-weight: 600; }"
            "QPushButton:hover { text-decoration: underline; }"
        )
        act_row.addWidget(btn_sched)

        act_row.addStretch()

        lbl_enc = QLabel("🛡 End-to-End Encrypted Generation")
        lbl_enc.setFont(QFont("Inter", 7.5, QFont.Weight.Medium))
        lbl_enc.setStyleSheet("color: #059669;")
        act_row.addWidget(lbl_enc)

        scope_lay.addLayout(act_row)

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setFixedHeight(6)
        self._prog_bar.setStyleSheet(
            "QProgressBar { background: #E2E8F0; border-radius: 3px; border: none; }"
            "QProgressBar::chunk { background-color: #0284C7; border-radius: 3px; }"
        )
        self._prog_bar.hide()
        scope_lay.addWidget(self._prog_bar)

        self._status_msg = QLabel("")
        self._status_msg.setFont(QFont("Inter", 8.5, QFont.Weight.Medium))
        self._status_msg.setStyleSheet("color: #059669;")
        self._status_msg.hide()
        scope_lay.addWidget(self._status_msg)

        scope_section.addWidget(scope_card)
        root.addLayout(scope_section)

        # ── Export History Card ───────────────────────────────────
        hist_section = QVBoxLayout()
        hist_section.setSpacing(10)

        hist_hdr = QHBoxLayout()
        hist_title = QLabel("● Recent Export History")
        hist_title.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        hist_title.setStyleSheet("color: #0F172A;")

        btn_audit = QPushButton("View Full Audit Log →")
        btn_audit.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #0284C7; font-size: 10px; font-weight: 600; }"
            "QPushButton:hover { text-decoration: underline; }"
        )

        hist_hdr.addWidget(hist_title)
        hist_hdr.addStretch()
        hist_hdr.addWidget(btn_audit)
        hist_section.addLayout(hist_hdr)

        hist_card = _card()
        hist_lay = QVBoxLayout(hist_card)
        hist_lay.setContentsMargins(1, 1, 1, 1)

        self._hist_table = self._build_history_table()
        hist_lay.addWidget(self._hist_table)

        hist_section.addWidget(hist_card)
        root.addLayout(hist_section)

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

    def update_scope_labels(self) -> None:
        """Update scope selection subtext labels with live database counts."""
        if not self._controller or not hasattr(self._controller, "get_export_scope_counts"):
            return
        counts = self._controller.get_export_scope_counts()

        dwg_info = counts.get("drawing", {})
        if dwg_info.get("has_drawing"):
            dwg_name = dwg_info.get("drawing_name", "Drawing")
            cmt_cnt = dwg_info.get("comments_count", 0)
            self._dwg_scope_lbl.setText(f"Active Drawing: {dwg_name}  •  Comments available: {cmt_cnt}")
            self._dwg_scope_lbl.setStyleSheet("color: #0284C7; font-size: 11px; margin-left: 22px;")
        else:
            self._dwg_scope_lbl.setText("No drawing is currently loaded")
            self._dwg_scope_lbl.setStyleSheet("color: #EF4444; font-size: 11px; margin-left: 22px;")

        hist_info = counts.get("all", {})
        p_cnt = hist_info.get("projects_count", 0)
        d_cnt = hist_info.get("drawings_count", 0)
        c_cnt = hist_info.get("comments_count", 0)
        self._hist_scope_lbl.setText(f"Persisted Database: {p_cnt} Projects  •  {d_cnt} Drawings  •  {c_cnt} Total Comments")
        self._hist_scope_lbl.setStyleSheet("color: #64748B; font-size: 11px; margin-left: 22px;")

    def _start_export(self) -> None:
        if self._controller is None:
            QMessageBox.critical(
                self,
                "Export Error",
                "Backend controller is not connected.",
            )
            return

        drawing_id = getattr(self._controller, "current_drawing_id", None) or None
        project_id = getattr(self._controller, "current_project_id", None) or None

        if self._rb_curr.isChecked():
            scope_val = "drawing"
            if not drawing_id:
                QMessageBox.warning(
                    self,
                    "Export Validation",
                    "No drawing is currently loaded.",
                )
                return
        elif self._rb_date.isChecked():
            scope_val = "date_range"
        else:
            scope_val = "all"

        if hasattr(self._controller, "get_export_scope_counts"):
            counts = self._controller.get_export_scope_counts()
            scope_lookup = "drawing" if scope_val == "drawing" else "all"
            avail_comments = counts.get(scope_lookup, {}).get("comments_count", 0)
            if avail_comments == 0 and scope_val != "date_range":
                QMessageBox.warning(
                    self,
                    "Export Warning",
                    "No comments available for the selected export scope.",
                )
                return

        fmt_code, filter_str, ext = self._get_format_details()
        today_str = _date.today().isoformat()

        if scope_val == "drawing":
            drawing_no = "Drawing"
            if self._controller and getattr(self._controller, "current_document", None):
                doc = self._controller.current_document
                if hasattr(doc, "file_name") and doc.file_name:
                    drawing_no = doc.file_name.rsplit(".", 1)[0]
            elif drawing_id and hasattr(self._controller, "drawing_repo"):
                try:
                    dwg = self._controller.drawing_repo.get_drawing_by_id(drawing_id)
                    if dwg and dwg.get("file_name"):
                        fname = dwg["file_name"]
                        drawing_no = fname.rsplit(".", 1)[0]
                except Exception:
                    pass
            default_filename = f"{drawing_no}_Error_Tracker_{today_str}{ext}"
        else:
            default_filename = f"Historical_Error_Tracker_{today_str}{ext}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {self._selected_format} File",
            default_filename,
            filter_str,
        )

        if not file_path:
            return

        out_path = Path(file_path)

        self._export_btn.setEnabled(False)
        self._export_btn.setText("Generating Report...")
        self._prog_bar.show()
        self._prog_bar.setValue(25)

        try:
            contract_no     = self._contract_input.text().strip()
            plant_name      = self._plant_input.text().strip()
            epod_wo_no      = self._epod_input.text().strip()
            designer_name   = self._designer_input.text().strip()
            date_str        = self._date_input.text().strip()
            department_name = self._dept_combo.currentText().strip() if hasattr(self, "_dept_combo") else "Piping Engineering"

            config = ExportConfigDTO(
                output_path=out_path,
                format=fmt_code,
                drawing_id=drawing_id if scope_val == "drawing" else None,
                project_id=project_id if scope_val == "project" else None,
                scope=scope_val,
                contract_no=contract_no,
                plant_name=plant_name,
                epod_wo_no=epod_wo_no,
                designer_name=designer_name,
                date_str=date_str,
                drawing_no=drawing_no if scope_val == "drawing" else None,
                department_name=department_name,
            )

            result = self._controller.export_data(config)
            self._prog_bar.setValue(100)

            if result and getattr(result, "success", False):
                self._export_btn.setText("✓  Exported Successfully!")
                self._status_msg.setText(f"✓ Exported data successfully to {out_path.name}")
                self._status_msg.show()
                self._reload_history_table()
                QTimer.singleShot(
                    2500, lambda: self._export_btn.setText("📥 Export Now")
                )
                QTimer.singleShot(
                    2500, lambda: self._export_btn.setEnabled(True)
                )
                QTimer.singleShot(
                    3000, lambda: self._prog_bar.hide()
                )
            else:
                err_msg = getattr(result, "error_message", "Export failed.") if result else "Export failed."
                self._export_btn.setText("📥 Export Now")
                self._export_btn.setEnabled(True)
                self._prog_bar.hide()
                QMessageBox.warning(
                    self,
                    "Export Error",
                    f"Failed to export data to:\n{out_path}\n\nError: {err_msg}",
                )
        except Exception as e:
            self._export_btn.setText("📥 Export Now")
            self._export_btn.setEnabled(True)
            self._prog_bar.hide()
            QMessageBox.critical(
                self,
                "Export Failed",
                f"An error occurred while generating the export:\n{e}",
            )

    def _build_history_table(self) -> QTableView:
        tbl = QTableView()
        tbl.setAlternatingRowColors(False)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setShowGrid(False)
        tbl.verticalHeader().hide()
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setMinimumHeight(180)
        tbl.setStyleSheet(
            """
            QTableView {
                border: none;
                background-color: #FFFFFF;
                gridline-color: transparent;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #64748B;
                font-weight: 700;
                font-size: 10px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
                padding: 8px 12px;
            }
            QTableView::item {
                border-bottom: 1px solid #F1F5F9;
                padding: 6px 12px;
                color: #0F172A;
                font-size: 11px;
            }
            QTableView::item:selected {
                background-color: #EFF6FF;
                color: #0F172A;
            }
            """
        )

        headers = ["FILE NAME", "FORMAT", "GENERATED DATE", "SIZE"]
        self._hist_model = QStandardItemModel(0, len(headers))
        self._hist_model.setHorizontalHeaderLabels(headers)
        tbl.setModel(self._hist_model)
        tbl.doubleClicked.connect(self._on_history_double_clicked)
        self._history_items_raw: list[dict] = []
        self._reload_history_table()

        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, len(headers)):
            tbl.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        return tbl

    def _on_history_double_clicked(self, index) -> None:
        """Open selected export file or show warning if file is missing."""
        row = index.row()
        if hasattr(self, "_history_items_raw") and 0 <= row < len(self._history_items_raw):
            item = self._history_items_raw[row]
            file_path_str = item.get("file_path")
            if file_path_str:
                file_path = Path(file_path_str)
                if file_path.exists():
                    try:
                        import os
                        os.startfile(str(file_path))
                    except Exception as e:
                        QMessageBox.warning(self, "Open Export File", f"Could not open file:\n{e}")
                else:
                    QMessageBox.warning(
                        self,
                        "File Not Found",
                        f"The exported file could not be found at path:\n{file_path_str}\n\nIt may have been moved or deleted.",
                    )
            else:
                QMessageBox.information(
                    self,
                    "Export History Item",
                    f"Selected export item: {item.get('name', 'Export')}",
                )

    def _reload_history_table(self) -> None:
        """Reload persistent export history rows into the table view."""
        if not hasattr(self, "_hist_model"):
            return
        self._hist_model.removeRows(0, self._hist_model.rowCount())

        history_items = []
        if self._controller and hasattr(self._controller, "get_export_history"):
            history_items = self._controller.get_export_history()

        if not history_items:
            history_items = md.EXPORT_HISTORY

        self._history_items_raw = history_items

        for h in history_items:
            row = [
                QStandardItem(f"📄  {h.get('name') or h.get('file_name', 'Export')}"),
                QStandardItem(h.get("format", "Excel")),
                QStandardItem(h.get("date") or h.get("created_at", "")),
                QStandardItem(h.get("size") or "—"),
            ]
            for item in row:
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
            self._hist_model.appendRow(row)

    def _prepend_history(self, output_path: Path | str, format_name: str, size_bytes: int = 0) -> None:
        self._reload_history_table()

    def reload_data(self) -> None:
        """Auto-refresh Export screen data, scope labels, and history table."""
        self.update_scope_labels()
        self._reload_history_table()
        if self._controller and getattr(self._controller, "current_drawing_id", None):
            cur_dwg = self._controller.get_current_drawing()
            if cur_dwg:
                dwg_dept = cur_dwg.get("department_name")
                if dwg_dept and hasattr(self, "_dept_combo"):
                    idx = self._dept_combo.findText(dwg_dept)
                    if idx != -1 and self._dept_combo.currentIndex() != idx:
                        self._dept_combo.blockSignals(True)
                        self._dept_combo.setCurrentIndex(idx)
                        self._dept_combo.blockSignals(False)

    def reload_comments(self) -> None:
        """Called by MainWindow when comments or drawings are updated."""
        self.reload_data()

    def showEvent(self, event) -> None:
        """Auto-sync department and categories when navigating to Export page."""
        super().showEvent(event)
        self.reload_data()
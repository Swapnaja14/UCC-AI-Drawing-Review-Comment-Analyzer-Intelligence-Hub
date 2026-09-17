"""
export_screen.py — Export screen.

Provides:
    ExportPage(QWidget)
        Responsive, scrollable layout with format selector cards (Excel / JSON / CSV),
        Standard Input metadata fields for the Error Tracker Sheet, scope options,
        progress feedback, and export history table.
"""
from __future__ import annotations
from datetime import date as _date
from pathlib import Path
from typing import Optional, Any

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
                                QLabel, QLineEdit, QComboBox, QPushButton, QRadioButton, QButtonGroup,
                                QProgressBar, QTableView, QHeaderView, QScrollArea,
                                QAbstractItemView, QFileDialog, QMessageBox, QSizePolicy)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PySide6.QtCore import Qt, QTimer

from src.core.dtos.export_dtos import ExportConfigDTO, ExportFormat
from app import mock_data as md


# ── Format card ───────────────────────────────────────────────────────────────

_FORMATS = [
    ("📊", "Excel", ".xlsx", "Error Tracker Multi-Tier Formatted Spreadsheet with Custom Colors", "#4ADE80"),
    ("📜", "JSON",  ".json", "Structured Machine-Readable Object Hierarchy with Metadata",        "#60A5FA"),
    ("📋", "CSV",   ".csv",  "Standard 9-Column Error Tracker Comma-Separated Values",            "#FBBF24"),
]


class _FormatCard(QFrame):
    """Selectable export-format card with rich typography and responsive spacing."""

    def __init__(self, icon: str, name: str, ext: str,
                 desc: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(175)
        self.setMinimumWidth(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False
        self._color    = color

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 30))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(icon_lbl)

        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("background: transparent; color: #F8FAFC;")
        lay.addWidget(name_lbl)

        ext_lbl = QLabel(f" {ext} ")
        ext_lbl.setFont(QFont("Cascadia Code", 11, QFont.Weight.DemiBold))
        ext_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ext_lbl.setStyleSheet(f"""
            background: {color}22;
            color: {color};
            border-radius: 4px;
            padding: 2px 8px;
        """)
        lay.addWidget(ext_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        desc_lbl = QLabel(desc)
        desc_lbl.setFont(QFont("Segoe UI", 12))
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setStyleSheet("background: transparent; color: #94A3B8; padding-top: 4px;")
        lay.addWidget(desc_lbl)

        self._dot = QLabel("● Selected")
        self._dot.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dot.setStyleSheet(f"background: transparent; color: {color}; padding-top: 4px;")
        self._dot.hide()
        lay.addWidget(self._dot)

    def set_selected(self, v: bool) -> None:
        self._selected = v
        if v:
            self.setStyleSheet(
                f"#Card {{ border: 2px solid {self._color};"
                f" border-radius: 10px;"
                f" background-color: {self._color}14; }}"
            )
            self._dot.show()
        else:
            self.setStyleSheet(
                "#Card { border: 1px solid #334155; border-radius: 10px; background-color: #1E222B; }"
                "#Card:hover { border: 1px solid #475569; background-color: #242936; }"
            )
            self._dot.hide()

    def mousePressEvent(self, e) -> None:
        self.set_selected(True)
        super().mousePressEvent(e)


# ── ExportPage ────────────────────────────────────────────────────────────────

class ExportPage(QWidget):
    """
    Responsive, scrollable Export Screen with dedicated Error Tracker fields,
    scope selection, and interactive spreadsheet generator.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller       = controller
        self._selected_format  = "Excel"
        self._format_cards: list[_FormatCard] = []
        self._progress         = 0

        # Outer root layout for the page
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # ── Scroll Area for Full Responsiveness ───────────────────
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #181A20;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #475569;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Container widget inside scroll area
        container = QWidget()
        container.setObjectName("ExportContainer")
        container.setStyleSheet("#ExportContainer { background-color: transparent; }")

        root = QVBoxLayout(container)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(24)

        # ── Section 1: Format Selector ────────────────────────────
        fmt_header_lay = QHBoxLayout()
        fmt_lbl = QLabel("Select Export Format")
        fmt_lbl.setFont(QFont("Segoe UI Variable", 18, QFont.Weight.Bold))
        fmt_lbl.setStyleSheet("color: #F8FAFC;")
        fmt_header_lay.addWidget(fmt_lbl)
        fmt_header_lay.addStretch()
        root.addLayout(fmt_header_lay)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(18)
        for icon, name, ext, desc, color in _FORMATS:
            card = _FormatCard(icon, name, ext, desc, color)
            card.mousePressEvent = self._make_select_handler(card, name)
            self._format_cards.append(card)
            fmt_row.addWidget(card, 1)
        self._format_cards[0].set_selected(True)
        root.addLayout(fmt_row)

        # ── Section 2: Standard Input Fields (Error Tracker) ──────
        meta_card = QFrame()
        meta_card.setObjectName("Card")
        meta_card.setStyleSheet("""
            #Card {
                background-color: #1E222B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        meta_lay = QVBoxLayout(meta_card)
        meta_lay.setContentsMargins(24, 20, 24, 24)
        meta_lay.setSpacing(18)

        meta_hdr_lay = QHBoxLayout()
        meta_title = QLabel("Standard Input Fields (Error Tracker Metadata)")
        meta_title.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        meta_title.setStyleSheet("color: #F8FAFC;")
        meta_hdr_lay.addWidget(meta_title)
        meta_hdr_lay.addStretch()
        
        badge_lbl = QLabel(" 🟧 User Input Fields — Will be written to Error Tracker Sheet ")
        badge_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        badge_lbl.setStyleSheet("""
            background-color: #FFC00022;
            color: #FFC000;
            border: 1px solid #FFC00055;
            border-radius: 6px;
            padding: 4px 10px;
        """)
        meta_hdr_lay.addWidget(badge_lbl)
        meta_lay.addLayout(meta_hdr_lay)

        input_style = """
            QLineEdit {
                background-color: #12141A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
                font-family: 'Segoe UI', Arial;
                min-height: 22px;
            }
            QLineEdit:hover {
                border: 1px solid #475569;
            }
            QLineEdit:focus {
                border: 1.5px solid #38BDF8;
                background-color: #161922;
            }
        """

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(16)

        # Column 0 & 1: Contract # & Plant Name
        c_box = QVBoxLayout()
        c_box.setSpacing(6)
        c_lbl = QLabel("Contract # (Column 2):")
        c_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        c_lbl.setStyleSheet("color: #CBD5E1;")
        self._contract_input = QLineEdit("CTR-2026-01")
        self._contract_input.setStyleSheet(input_style)
        self._contract_input.setPlaceholderText("e.g. CTR-2026-01")
        c_box.addWidget(c_lbl)
        c_box.addWidget(self._contract_input)
        grid.addLayout(c_box, 0, 0)

        p_box = QVBoxLayout()
        p_box.setSpacing(6)
        p_lbl = QLabel("Plant Name (Column 3):")
        p_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        p_lbl.setStyleSheet("color: #CBD5E1;")
        self._plant_input = QLineEdit("Austin Substation")
        self._plant_input.setStyleSheet(input_style)
        self._plant_input.setPlaceholderText("e.g. Austin Substation")
        p_box.addWidget(p_lbl)
        p_box.addWidget(self._plant_input)
        grid.addLayout(p_box, 0, 1)

        # Column 2 & 3: E-Pod WO # & UCC-I Designer
        w_box = QVBoxLayout()
        w_box.setSpacing(6)
        w_lbl = QLabel("E-Pod WO # (Column 4):")
        w_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        w_lbl.setStyleSheet("color: #CBD5E1;")
        self._epod_input = QLineEdit("WO-440192")
        self._epod_input.setStyleSheet(input_style)
        self._epod_input.setPlaceholderText("e.g. WO-440192")
        w_box.addWidget(w_lbl)
        w_box.addWidget(self._epod_input)
        grid.addLayout(w_box, 1, 0)

        d_box = QVBoxLayout()
        d_box.setSpacing(6)
        d_lbl = QLabel("UCC-I Designer (Column 6):")
        d_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        d_lbl.setStyleSheet("color: #CBD5E1;")
        self._designer_input = QLineEdit("Lead Reviewer")
        self._designer_input.setStyleSheet(input_style)
        self._designer_input.setPlaceholderText("e.g. Lead Reviewer")
        d_box.addWidget(d_lbl)
        d_box.addWidget(self._designer_input)
        grid.addLayout(d_box, 1, 1)

        # Row 2 (Cols 0 & 1): Review Date & Engineering Department
        dt_box = QVBoxLayout()
        dt_box.setSpacing(6)
        dt_lbl = QLabel("Review Date (Column 1):")
        dt_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        dt_lbl.setStyleSheet("color: #CBD5E1;")
        self._date_input = QLineEdit(_date.today().strftime("%Y-%m-%d"))
        self._date_input.setStyleSheet(input_style)
        self._date_input.setPlaceholderText("YYYY-MM-DD")
        dt_box.addWidget(dt_lbl)
        dt_box.addWidget(self._date_input)
        grid.addLayout(dt_box, 2, 0)

        dept_box = QVBoxLayout()
        dept_box.setSpacing(6)
        dept_lbl = QLabel("Engineering Department (Column 10):")
        dept_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        dept_lbl.setStyleSheet("color: #CBD5E1;")
        self._dept_combo = QComboBox()
        self._dept_combo.setStyleSheet("""
            QComboBox {
                background-color: #12141A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px 36px 10px 14px;
                font-size: 14px;
                font-family: 'Segoe UI', Arial;
                min-height: 22px;
            }
            QComboBox:hover {
                border-color: #38BDF8;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 32px;
                border: none;
                background: transparent;
            }
            QComboBox::drop-down:hover {
                background-color: rgba(56, 189, 248, 0.15);
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #94A3B8;
                margin-right: 10px;
            }
            QComboBox::down-arrow:hover, QComboBox:hover::down-arrow {
                border-top-color: #38BDF8;
            }
            QComboBox::down-arrow:on {
                border-top: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-bottom: 6px solid #38BDF8;
            }
            QComboBox QAbstractItemView {
                background-color: #1E222B;
                color: #F8FAFC;
                selection-background-color: #0284C7;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        # Populate 7 official UCC engineering departments
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

        # Row 3 (Col 0): Auto-read program fields explanation
        info_box = QVBoxLayout()
        info_box.setSpacing(6)
        info_lbl = QLabel("Auto-Read Program Fields (Cols 7-10):")
        info_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        info_lbl.setStyleSheet("color: #92D050;")
        info_val = QLabel("Drawing #, Title, Commentary OCR, Error Classification, and Department are auto-read from database.")
        info_val.setFont(QFont("Segoe UI", 12))
        info_val.setWordWrap(True)
        info_val.setStyleSheet("color: #94A3B8; padding-top: 4px;")
        info_box.addWidget(info_lbl)
        info_box.addWidget(info_val)
        grid.addLayout(info_box, 3, 0, 1, 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        meta_lay.addLayout(grid)
        root.addWidget(meta_card)

        # ── Section 2.5: Error Tracker Categories (Column 9: Category of Error) ──
        cat_card = self._build_category_card()
        root.addWidget(cat_card)
        self._dept_combo.currentTextChanged.connect(self._on_department_changed)

        # ── Section 3: Scope Options ──────────────────────────────
        scope_card = QFrame()
        scope_card.setObjectName("Card")
        scope_card.setStyleSheet("""
            #Card {
                background-color: #1E222B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        scope_lay = QVBoxLayout(scope_card)
        scope_lay.setContentsMargins(24, 18, 24, 18)
        scope_lay.setSpacing(12)

        scope_title = QLabel("Export Scope")
        scope_title.setFont(QFont("Segoe UI Variable", 15, QFont.Weight.Bold))
        scope_title.setStyleSheet("color: #F8FAFC;")
        scope_lay.addWidget(scope_title)

        scope_btn_style = """
            QRadioButton {
                color: #CBD5E1;
                font-size: 14px;
                font-family: 'Segoe UI';
                spacing: 10px;
                min-height: 28px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid #64748B;
                background-color: #12141A;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #38BDF8;
                background-color: #38BDF8;
            }
            QRadioButton:hover {
                color: #F8FAFC;
            }
        """

        self._scope_grp = QButtonGroup(self)
        for label in ["Current Loaded Drawing", "Current Project (All Drawings)", "All Historical Comments"]:
            rb = QRadioButton(label)
            rb.setStyleSheet(scope_btn_style)
            self._scope_grp.addButton(rb)
            scope_lay.addWidget(rb)
        self._scope_grp.buttons()[0].setChecked(True)
        root.addWidget(scope_card)

        # ── Section 4: Export Action Button & Progress ────────────
        act_box = QVBoxLayout()
        act_box.setSpacing(12)

        act_row = QHBoxLayout()
        act_row.setSpacing(20)

        self._export_btn = QPushButton("  ↑  Export Error Tracker Sheet")
        self._export_btn.setFont(QFont("Segoe UI Variable", 15, QFont.Weight.Bold))
        self._export_btn.setFixedHeight(50)
        self._export_btn.setMinimumWidth(320)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: #FFFFFF;
                border-radius: 8px;
                padding: 0 28px;
                border: 1px solid #38BDF8;
            }
            QPushButton:hover {
                background-color: #0369A1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #64748B;
                border: none;
            }
        """)
        self._export_btn.clicked.connect(self._start_export)
        act_row.addWidget(self._export_btn)
        act_row.addStretch()
        act_box.addLayout(act_row)

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setFixedHeight(10)
        self._prog_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E222B;
                border: 1px solid #334155;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #38BDF8;
                border-radius: 4px;
            }
        """)
        self._prog_bar.hide()
        act_box.addWidget(self._prog_bar)
        root.addLayout(act_box)

        # ── Section 5: Export History Table ───────────────────────
        hist_card = QFrame()
        hist_card.setObjectName("Card")
        hist_card.setStyleSheet("""
            #Card {
                background-color: #1E222B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        hist_lay = QVBoxLayout(hist_card)
        hist_lay.setContentsMargins(0, 0, 0, 0)
        hist_lay.setSpacing(0)

        hist_hdr = QLabel("  Export History")
        hist_hdr.setFixedHeight(48)
        hist_hdr.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        hist_hdr.setStyleSheet(
            "padding-left: 20px; color: #F8FAFC; border-bottom: 1px solid #334155;"
        )
        hist_lay.addWidget(hist_hdr)

        self._hist_table = self._build_history_table()
        hist_lay.addWidget(self._hist_table)
        root.addWidget(hist_card)

        # Set container inside scroll area and add scroll area to page
        scroll.setWidget(container)
        page_layout.addWidget(scroll)

        # Initialise error tracker categories
        self._refresh_categories()

    # ── Helpers ───────────────────────────────────────────────────

    def _make_select_handler(self, card: _FormatCard, name: str):
        def handler(e):
            for c in self._format_cards:
                c.set_selected(False)
            card.set_selected(True)
            self._selected_format = name
        return handler

    def _get_format_details(self) -> tuple[str, str, str]:
        """Returns (format_code, file_filter, file_extension)."""
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

        drawing_no = "Error_Tracker"
        if self._controller and getattr(self._controller, "current_document", None):
            doc = self._controller.current_document
            if hasattr(doc, "file_name") and doc.file_name:
                drawing_no = doc.file_name.rsplit(".", 1)[0]

        default_filename = f"{drawing_no}_Error_Tracker_{today_str}{ext}"

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

        self._export_btn.setEnabled(False)
        self._prog_bar.show()
        self._prog_bar.setValue(50)

        try:
            scope_text = self._scope_grp.checkedButton().text()
            drawing_id = getattr(self._controller, "current_drawing_id", None) or None
            
            if scope_text == "All Historical Comments":
                scope_val = "all"
                drawing_id = None
            elif scope_text == "Current Project (All Drawings)":
                scope_val = "project"
                drawing_id = None
            else:
                scope_val = "drawing"
            
            # Read standard input metadata fields
            contract_no     = self._contract_input.text().strip()
            plant_name      = self._plant_input.text().strip()
            epod_wo_no      = self._epod_input.text().strip()
            designer_name   = self._designer_input.text().strip()
            date_str        = self._date_input.text().strip()
            department_name = self._dept_combo.currentText().strip() if hasattr(self, "_dept_combo") else "Piping Engineering"

            config = ExportConfigDTO(
                output_path=out_path,
                format=fmt_code,
                drawing_id=drawing_id,
                scope=scope_val,
                contract_no=contract_no,
                plant_name=plant_name,
                epod_wo_no=epod_wo_no,
                designer_name=designer_name,
                date_str=date_str,
                drawing_no=drawing_no,
                department_name=department_name,
            )

            result = self._controller.export_data(config)
            self._prog_bar.setValue(100)

            if result and getattr(result, "success", False):
                self._export_btn.setText("✓  Exported Successfully!")
                self._prepend_history(
                    result.output_path,
                    self._selected_format,
                    getattr(result, "file_size_bytes", 0),
                )
                QTimer.singleShot(
                    2500, lambda: self._export_btn.setText("  ↑  Export Error Tracker Sheet")
                )
                QTimer.singleShot(
                    2500, lambda: self._export_btn.setEnabled(True)
                )
                self._prog_bar.hide()

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Successfully generated Error Tracker Sheet with {result.total_rows} row(s) to:\n{result.output_path}",
                )
            else:
                err_msg = getattr(result, "error_message", "") if result else "Unknown error"
                self._export_btn.setText("  ↑  Export Error Tracker Sheet")
                self._export_btn.setEnabled(True)
                self._prog_bar.hide()
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Failed to export data to:\n{out_path}\n\nError: {err_msg}",
                )
        except Exception as e:
            self._export_btn.setText("  ↑  Export Error Tracker Sheet")
            self._export_btn.setEnabled(True)
            self._prog_bar.hide()
            QMessageBox.critical(
                self,
                "Export Failed",
                f"An error occurred during export:\n{str(e)}",
            )

    def _build_history_table(self) -> QTableView:
        table = QTableView()
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setMinimumHeight(240)
        table.setStyleSheet("""
            QTableView {
                background-color: #12141A;
                alternate-background-color: #181B22;
                border: none;
                gridline-color: #334155;
            }
            QTableView::item {
                padding: 10px 16px;
                color: #E2E8F0;
                font-size: 13px;
                border-bottom: 1px solid #1E222B;
            }
            QTableView::item:selected {
                background-color: #0284C722;
                color: #38BDF8;
            }
            QHeaderView::section {
                background-color: #181B22;
                color: #94A3B8;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 12px;
                border: none;
                border-bottom: 1px solid #334155;
            }
        """)

        self._hist_model = QStandardItemModel(0, 4)
        self._hist_model.setHorizontalHeaderLabels(
            ["FILE NAME", "FORMAT", "DATE", "SIZE"]
        )
        for h in md.EXPORT_HISTORY:
            row = [
                QStandardItem(h["name"]),
                QStandardItem(h["format"]),
                QStandardItem(h["date"]),
                QStandardItem(h["size"]),
            ]
            row[0].setFont(QFont("Cascadia Code", 12))
            for item in row:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
            self._hist_model.appendRow(row)

        table.setModel(self._hist_model)
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _prepend_history(self, output_path: Path | str, format_name: str, size_bytes: int = 0) -> None:
        today = _date.today().isoformat()
        file_name = Path(output_path).name
        size_str = self._format_size(size_bytes) if size_bytes > 0 else "—"
        row = [
            QStandardItem(file_name),
            QStandardItem(format_name),
            QStandardItem(today),
            QStandardItem(size_str),
        ]
        row[0].setFont(QFont("Cascadia Code", 12))
        for item in row:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            item.setForeground(QColor("#4ADE80"))
        self._hist_model.insertRow(0, row)

    # ── Section 2.5: Error Tracker Category Editor ────────────────

    def _build_category_card(self) -> QFrame:
        """Build the dedicated Error Tracker Category Editor card (Column 9)."""
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet("""
            #Card {
                background-color: #1E222B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(16)

        # Header Row
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("Error Tracker Categories (Column 9: Category of Error)")
        title.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #F8FAFC;")
        title_box.addWidget(title)

        desc = QLabel(
            "Configure error categories written to Column 9 of the Error Tracker spreadsheet. "
            "Categories added here are scoped specifically to this engineering department so other departments remain clean."
        )
        desc.setFont(QFont("Segoe UI", 12))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94A3B8;")
        title_box.addWidget(desc)
        hdr.addLayout(title_box, 1)

        self._cat_dept_badge = QLabel("📁 Piping Engineering")
        self._cat_dept_badge.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._cat_dept_badge.setStyleSheet("""
            background-color: #0284C722;
            color: #38BDF8;
            border: 1px solid #38BDF855;
            border-radius: 6px;
            padding: 6px 14px;
        """)
        hdr.addWidget(self._cat_dept_badge, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(hdr)

        # Active Categories Section
        self._active_cat_header = QLabel("Active Error Categories (Piping Engineering):")
        self._active_cat_header.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self._active_cat_header.setStyleSheet("color: #E2E8F0; margin-top: 4px;")
        lay.addWidget(self._active_cat_header)

        cats_scroll = QScrollArea()
        cats_scroll.setWidgetResizable(True)
        cats_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cats_scroll.setStyleSheet("""
            QScrollArea {
                background: #12141A;
                border: 1px solid #282D37;
                border-radius: 8px;
            }
        """)
        cats_scroll.setFixedHeight(145)

        self._cats_container = QWidget()
        self._cats_container.setStyleSheet("background: transparent;")
        self._cats_grid = QGridLayout(self._cats_container)
        self._cats_grid.setContentsMargins(12, 12, 12, 12)
        self._cats_grid.setHorizontalSpacing(10)
        self._cats_grid.setVerticalSpacing(8)
        cats_scroll.setWidget(self._cats_container)
        lay.addWidget(cats_scroll)

        # Smart Suggestions Section (Clickable Chips)
        sugg_box = QVBoxLayout()
        sugg_box.setSpacing(8)

        sugg_hdr_lay = QHBoxLayout()
        sugg_title = QLabel("💡 Smart Suggestions (Click to Add to Department):")
        sugg_title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        sugg_title.setStyleSheet("color: #FBBF24;")
        sugg_hdr_lay.addWidget(sugg_title)
        sugg_hdr_lay.addStretch()

        self._sugg_notice = QLabel("1-click discipline recommendations & historical entries")
        self._sugg_notice.setFont(QFont("Segoe UI", 11))
        self._sugg_notice.setStyleSheet("color: #64748B;")
        sugg_hdr_lay.addWidget(self._sugg_notice)
        sugg_box.addLayout(sugg_hdr_lay)

        sugg_scroll = QScrollArea()
        sugg_scroll.setWidgetResizable(True)
        sugg_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sugg_scroll.setFixedHeight(46)
        sugg_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sugg_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._sugg_container = QWidget()
        self._sugg_container.setStyleSheet("background: transparent;")
        self._sugg_layout = QHBoxLayout(self._sugg_container)
        self._sugg_layout.setContentsMargins(0, 2, 0, 2)
        self._sugg_layout.setSpacing(8)
        self._sugg_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        sugg_scroll.setWidget(self._sugg_container)
        sugg_box.addWidget(sugg_scroll)
        lay.addLayout(sugg_box)

        # Quick Add Custom Category Row
        add_box = QVBoxLayout()
        add_box.setSpacing(6)
        add_lbl = QLabel("Add New Custom Error Category & Trigger Keywords:")
        add_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        add_lbl.setStyleSheet("color: #CBD5E1;")
        add_box.addWidget(add_lbl)

        add_row = QHBoxLayout()
        add_row.setSpacing(10)

        input_style = """
            QLineEdit {
                background-color: #12141A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
                font-family: 'Segoe UI', Arial;
                min-height: 20px;
            }
            QLineEdit:hover { border: 1px solid #475569; }
            QLineEdit:focus { border: 1.5px solid #38BDF8; background-color: #161922; }
        """
        self._new_cat_input = QLineEdit()
        self._new_cat_input.setStyleSheet(input_style)
        self._new_cat_input.setPlaceholderText("Category Name (e.g. Tie-in Flange Rating)...")
        self._new_cat_input.returnPressed.connect(self._on_add_custom_category)
        add_row.addWidget(self._new_cat_input, 4)

        self._new_cat_keywords_input = QLineEdit()
        self._new_cat_keywords_input.setStyleSheet(input_style)
        self._new_cat_keywords_input.setPlaceholderText("Trigger Keywords / Phrases (e.g. flange rating, class 150, class 300)...")
        self._new_cat_keywords_input.returnPressed.connect(self._on_add_custom_category)
        add_row.addWidget(self._new_cat_keywords_input, 5)

        self._add_cat_btn = QPushButton("  ➕  Add Category to Piping Engineering")
        self._add_cat_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._add_cat_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                min-height: 20px;
            }
            QPushButton:hover { background-color: #0369A1; }
            QPushButton:pressed { background-color: #075985; }
        """)
        self._add_cat_btn.clicked.connect(self._on_add_custom_category)
        add_row.addWidget(self._add_cat_btn)
        add_box.addLayout(add_row)

        kw_help_lbl = QLabel("💡 Trigger Keywords: Comma-separated phrases from Drawing Commentary (Column 9) that AI & rules use to identify this Category (Column 10).")
        kw_help_lbl.setFont(QFont("Segoe UI", 11))
        kw_help_lbl.setStyleSheet("color: #64748B; padding-left: 2px;")
        add_box.addWidget(kw_help_lbl)

        lay.addLayout(add_box)

        # Status / Feedback label
        self._cat_status_lbl = QLabel("")
        self._cat_status_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self._cat_status_lbl.setStyleSheet("color: #4ADE80; padding: 2px 4px;")
        self._cat_status_lbl.hide()
        lay.addWidget(self._cat_status_lbl)

        return card

    def _refresh_categories(self) -> None:
        """Populate active categories and smart suggestions for the currently selected department."""
        if not hasattr(self, "_cats_grid") or not hasattr(self, "_sugg_layout"):
            return

        dept_name = self._dept_combo.currentText().strip() if hasattr(self, "_dept_combo") else "Piping Engineering"

        # Update badge and labels
        self._cat_dept_badge.setText(f"📁 {dept_name}")
        self._active_cat_header.setText(f"Active Error Categories for {dept_name}:")
        self._new_cat_input.setPlaceholderText(f"Category Name for {dept_name} (e.g. Tie-in Flange Rating)...")
        if hasattr(self, "_new_cat_keywords_input"):
            self._new_cat_keywords_input.setPlaceholderText("Trigger Keywords / Phrases (e.g. flange rating, class 150, class 300)...")
        self._add_cat_btn.setText(f"  ➕  Add Category to {dept_name}")

        # Clear existing items in cats_grid
        while self._cats_grid.count():
            item = self._cats_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Clear existing items in sugg_layout
        while self._sugg_layout.count():
            item = self._sugg_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Query categories from controller
        cats: list[dict[str, Any]] = []
        if self._controller:
            try:
                cats = self._controller.get_categories_for_department(dept_name)
            except Exception:
                cats = []

        # Fallback to default categories if empty
        if not cats:
            cats = [{"name": c, "department_name": None} for c in md.CATEGORIES]

        # Populate active categories grid (4 columns)
        COLS = 4
        for idx, cat in enumerate(cats):
            cname = cat.get("name", "")
            cat_dept = cat.get("department_name")
            kw_str = cat.get("keywords") or ""
            is_custom = bool(cat_dept and cat_dept == dept_name)

            badge = QFrame()
            badge.setFixedHeight(34)
            b_lay = QHBoxLayout(badge)
            b_lay.setContentsMargins(10, 4, 10, 4)
            b_lay.setSpacing(8)

            if is_custom:
                badge.setStyleSheet("""
                    QFrame {
                        background-color: #0284C71A;
                        border: 1px solid #38BDF866;
                        border-radius: 6px;
                    }
                """)
                tag_lbl = QLabel(f"🏷  {cname}")
                tag_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
                tag_lbl.setStyleSheet("color: #38BDF8; background: transparent;")
                if kw_str:
                    badge.setToolTip(f"Category: {cname}\nTrigger Keywords: {kw_str}")
                    tag_lbl.setToolTip(f"Category: {cname}\nTrigger Keywords: {kw_str}")
                else:
                    badge.setToolTip(f"Category: {cname}\n(No custom trigger keywords)")
                    tag_lbl.setToolTip(f"Category: {cname}\n(No custom trigger keywords)")
                b_lay.addWidget(tag_lbl)
                b_lay.addStretch()

                del_btn = QPushButton("✕")
                del_btn.setToolTip(f"Delete '{cname}' from {dept_name}")
                del_btn.setFixedSize(18, 18)
                del_btn.setStyleSheet("""
                    QPushButton {
                        color: #94A3B8;
                        background: transparent;
                        border: none;
                        font-weight: bold;
                        font-size: 11px;
                        border-radius: 9px;
                    }
                    QPushButton:hover {
                        color: #EF4444;
                        background-color: #EF444422;
                    }
                """)
                del_btn.clicked.connect(lambda _, name=cname: self._on_delete_custom_category(name))
                b_lay.addWidget(del_btn)
            else:
                badge.setStyleSheet("""
                    QFrame {
                        background-color: #1E222B;
                        border: 1px solid #334155;
                        border-radius: 6px;
                    }
                """)
                tag_lbl = QLabel(cname)
                tag_lbl.setFont(QFont("Segoe UI", 11))
                tag_lbl.setStyleSheet("color: #E2E8F0; background: transparent;")
                if kw_str:
                    badge.setToolTip(f"Standard Category: {cname}\nTrigger Keywords: {kw_str}")
                    tag_lbl.setToolTip(f"Standard Category: {cname}\nTrigger Keywords: {kw_str}")
                else:
                    badge.setToolTip(f"Standard Category: {cname}")
                    tag_lbl.setToolTip(f"Standard Category: {cname}")
                b_lay.addWidget(tag_lbl)
                b_lay.addStretch()

                lock_lbl = QLabel("🔒")
                lock_lbl.setToolTip("Universal Standard Category")
                lock_lbl.setFont(QFont("Segoe UI Emoji", 9))
                lock_lbl.setStyleSheet("color: #64748B; background: transparent;")
                b_lay.addWidget(lock_lbl)

            row = idx // COLS
            col = idx % COLS
            self._cats_grid.addWidget(badge, row, col)

        # Populate Smart Suggestions
        active_names = {c.get("name", "").lower().strip() for c in cats}
        suggestions: list[str] = []
        if self._controller:
            try:
                suggestions = self._controller.get_category_suggestions(dept_name)
            except Exception:
                suggestions = []

        # Filter out already active ones
        available_suggestions = [s for s in suggestions if s.lower().strip() not in active_names]

        if available_suggestions:
            for sugg in available_suggestions:
                sugg_kw = ""
                if self._controller and hasattr(self._controller, "category_repo"):
                    sugg_kw = self._controller.category_repo.get_suggestion_keywords(sugg)
                tooltip_txt = f"Click to add '{sugg}' to {dept_name}"
                if sugg_kw:
                    tooltip_txt += f"\nPreconfigured Triggers: {sugg_kw}"

                sugg_btn = QPushButton(f"+  {sugg}")
                sugg_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
                sugg_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #161922;
                        color: #38BDF8;
                        border: 1px dashed #38BDF877;
                        border-radius: 14px;
                        padding: 4px 12px;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #0284C733;
                        border: 1px solid #38BDF8;
                        color: #F8FAFC;
                    }
                    QPushButton:pressed {
                        background-color: #0284C7;
                        color: #FFFFFF;
                    }
                """)
                sugg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                sugg_btn.setToolTip(tooltip_txt)
                sugg_btn.clicked.connect(lambda _, s=sugg: self._on_suggestion_clicked(s))
                self._sugg_layout.addWidget(sugg_btn)
            self._sugg_layout.addStretch()
        else:
            all_active = QLabel("✓ All recommended suggestions for this department are active.")
            all_active.setFont(QFont("Segoe UI", 11))
            all_active.setStyleSheet("color: #4ADE80; font-style: italic; padding: 4px;")
            self._sugg_layout.addWidget(all_active)
            self._sugg_layout.addStretch()

    def _on_department_changed(self, dept_name: str) -> None:
        """Handle department dropdown change by updating category list and suggestions."""
        self._refresh_categories()

    def _on_suggestion_clicked(self, suggestion: str) -> None:
        """Add a suggested category with 1 click to the current department with predefined trigger keywords."""
        dept_name = self._dept_combo.currentText().strip() if hasattr(self, "_dept_combo") else "Piping Engineering"
        keywords = ""
        if self._controller and hasattr(self._controller, "category_repo"):
            keywords = self._controller.category_repo.get_suggestion_keywords(suggestion)
        if self._controller:
            self._controller.add_category(name=suggestion, department_name=dept_name, keywords=keywords)
            msg = f"✓ Added '{suggestion}' to {dept_name} error categories"
            if keywords:
                msg += f" (with triggers: {keywords[:35]}...)"
            self._show_status_message(msg)
            self._refresh_categories()

    def _on_add_custom_category(self) -> None:
        """Add custom category and trigger keywords typed into the input fields."""
        name = self._new_cat_input.text().strip()
        if not name:
            return
        keywords = self._new_cat_keywords_input.text().strip() if hasattr(self, "_new_cat_keywords_input") else ""
        dept_name = self._dept_combo.currentText().strip() if hasattr(self, "_dept_combo") else "Piping Engineering"
        if self._controller:
            self._controller.add_category(name=name, department_name=dept_name, keywords=keywords)
            self._new_cat_input.clear()
            if hasattr(self, "_new_cat_keywords_input"):
                self._new_cat_keywords_input.clear()
            msg = f"✓ Added '{name}' to {dept_name} error categories"
            if keywords:
                msg += f" (triggers: {keywords})"
            self._show_status_message(msg)
            self._refresh_categories()
        else:
            QMessageBox.warning(self, "Controller Not Connected", "Database controller is not connected.")

    def _on_delete_custom_category(self, cat_name: str) -> None:
        """Delete a custom category from the current department."""
        dept_name = self._dept_combo.currentText().strip() if hasattr(self, "_dept_combo") else "Piping Engineering"
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to remove custom error category '{cat_name}' from {dept_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes and self._controller:
            ok = self._controller.delete_category(name=cat_name, department_name=dept_name)
            if ok:
                self._show_status_message(f"Removed '{cat_name}' from {dept_name}")
                self._refresh_categories()
            else:
                QMessageBox.warning(self, "Delete Failed", f"Could not delete category '{cat_name}'.")

    def _show_status_message(self, msg: str) -> None:
        """Display a brief confirmation toast message."""
        self._cat_status_lbl.setText(msg)
        self._cat_status_lbl.show()
        QTimer.singleShot(3500, self._cat_status_lbl.hide)

    def reload_data(self) -> None:
        """Auto-refresh Export screen data, auto-select drawing department, and refresh categories."""
        if self._controller and self._controller.current_drawing_id:
            cur_dwg = self._controller.get_current_drawing()
            if cur_dwg:
                dwg_dept = cur_dwg.get("department_name")
                if dwg_dept and hasattr(self, "_dept_combo"):
                    idx = self._dept_combo.findText(dwg_dept)
                    if idx != -1 and self._dept_combo.currentIndex() != idx:
                        self._dept_combo.blockSignals(True)
                        self._dept_combo.setCurrentIndex(idx)
                        self._dept_combo.blockSignals(False)
        self._refresh_categories()

    def reload_comments(self) -> None:
        """Called by MainWindow when comments or drawings are updated."""
        self.reload_data()

    def showEvent(self, event) -> None:
        """Auto-sync department and categories when navigating to Export page."""
        super().showEvent(event)
        self.reload_data()


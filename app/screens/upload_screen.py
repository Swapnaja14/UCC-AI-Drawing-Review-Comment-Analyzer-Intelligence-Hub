"""
upload_screen.py — Superior Dual Single & Batch/Zip Upload Screen for Engineering Drawings.

Provides:
    UploadPage(QWidget)
        Dual side-by-side flex card layout supporting:
        - Mode 1: BATCH / ZIP UPLOAD (multiple PDFs & .ZIP archives with path traversal safety and zip inspection)
        - Mode 2: SINGLE FILE UPLOAD (individual PDF drawing review)
        - Independent Engineering Department selectors for each upload card.
        - Independent Process buttons inside each card for completely segregated workflow execution.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QFrame,
    QToolButton, QSizePolicy, QMenu, QComboBox,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon, QColor

from app.components.upload_widget import DropZone
from app.components.dialogs import open_pdf_file, open_multiple_pdf_or_zip_files
from src.infrastructure.logging.logger import get_logger

try:
    import qtawesome as qta
    _HAS_QTA = True
except ImportError:
    _HAS_QTA = False

logger = get_logger("UploadScreen")


class UploadPage(QWidget):
    """
    Dual Single & Batch/Zip Drawing Upload Screen with Isolated Options, Dropdowns & Buttons.

    Signals
    -------
    open_viewer_requested : Signal()
        Emitted when user completes processing and requests to view drawings.
    """

    open_viewer_requested = Signal()

    MODE_NONE = "NONE"
    MODE_SINGLE = "SINGLE"
    MODE_BATCH = "BATCH"

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._controller = controller
        
        # State: Single file mode
        self._single_filepath: str | None = None
        
        # State: Batch mode (files or zip archives)
        self._batch_filepaths: List[str] = []

        # Main Layout
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 20, 30, 30)
        root.setSpacing(16)

        # ── 1. Page Title & Action Header Card ─────────────────────────────────────
        header_card = QFrame()
        header_card.setObjectName("Card")
        header_card.setFixedHeight(64)
        header_lay = QHBoxLayout(header_card)
        header_lay.setContentsMargins(20, 10, 20, 10)
        header_lay.setSpacing(16)

        title_lbl = QLabel("UPLOAD DRAWINGS")
        title_lbl.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #F8FAFC; letter-spacing: 0.5px;")
        header_lay.addWidget(title_lbl)

        header_lay.addStretch()

        self._recent_btn = QPushButton("Recent Files ▾")
        self._recent_btn.setObjectName("GhostBtn")
        self._recent_btn.setFixedHeight(36)
        self._recent_btn.clicked.connect(self._show_recent)
        header_lay.addWidget(self._recent_btn)

        root.addWidget(header_card)

        # Dropdown Style definition for consistency
        dept_combo_style = (
            "QComboBox {"
            "    background-color: #1A1C23;"
            "    border: 1px solid #333742;"
            "    border-radius: 6px;"
            "    padding: 4px 10px;"
            "    color: #F8FAFC;"
            "    font-size: 12px;"
            "}"
            "QComboBox::drop-down {"
            "    subcontrol-origin: padding;"
            "    subcontrol-position: top right;"
            "    width: 24px;"
            "    border-left-width: 0px;"
            "}"
            "QComboBox QAbstractItemView {"
            "    background-color: #252830;"
            "    color: #F2F3F5;"
            "    selection-background-color: #3E9BFF;"
            "    border: 1px solid #333742;"
            "}"
        )

        # ── 2. Side-by-side Flex Layout (Horizontal Container) ─────────────────────
        flex_container = QHBoxLayout()
        flex_container.setSpacing(20)

        # ════════════════════════════════════════════════════════════════════════════
        # LEFT FLEX COLUMN: Single PDF File Upload Card
        # ════════════════════════════════════════════════════════════════════════════
        self._single_card = QFrame()
        self._single_card.setObjectName("Card")
        self._update_card_style(self._single_card, active=False, accent_color="#3E9BFF")
        
        single_lay = QVBoxLayout(self._single_card)
        single_lay.setContentsMargins(20, 20, 20, 20)
        single_lay.setSpacing(12)

        # Single Header Row
        s_top = QHBoxLayout()
        s_header = QLabel("📄 SINGLE FILE UPLOAD")
        s_header.setFont(QFont("Segoe UI Variable", 14, QFont.Weight.Bold))
        s_header.setStyleSheet("color: #3E9BFF;")
        s_top.addWidget(s_header)

        self._single_badge = QLabel("Mode 2")
        self._single_badge.setStyleSheet("background: #1E293B; color: #3E9BFF; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        s_top.addWidget(self._single_badge, 0, Qt.AlignmentFlag.AlignRight)
        single_lay.addLayout(s_top)

        s_sub = QLabel("Upload and process one PDF engineering drawing individually")
        s_sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        single_lay.addWidget(s_sub)

        # Single Mode Department Selector Dropdown
        s_dept_lay = QHBoxLayout()
        s_dept_lbl = QLabel("Engineering Dept *")
        s_dept_lbl.setFont(QFont("Segoe UI Variable", 11, QFont.Weight.DemiBold))
        s_dept_lbl.setStyleSheet("color: #94A3B8;")
        s_dept_lay.addWidget(s_dept_lbl)

        self._single_dept_combo = QComboBox()
        self._single_dept_combo.setFixedHeight(34)
        self._single_dept_combo.setStyleSheet(dept_combo_style)
        self._single_dept_combo.currentIndexChanged.connect(self._validate_single_form)
        s_dept_lay.addWidget(self._single_dept_combo, 1)
        single_lay.addLayout(s_dept_lay)

        # Drop Zone for Single PDF
        self._single_drop = DropZone(allow_zips=False)
        self._single_drop.file_dropped.connect(self._on_single_file_selected)

        s_drop_lay = QVBoxLayout(self._single_drop)
        s_drop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_drop_lay.setSpacing(8)

        s_icon = QLabel("☁")
        s_icon.setFont(QFont("Segoe UI", 34))
        s_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_icon.setStyleSheet("color: #3E9BFF;")
        s_drop_lay.addWidget(s_icon)

        s_instr = QLabel("Drag & drop a single PDF here")
        s_instr.setFont(QFont("Segoe UI Variable", 13, QFont.Weight.DemiBold))
        s_instr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s_instr.setStyleSheet("color: #F2F3F5;")
        s_drop_lay.addWidget(s_instr)

        s_browse = QPushButton("  Browse PDF File")
        s_browse.setObjectName("PrimaryBtn")
        s_browse.setFixedHeight(34)
        s_browse.setFixedWidth(170)
        s_browse.clicked.connect(self._browse_single)
        s_drop_lay.addWidget(s_browse, 0, Qt.AlignmentFlag.AlignCenter)

        single_lay.addWidget(self._single_drop, 1)

        # Selected Single File Details Card
        self._single_file_card = QFrame()
        self._single_file_card.setStyleSheet("background: #262932; border-radius: 8px; padding: 6px;")
        self._single_file_card.hide()

        sfc_lay = QHBoxLayout(self._single_file_card)
        sfc_lay.setContentsMargins(12, 8, 12, 8)
        sfc_lay.setSpacing(10)

        s_ficon = QLabel("📄")
        s_ficon.setFont(QFont("Segoe UI", 18))
        sfc_lay.addWidget(s_ficon)

        s_meta = QVBoxLayout()
        self._single_fname = QLabel("filename.pdf")
        self._single_fname.setFont(QFont("Cascadia Code", 12))
        self._single_fname.setStyleSheet("color: #F8FAFC;")
        s_meta.addWidget(self._single_fname)
        self._single_fmeta = QLabel("— MB")
        self._single_fmeta.setStyleSheet("color: #94A3B8; font-size: 11px;")
        s_meta.addWidget(self._single_fmeta)
        sfc_lay.addLayout(s_meta, 1)

        s_remove = QToolButton()
        s_remove.setText("✕")
        s_remove.setToolTip("Remove file")
        s_remove.setStyleSheet("color: #F87171; background: transparent; font-weight: bold;")
        s_remove.clicked.connect(self._clear_single_file)
        sfc_lay.addWidget(s_remove)

        single_lay.addWidget(self._single_file_card)

        # Status & Progress for Single File
        self._single_status_lbl = QLabel("")
        self._single_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._single_status_lbl.setFont(QFont("Segoe UI", 11))
        self._single_status_lbl.setStyleSheet("color: #3E9BFF;")
        self._single_status_lbl.hide()
        single_lay.addWidget(self._single_status_lbl)

        self._single_prog = QProgressBar()
        self._single_prog.setRange(0, 100)
        self._single_prog.setValue(0)
        self._single_prog.setFixedHeight(6)
        self._single_prog.hide()
        single_lay.addWidget(self._single_prog)

        # Single Dedicated Process Button
        self._single_process_btn = QPushButton("  Process Single Drawing")
        self._single_process_btn.setObjectName("PrimaryBtn")
        self._single_process_btn.setFixedHeight(42)
        self._single_process_btn.setFont(QFont("Segoe UI Variable", 12, QFont.Weight.Bold))
        self._single_process_btn.setEnabled(False)
        self._single_process_btn.clicked.connect(self._start_single_workflow)
        single_lay.addWidget(self._single_process_btn)

        flex_container.addWidget(self._single_card, 1)

        # ════════════════════════════════════════════════════════════════════════════
        # RIGHT FLEX COLUMN: Multiple Files & Zipped Folders Batch Upload Card
        # ════════════════════════════════════════════════════════════════════════════
        self._batch_card = QFrame()
        self._batch_card.setObjectName("Card")
        self._update_card_style(self._batch_card, active=False, accent_color="#8B9CFF")
        
        batch_lay = QVBoxLayout(self._batch_card)
        batch_lay.setContentsMargins(20, 20, 20, 20)
        batch_lay.setSpacing(12)

        # Batch Header Row
        b_top = QHBoxLayout()
        b_header = QLabel("📦 BATCH / ZIP UPLOAD")
        b_header.setFont(QFont("Segoe UI Variable", 14, QFont.Weight.Bold))
        b_header.setStyleSheet("color: #8B9CFF;")
        b_top.addWidget(b_header)

        self._batch_badge = QLabel("Mode 1")
        self._batch_badge.setStyleSheet("background: #2E1065; color: #C4B5FD; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        b_top.addWidget(self._batch_badge, 0, Qt.AlignmentFlag.AlignRight)
        batch_lay.addLayout(b_top)

        b_sub = QLabel("Upload multiple PDF files or .ZIP folders containing drawings")
        b_sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        batch_lay.addWidget(b_sub)

        # Batch Mode Department Selector Dropdown
        b_dept_lay = QHBoxLayout()
        b_dept_lbl = QLabel("Engineering Dept *")
        b_dept_lbl.setFont(QFont("Segoe UI Variable", 11, QFont.Weight.DemiBold))
        b_dept_lbl.setStyleSheet("color: #94A3B8;")
        b_dept_lay.addWidget(b_dept_lbl)

        self._batch_dept_combo = QComboBox()
        self._batch_dept_combo.setFixedHeight(34)
        self._batch_dept_combo.setStyleSheet(dept_combo_style)
        self._batch_dept_combo.currentIndexChanged.connect(self._validate_batch_form)
        b_dept_lay.addWidget(self._batch_dept_combo, 1)
        batch_lay.addLayout(b_dept_lay)

        # Drop Zone for Batch Upload
        self._batch_drop = DropZone(allow_zips=True)
        self._batch_drop.files_dropped.connect(self._on_batch_files_selected)

        b_drop_lay = QVBoxLayout(self._batch_drop)
        b_drop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_drop_lay.setSpacing(8)

        b_icon = QLabel("📦")
        b_icon.setFont(QFont("Segoe UI", 34))
        b_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_icon.setStyleSheet("color: #8B9CFF;")
        b_drop_lay.addWidget(b_icon)

        b_instr = QLabel("Drag & drop multiple PDFs or .ZIP folders")
        b_instr.setFont(QFont("Segoe UI Variable", 13, QFont.Weight.DemiBold))
        b_instr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_instr.setStyleSheet("color: #F2F3F5;")
        b_drop_lay.addWidget(b_instr)

        b_browse = QPushButton("  Select Files / ZIPs")
        b_browse.setObjectName("PrimaryBtn")
        b_browse.setStyleSheet("background-color: #4F46E5; color: white;")
        b_browse.setFixedHeight(34)
        b_browse.setFixedWidth(200)
        b_browse.clicked.connect(self._browse_batch)
        b_drop_lay.addWidget(b_browse, 0, Qt.AlignmentFlag.AlignCenter)

        batch_lay.addWidget(self._batch_drop, 1)

        # Selected Batch Item List & Breakdown Card
        self._batch_file_card = QFrame()
        self._batch_file_card.setStyleSheet("background: #262932; border-radius: 8px; padding: 6px;")
        self._batch_file_card.hide()

        bc_lay = QVBoxLayout(self._batch_file_card)
        bc_lay.setContentsMargins(10, 8, 10, 8)
        bc_lay.setSpacing(6)

        bc_top = QHBoxLayout()
        self._batch_summary_lbl = QLabel("Selected files: 0")
        self._batch_summary_lbl.setFont(QFont("Segoe UI Variable", 11, QFont.Weight.DemiBold))
        self._batch_summary_lbl.setStyleSheet("color: #4ADE80;")
        bc_top.addWidget(self._batch_summary_lbl, 1)

        b_clear = QToolButton()
        b_clear.setText("Clear All ✕")
        b_clear.setStyleSheet("color: #F87171; background: transparent; font-size: 11px;")
        b_clear.clicked.connect(self._clear_batch_files)
        bc_top.addWidget(b_clear)

        bc_lay.addLayout(bc_top)

        self._batch_list = QListWidget()
        self._batch_list.setFixedHeight(64)
        self._batch_list.setStyleSheet(
            "QListWidget { background: #1A1C23; border: 1px solid #333742; border-radius: 4px; color: #E2E8F0; font-size: 11px; }"
            "QListWidget::item { padding: 3px 6px; }"
        )
        bc_lay.addWidget(self._batch_list)

        batch_lay.addWidget(self._batch_file_card)

        # Status & Progress for Batch
        self._batch_status_lbl = QLabel("")
        self._batch_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._batch_status_lbl.setFont(QFont("Segoe UI", 11))
        self._batch_status_lbl.setStyleSheet("color: #8B9CFF;")
        self._batch_status_lbl.hide()
        batch_lay.addWidget(self._batch_status_lbl)

        self._batch_prog = QProgressBar()
        self._batch_prog.setRange(0, 100)
        self._batch_prog.setValue(0)
        self._batch_prog.setFixedHeight(6)
        self._batch_prog.hide()
        batch_lay.addWidget(self._batch_prog)

        # Batch Dedicated Process Button
        self._batch_process_btn = QPushButton("  Process Batch Upload")
        self._batch_process_btn.setObjectName("PrimaryBtn")
        self._batch_process_btn.setStyleSheet(
            "QPushButton { background-color: #4F46E5; color: white; border-radius: 8px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4338CA; }"
            "QPushButton:disabled { background-color: #2D313A; color: #64748B; }"
        )
        self._batch_process_btn.setFixedHeight(42)
        self._batch_process_btn.setFont(QFont("Segoe UI Variable", 12, QFont.Weight.Bold))
        self._batch_process_btn.setEnabled(False)
        self._batch_process_btn.clicked.connect(self._start_batch_workflow)
        batch_lay.addWidget(self._batch_process_btn)

        flex_container.addWidget(self._batch_card, 1)

        root.addLayout(flex_container, 1)

        self._populate_departments()
        if self._controller:
            self._connect_controller_signals()

    # ── Backward Compatibility Property Aliases ──────────────────────────────

    @property
    def _dept_combo(self) -> QComboBox:
        return self._single_dept_combo

    @property
    def _process_btn(self) -> QPushButton:
        return self._single_process_btn

    # ── Styling Helpers ──────────────────────────────────────────────────────

    def _update_card_style(self, card: QFrame, active: bool, accent_color: str) -> None:
        if active:
            card.setStyleSheet(
                f"QFrame#Card {{ background: #1E2026; border: 2px solid {accent_color}; border-radius: 12px; }}"
            )
        else:
            card.setStyleSheet(
                "QFrame#Card { background: #1E2026; border: 1px solid #2D313A; border-radius: 12px; }"
            )

    # ── Controller & Dept Initialization ─────────────────────────────────────

    def set_controller(self, controller) -> None:
        self._controller = controller
        self._populate_departments()
        if self._controller:
            self._connect_controller_signals()

    def showEvent(self, event):
        super().showEvent(event)
        self.reload_data()

    def reload_data(self) -> None:
        if self._single_dept_combo.count() <= 1:
            self._populate_departments()

    def _populate_departments(self) -> None:
        for combo in (self._single_dept_combo, self._batch_dept_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("-- Select Engineering Department --", None)

        depts = []
        if self._controller:
            try:
                depts = self._controller.get_all_departments()
            except Exception as e:
                logger.warning(f"Failed to load departments from database: {e}")

        default_names = [
            "Electrical Engineering",
            "GPD",
            "Pipe Support Engineering",
            "Piping Engineering",
            "Plakon",
            "Structural & Physical Design",
            "System Engineering",
        ]

        if not depts:
            for idx, dname in enumerate(default_names):
                dept_id = f"DEPT-DEF-{idx+1:02d}"
                self._single_dept_combo.addItem(dname, dept_id)
                self._batch_dept_combo.addItem(dname, dept_id)
        else:
            for d in depts:
                name = d.get("name") if isinstance(d, dict) else getattr(d, "name", "")
                dept_id = d.get("id") if isinstance(d, dict) else getattr(d, "id", None)
                if name:
                    self._single_dept_combo.addItem(name, dept_id or name)
                    self._batch_dept_combo.addItem(name, dept_id or name)

        for combo in (self._single_dept_combo, self._batch_dept_combo):
            combo.blockSignals(False)

    # ── Department Selection Getters ────────────────────────────────────────

    def get_single_department_id(self) -> str | None:
        idx = self._single_dept_combo.currentIndex()
        if idx <= 0:
            return None
        return self._single_dept_combo.itemData(idx, Qt.ItemDataRole.UserRole)

    def get_single_department_name(self) -> str | None:
        idx = self._single_dept_combo.currentIndex()
        if idx <= 0:
            return None
        return self._single_dept_combo.currentText()

    def get_batch_department_id(self) -> str | None:
        idx = self._batch_dept_combo.currentIndex()
        if idx <= 0:
            return None
        return self._batch_dept_combo.itemData(idx, Qt.ItemDataRole.UserRole)

    def get_batch_department_name(self) -> str | None:
        idx = self._batch_dept_combo.currentIndex()
        if idx <= 0:
            return None
        return self._batch_dept_combo.currentText()

    def get_selected_department_id(self) -> str | None:
        return self.get_single_department_id() or self.get_batch_department_id()

    def get_selected_department_name(self) -> str | None:
        return self.get_single_department_name() or self.get_batch_department_name()

    # ── Form Validation & State Management ───────────────────────────────────

    def _validate_forms(self) -> bool:
        s_val = self._validate_single_form()
        b_val = self._validate_batch_form()
        return s_val or b_val

    def _validate_single_form(self) -> bool:
        has_dept = self.get_single_department_id() is not None or self.get_single_department_name() is not None
        dept_name = self.get_single_department_name() or ""
        has_single = bool(self._single_filepath and os.path.exists(self._single_filepath))

        if has_single:
            self._update_card_style(self._single_card, active=True, accent_color="#3E9BFF")
            if has_dept:
                fname = os.path.basename(self._single_filepath)
                self._single_status_lbl.setText(f"✓ Ready: '{fname}' for '{dept_name}'")
                self._single_status_lbl.setStyleSheet("color: #4ADE80;")
                self._single_status_lbl.show()
                self._single_process_btn.setEnabled(True)
                self._single_process_btn.setText("  Process Single Drawing")
                return True
            else:
                self._single_status_lbl.setText("⚠️ Select an Engineering Department.")
                self._single_status_lbl.setStyleSheet("color: #FBBF24;")
                self._single_status_lbl.show()
                self._single_process_btn.setEnabled(False)
                return False
        else:
            self._update_card_style(self._single_card, active=False, accent_color="#3E9BFF")
            self._single_process_btn.setEnabled(False)
            self._single_process_btn.setText("  Process Single Drawing")
            return False

    def _validate_batch_form(self) -> bool:
        has_dept = self.get_batch_department_id() is not None or self.get_batch_department_name() is not None
        dept_name = self.get_batch_department_name() or ""
        has_batch = bool(self._batch_filepaths)

        if has_batch:
            self._update_card_style(self._batch_card, active=True, accent_color="#8B9CFF")
            if has_dept:
                self._batch_status_lbl.setText(f"✓ Ready: Batch ({len(self._batch_filepaths)} items) for '{dept_name}'")
                self._batch_status_lbl.setStyleSheet("color: #4ADE80;")
                self._batch_status_lbl.show()
                self._batch_process_btn.setEnabled(True)
                self._batch_process_btn.setText("  Process Batch Upload")
                return True
            else:
                self._batch_status_lbl.setText("⚠️ Select an Engineering Department.")
                self._batch_status_lbl.setStyleSheet("color: #FBBF24;")
                self._batch_status_lbl.show()
                self._batch_process_btn.setEnabled(False)
                return False
        else:
            self._update_card_style(self._batch_card, active=False, accent_color="#8B9CFF")
            self._batch_process_btn.setEnabled(False)
            self._batch_process_btn.setText("  Process Batch Upload")
            return False

    def _connect_controller_signals(self) -> None:
        if not self._controller:
            return
        try:
            self._controller.workflow_step_signal.connect(self._on_workflow_step)
            self._controller.workflow_completed_signal.connect(self._on_workflow_completed)
        except Exception:
            pass

        try:
            self._controller.batch_workflow_step_signal.connect(self._on_batch_workflow_step)
            self._controller.batch_workflow_completed_signal.connect(self._on_batch_workflow_completed)
        except Exception:
            pass

        try:
            self._controller.processing_error_signal.connect(self._on_doc_error)
        except Exception:
            pass

    # ── Single File Handlers ──────────────────────────────────────────────────

    def _browse_single(self) -> None:
        path = open_pdf_file(self)
        if path:
            self._on_single_file_selected(path)

    def _on_single_file_selected(self, path: str) -> None:
        self._single_filepath = path
        name = os.path.basename(path)

        if self._controller:
            val_res = self._controller.validate_file(path)
            if not val_res.is_valid:
                self._single_fname.setText(name)
                self._single_fmeta.setText(f"❌ {val_res.error_message}")
                self._single_file_card.show()
                self._validate_single_form()
                return
            size_str = f"{val_res.file_size_mb} MB"
        else:
            size_mb = round(os.path.getsize(path) / (1024 * 1024), 2) if os.path.exists(path) else "?"
            size_str = f"{size_mb} MB"

        self._single_fname.setText(name)
        self._single_fmeta.setText(f"{size_str}  ·  Validated PDF Drawing")
        self._single_file_card.show()
        self._validate_single_form()

    def _clear_single_file(self) -> None:
        self._single_filepath = None
        self._single_file_card.hide()
        self._single_prog.hide()
        self._single_status_lbl.hide()
        self._single_prog.setValue(0)
        self._validate_single_form()

    # ── Batch Files & Zip Handlers ────────────────────────────────────────────

    def _browse_batch(self) -> None:
        paths = open_multiple_pdf_or_zip_files(self)
        if paths:
            self._on_batch_files_selected(paths)

    def _on_batch_files_selected(self, paths: List[str]) -> None:
        existing = set(self._batch_filepaths)
        for p in paths:
            if p and p not in existing:
                self._batch_filepaths.append(p)
                existing.add(p)

        self._update_batch_display()
        self._validate_batch_form()

    def _update_batch_display(self) -> None:
        self._batch_list.clear()

        if not self._batch_filepaths:
            self._batch_file_card.hide()
            return

        total_mb = 0.0
        zip_count = 0
        pdf_count = 0

        for p in self._batch_filepaths:
            p_obj = Path(p)
            fname = p_obj.name
            size_mb = round(p_obj.stat().st_size / (1024 * 1024), 2) if p_obj.exists() else 0.0
            total_mb += size_mb

            if p_obj.suffix.lower() == ".zip":
                zip_count += 1
                insp_text = "[ZIP Archive]"
                if self._controller and hasattr(self._controller, "file_service"):
                    insp = self._controller.file_service.inspect_zip_archive(p_obj)
                    p_num = len(insp.get("pdf_files", []))
                    insp_text = f"[ZIP Archive: {p_num} PDF(s)]"

                item_text = f"📦 {fname} ({size_mb} MB)  {insp_text}"
            else:
                pdf_count += 1
                item_text = f"📄 {fname} ({size_mb} MB)  [PDF Drawing]"

            self._batch_list.addItem(item_text)

        summary_parts = []
        if pdf_count > 0:
            summary_parts.append(f"{pdf_count} PDF(s)")
        if zip_count > 0:
            summary_parts.append(f"{zip_count} ZIP archive(s)")

        total_desc = " + ".join(summary_parts) if summary_parts else "0 files"
        self._batch_summary_lbl.setText(f"Selected: {len(self._batch_filepaths)} ({total_desc}, ~{round(total_mb, 1)} MB)")
        self._batch_file_card.show()

    def _clear_batch_files(self) -> None:
        self._batch_filepaths.clear()
        self._batch_list.clear()
        self._batch_file_card.hide()
        self._batch_prog.hide()
        self._batch_status_lbl.hide()
        self._batch_prog.setValue(0)
        self._validate_batch_form()

    # ── Processing Workflows ──────────────────────────────────────────────────

    def _start_single_workflow(self) -> None:
        dept_id = self.get_single_department_id()
        dept_name = self.get_single_department_name()

        if not dept_id and not dept_name:
            self._single_status_lbl.setText("❌ Select an Engineering Department before processing.")
            self._single_status_lbl.setStyleSheet("color: #F87171;")
            self._single_status_lbl.show()
            self._single_process_btn.setEnabled(False)
            return

        if not self._single_filepath or not os.path.exists(self._single_filepath):
            self._single_status_lbl.setText("❌ Select a valid PDF drawing.")
            self._single_status_lbl.setStyleSheet("color: #F87171;")
            self._single_status_lbl.show()
            return

        self._single_prog.show()
        self._single_status_lbl.setText(f"Processing '{os.path.basename(self._single_filepath)}'...")
        self._single_status_lbl.setStyleSheet("color: #3E9BFF;")
        self._single_status_lbl.show()
        self._single_prog.setValue(10)
        
        self._single_process_btn.setText("Processing Pipeline Active...")
        self._single_process_btn.setEnabled(False)

        if self._controller:
            self._controller.start_processing_workflow(self._single_filepath, department_id=dept_id or dept_name)
        else:
            self._single_prog.setValue(100)

    def _start_batch_workflow(self) -> None:
        dept_id = self.get_batch_department_id()
        dept_name = self.get_batch_department_name()

        if not dept_id and not dept_name:
            self._batch_status_lbl.setText("❌ Select an Engineering Department before processing.")
            self._batch_status_lbl.setStyleSheet("color: #F87171;")
            self._batch_status_lbl.show()
            self._batch_process_btn.setEnabled(False)
            return

        if not self._batch_filepaths:
            self._batch_status_lbl.setText("❌ Select PDF or ZIP files to process.")
            self._batch_status_lbl.setStyleSheet("color: #F87171;")
            self._batch_status_lbl.show()
            return

        self._batch_prog.show()
        self._batch_status_lbl.setText(f"Batch Processing Active for '{dept_name}'...")
        self._batch_status_lbl.setStyleSheet("color: #8B9CFF;")
        self._batch_status_lbl.show()
        self._batch_prog.setValue(5)

        self._batch_process_btn.setText("Batch Processing Active...")
        self._batch_process_btn.setEnabled(False)

        if self._controller:
            self._controller.start_batch_processing_workflow(self._batch_filepaths, department_id=dept_id or dept_name)
        else:
            self._batch_prog.setValue(100)

    def _start_active_workflow(self) -> None:
        """Fallback method delegating to active workflow."""
        if self._single_filepath:
            self._start_single_workflow()
        elif self._batch_filepaths:
            self._start_batch_workflow()

    # ── Workflow Signals Slots ────────────────────────────────────────────────

    def _on_workflow_step(self, step_snapshot) -> None:
        self._single_prog.setValue(step_snapshot.progress_percentage)
        self._single_status_lbl.setText(f"{step_snapshot.step_name}: {step_snapshot.message}")

    def _on_workflow_completed(self, result_dto) -> None:
        self._single_prog.setValue(100)
        self._single_status_lbl.setText(f"✓ Complete in {result_dto.processing_duration_seconds}s! Saved to DB.")
        self._single_status_lbl.setStyleSheet("color: #4ADE80;")
        self._single_status_lbl.show()

        self._single_process_btn.setText("  View PDF Drawing ➔  ")
        self._single_process_btn.setEnabled(True)
        self._single_process_btn.setStyleSheet(
            "QPushButton { background-color: #059669; color: white; border-radius: 8px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #047857; }"
        )
        try:
            self._single_process_btn.clicked.disconnect()
        except Exception:
            pass
        self._single_process_btn.clicked.connect(self._open_viewer)

    def _on_batch_workflow_step(self, batch_snapshot) -> None:
        pct = batch_snapshot.overall_progress_percentage
        idx = batch_snapshot.current_file_index
        total = batch_snapshot.total_files
        fname = batch_snapshot.current_file_name
        step_name = batch_snapshot.step_snapshot.step_name

        self._batch_prog.setValue(pct)
        self._batch_status_lbl.setText(f"[{idx}/{total}] {fname} — {step_name} ({pct}%)")

    def _on_batch_workflow_completed(self, batch_result_dto) -> None:
        self._batch_prog.setValue(100)
        succ = batch_result_dto.successful_files_count
        tot = batch_result_dto.total_files_processed
        dur = batch_result_dto.total_duration_seconds
        cmts = batch_result_dto.total_comments_found

        self._batch_status_lbl.setText(f"✓ Batch Complete! {succ}/{tot} processed ({cmts} comments, {dur}s)")
        self._batch_status_lbl.setStyleSheet("color: #4ADE80;")
        self._batch_status_lbl.show()

        self._batch_process_btn.setText("  View Processed Drawings ➔  ")
        self._batch_process_btn.setEnabled(True)
        self._batch_process_btn.setStyleSheet(
            "QPushButton { background-color: #059669; color: white; border-radius: 8px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #047857; }"
        )
        try:
            self._batch_process_btn.clicked.disconnect()
        except Exception:
            pass
        self._batch_process_btn.clicked.connect(self._open_viewer)

    def _open_viewer(self) -> None:
        self.open_viewer_requested.emit()

    def _on_doc_error(self, error_msg: str) -> None:
        self._single_prog.hide()
        self._batch_prog.hide()
        self._single_status_lbl.setText(f"❌ {error_msg}")
        self._batch_status_lbl.setText(f"❌ {error_msg}")
        self._single_status_lbl.setStyleSheet("color: #F87171;")
        self._batch_status_lbl.setStyleSheet("color: #F87171;")
        self._single_process_btn.setText("Processing Failed")
        self._batch_process_btn.setText("Processing Failed")

    def _show_recent(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #252830; color: #F2F3F5; border: 1px solid #3A3D46; "
            "border-radius: 6px; padding: 6px; }"
            "QMenu::item { padding: 8px 16px; border-radius: 4px; font-size: 12px; }"
            "QMenu::item:selected { background-color: #3E9BFF; color: #FFFFFF; }"
            "QMenu::separator { height: 1px; background: #3A3D46; margin: 4px 0px; }"
        )

        recent_drawings = []
        if self._controller:
            try:
                recent_drawings = self._controller.get_recent_drawings(limit=15)
            except Exception as e:
                logger.warning(f"Error fetching recent drawings: {e}")

        added_paths = set()
        actions_count = 0

        def _resolve_file_path(raw_path: str, fname: str) -> Path | None:
            if raw_path and Path(raw_path).exists():
                return Path(raw_path)
            if raw_path and Path(raw_path).is_file():
                return Path(raw_path).resolve()
            p_rel = Path(raw_path) if raw_path else None
            if p_rel and p_rel.exists():
                return p_rel.resolve()
            dataset_dir = Path("dataset/raw_drawings")
            if dataset_dir.exists() and fname:
                for found in dataset_dir.rglob(fname):
                    if found.is_file():
                        return found.resolve()
            return None

        for d in recent_drawings:
            fname = d.get("file_name", "")
            raw_path = d.get("file_path", "")
            dept_name = d.get("department_name")
            dept_id = d.get("department_id")
            pages = d.get("total_pages", 1)

            resolved = _resolve_file_path(raw_path, fname)
            if not resolved or str(resolved) in added_paths:
                continue

            added_paths.add(str(resolved))
            actions_count += 1

            dept_display = dept_name if dept_name and dept_name != "Unassigned" else "General"
            label = f"{fname}  •  {dept_display} ({pages}p)"
            action = menu.addAction(label)
            if _HAS_QTA:
                try:
                    action.setIcon(qta.icon("fa5s.file-pdf", color="#3E9BFF"))
                except Exception:
                    pass

            def _make_handler(target_path=str(resolved), target_dept=dept_name, target_id=dept_id):
                return lambda: self._select_recent_file(target_path, target_dept, target_id)

            action.triggered.connect(_make_handler())

        if actions_count == 0:
            empty_act = menu.addAction("No recent PDF files found")
            empty_act.setEnabled(False)

        btn_pos = self._recent_btn.mapToGlobal(self._recent_btn.rect().bottomLeft())
        menu.exec(btn_pos)

    def _select_recent_file(self, file_path: str, dept_name: str | None = None, dept_id: str | None = None) -> None:
        self._on_single_file_selected(file_path)

        if dept_id or dept_name:
            for idx in range(1, self._single_dept_combo.count()):
                item_id = self._single_dept_combo.itemData(idx, Qt.ItemDataRole.UserRole)
                item_text = self._single_dept_combo.itemText(idx)
                if (dept_id and item_id == dept_id) or (dept_name and item_text.strip().lower() == dept_name.strip().lower()):
                    self._single_dept_combo.setCurrentIndex(idx)
                    break

        self._validate_single_form()

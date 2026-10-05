"""
ocr_results_screen.py — OCR Results screen.

Provides:
    OcrResultsPage(QWidget)
        Editable table of OCR-extracted comment text with confidence bars,
        status chips, a search bar, status filter, and pagination controls.

ARCHITECTURE NOTE:
This screen loads comments through AppController.get_comments_for_drawing()
and persists inline text edits through AppController.update_comment_text().

UI code in this file must NOT:
  - import or instantiate CommentRepository directly
  - execute SQLAlchemy queries
  - access SQLite

MOCK DATA FALLBACK:
When no controller is present or the database has no comments for the loaded
drawing, the screen falls back to app/mock_data.py COMMENTS so that the UI
remains functional during development. This fallback is intentional and must
be retained until the OCR/AI pipeline populates the database.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                                QLabel, QTableView, QPushButton, QComboBox,
                                QHeaderView, QAbstractItemView, QDialog,
                                QTextEdit, QScrollArea, QMessageBox)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, QModelIndex

from app import mock_data as md
from app.components.comment_table import (
    ConfidenceDelegate,
    StatusDelegate,
    EngineDelegate,
    PageDelegate,
)
from app.components.search_bar import SearchBar
from src.services.text_cleaning_service import TextCleaningService
from src.core.dtos.comment_processing_dtos import CleanedCommentDTO, CorrectionDTO


class CleanTextDialog(QDialog):
    """
    Modal dialog displaying OCR text cleaning results and corrections,
    allowing the user to inspect differences and save cleaned text back to the comment.
    """

    def __init__(
        self,
        comment_id: str,
        original_text: str,
        cleaned_dto: CleanedCommentDTO,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Clean Text — {comment_id}")
        self.setMinimumWidth(540)
        self.setMinimumHeight(440)
        self.resize(580, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # ── Header ────────────────────────────────────────────────
        title_lbl = QLabel("OCR Text Cleaning & Corrections")
        title_lbl.setObjectName("CardHeader")
        layout.addWidget(title_lbl)

        cid_lbl = QLabel(f"Comment ID: {comment_id}")
        cid_lbl.setObjectName("SubCaption")
        layout.addWidget(cid_lbl)

        # ── Original Text ─────────────────────────────────────────
        orig_lbl = QLabel("Original Text:")
        orig_lbl.setStyleSheet("font-weight: 600;")
        layout.addWidget(orig_lbl)

        self._orig_edit = QTextEdit()
        self._orig_edit.setPlainText(original_text)
        self._orig_edit.setReadOnly(True)
        self._orig_edit.setMaximumHeight(70)
        layout.addWidget(self._orig_edit)

        # ── Cleaned Text ──────────────────────────────────────────
        clean_lbl = QLabel("Cleaned Text (Editable):")
        clean_lbl.setStyleSheet("font-weight: 600;")
        layout.addWidget(clean_lbl)

        self._clean_edit = QTextEdit()
        self._clean_edit.setPlainText(cleaned_dto.cleaned_text)
        self._clean_edit.setMaximumHeight(80)
        layout.addWidget(self._clean_edit)

        # ── Corrections List ──────────────────────────────────────
        corr_count = len(cleaned_dto.corrections) if cleaned_dto.corrections else 0
        corr_header = QLabel(f"Corrections Applied ({corr_count}):")
        corr_header.setStyleSheet("font-weight: 600;")
        layout.addWidget(corr_header)

        corr_container = QFrame()
        corr_container.setObjectName("Card")
        corr_lay = QVBoxLayout(corr_container)
        corr_lay.setContentsMargins(14, 12, 14, 12)
        corr_lay.setSpacing(8)

        if cleaned_dto.corrections:
            for corr in cleaned_dto.corrections:
                c_type = getattr(corr, "correction_type", "correction")
                c_lbl = QLabel(
                    f"• <b>{corr.original}</b> → <b>{corr.corrected}</b> "
                    f"<i>({c_type})</i>"
                )
                c_lbl.setTextFormat(Qt.TextFormat.RichText)
                c_lbl.setWordWrap(True)
                corr_lay.addWidget(c_lbl)
        else:
            no_corr_lbl = QLabel("No corrections were necessary — text is already clean.")
            no_corr_lbl.setStyleSheet("color: #A6A9B1; font-style: italic;")
            corr_lay.addWidget(no_corr_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(corr_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(140)
        layout.addWidget(scroll)

        # ── Action Buttons ────────────────────────────────────────
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)
        btn_box.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Save to Comment")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self.accept)
        btn_box.addWidget(save_btn)

        layout.addLayout(btn_box)

    def get_cleaned_text(self) -> str:
        """Return the (potentially user-edited) cleaned text."""
        return self._clean_edit.toPlainText().strip()



def _get(c: Union[Dict[str, Any], Any], field: str, default: Any = "") -> Any:
    """Access a field from either a normalised display dict or a mock dataclass."""
    if isinstance(c, dict):
        return c.get(field, default)
    return getattr(c, field, default)


class OcrResultsPage(QWidget):
    """
    OCR Results — editable table with confidence bars, status chips,
    search, filter, and pagination.
    """
    comment_selected = Signal(str)

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._page      = 0
        self._page_size = 10

        # Load comments from DB or fall back to mock data
        # INTEGRATION NOTE:
        # DB comments are normalised dicts. Mock data items are dataclass objects.
        # The _get() helper handles both. Once the OCR pipeline populates the DB,
        # the fallback will naturally be bypassed.
        self._comments: List[Any] = self._load_comments()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # ── Toolbar ───────────────────────────────────────────────
        tb = QHBoxLayout()
        tb.setSpacing(12)

        search = SearchBar(
            placeholder="  🔍  Search OCR text, drawing number…",
            fixed_width=320,
        )
        tb.addWidget(search)
        tb.addStretch()

        self._dwg_filt = QComboBox()
        self._dwg_filt.setFixedHeight(36)
        self._dwg_filt.setFixedWidth(200)
        self._dwg_filt.currentIndexChanged.connect(self._on_drawing_filter_changed)
        tb.addWidget(self._dwg_filt)

        self._status_filt = QComboBox()
        self._status_filt.addItems(["All Status", "Pending", "Approved", "Rejected", "Flagged"])
        self._status_filt.setFixedHeight(36)
        self._status_filt.setFixedWidth(140)
        self._status_filt.currentTextChanged.connect(self._on_status_filter_changed)
        tb.addWidget(self._status_filt)

        clean_btn = QPushButton("✨ Clean Text")
        clean_btn.setObjectName("PrimaryBtn")
        clean_btn.setFixedHeight(36)
        clean_btn.setToolTip("Run TextCleaningService and view corrections")
        clean_btn.clicked.connect(self.clean_selected_comment)
        tb.addWidget(clean_btn)

        review_btn = QPushButton("🔍 View in Review")
        review_btn.setObjectName("SecondaryBtn")
        review_btn.setFixedHeight(36)
        review_btn.setToolTip("Open this comment directly in the Human Review screen")
        review_btn.clicked.connect(self.view_selected_in_review)
        tb.addWidget(review_btn)

        root.addLayout(tb)

        # ── Table ─────────────────────────────────────────────────
        table_card = QFrame()
        table_card.setObjectName("Card")
        tc_lay = QVBoxLayout(table_card)
        tc_lay.setContentsMargins(0, 0, 0, 0)

        self._model = self._build_model()
        
        self._status_proxy = QSortFilterProxyModel()
        self._status_proxy.setSourceModel(self._model)
        self._status_proxy.setFilterKeyColumn(6)
        
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._status_proxy)
        self._proxy.setFilterKeyColumn(-1)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        search.search_changed.connect(self._proxy.setFilterFixedString)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().hide()
        self._table.setShowGrid(False)
        self._table.setItemDelegateForColumn(1, PageDelegate(self._table))
        self._table.setItemDelegateForColumn(4, ConfidenceDelegate(self._table))
        self._table.setItemDelegateForColumn(5, EngineDelegate(self._table))
        self._table.setItemDelegateForColumn(6, StatusDelegate(self._table))

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Comment ID
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)            # Page
        self._table.setColumnWidth(1, 75)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)          # OCR Text
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # BBox (X, Y, W, H)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)            # OCR Conf.
        self._table.setColumnWidth(4, 125)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)            # Engine
        self._table.setColumnWidth(5, 120)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)            # Status
        self._table.setColumnWidth(6, 115)

        # Connect row click & double click to jump to Human Review
        self._table.clicked.connect(self._on_table_clicked)
        self._table.doubleClicked.connect(self._on_table_double_clicked)

        # Connect text edits to persistence
        # INTEGRATION NOTE:
        # When a user double-clicks and edits OCR text, dataChanged fires.
        # _on_text_edited() resolves the comment ID from the ID column and
        # calls AppController.update_comment_text(). For mock data IDs
        # (format "C-NNNN"), persistence is skipped.
        self._model.dataChanged.connect(self._on_text_edited)

        tc_lay.addWidget(self._table)
        root.addWidget(table_card, 1)

        # ── Pagination ────────────────────────────────────────────
        pag = QHBoxLayout()
        pag.setSpacing(8)

        rpp_lbl = QLabel("Rows per page:")
        rpp_lbl.setObjectName("SubCaption")
        pag.addWidget(rpp_lbl)

        rpp = QComboBox()
        rpp.addItems(["10", "25", "50"])
        rpp.setFixedHeight(32)
        rpp.setFixedWidth(70)
        pag.addWidget(rpp)

        pag.addStretch()

        total = len(self._comments)
        self._pg_lbl = QLabel(f"1–{min(self._page_size, total)} of {total}")
        self._pg_lbl.setObjectName("SubCaption")
        pag.addWidget(self._pg_lbl)

        prev_btn = QPushButton("‹")
        prev_btn.setObjectName("SecondaryBtn")
        prev_btn.setFixedSize(32, 32)
        pag.addWidget(prev_btn)

        next_btn = QPushButton("›")
        next_btn.setObjectName("SecondaryBtn")
        next_btn.setFixedSize(32, 32)
        pag.addWidget(next_btn)

        root.addLayout(pag)

    # ── Data loading ──────────────────────────────────────────────

    # ── Data loading ──────────────────────────────────────────────

    def reload_drawings(self) -> None:
        """Populate the drawing scope dropdown."""
        if not hasattr(self, "_dwg_filt") or not self._controller:
            return
        self._dwg_filt.blockSignals(True)
        self._dwg_filt.clear()
        self._dwg_filt.addItem("📄 Active Drawing Only", "")
        self._dwg_filt.addItem("🌐 All Drawings in Batch", "ALL")

        drawings = self._controller.get_all_drawings()
        for d in drawings:
            did = d.get("id", "")
            fname = d.get("file_name", "Drawing")
            cmts = d.get("comments_count", 0)
            prefix = "➜ " if did == self._controller.current_drawing_id else "   "
            label = f"{prefix}{fname} ({cmts} cmts)"
            self._dwg_filt.addItem(label, did)

        curr_id = self._controller.current_drawing_id
        if curr_id:
            for i in range(self._dwg_filt.count()):
                if self._dwg_filt.itemData(i) == curr_id:
                    self._dwg_filt.setCurrentIndex(i)
                    break
        self._dwg_filt.blockSignals(False)

    def _on_drawing_filter_changed(self, index: int) -> None:
        dwg_id = self._dwg_filt.itemData(index)
        if dwg_id == "ALL":
            drawings = self._controller.get_all_drawings() if self._controller else []
            all_cmts = []
            for d in drawings:
                did = d.get("id")
                if did:
                    all_cmts.extend(self._controller.get_comments_for_drawing(did))
            self._comments = all_cmts
        elif dwg_id and self._controller and dwg_id != self._controller.current_drawing_id:
            self._controller.switch_current_drawing(dwg_id)
            return
        else:
            self._comments = self._load_comments()

        self._rebuild_table()

    def _load_comments(self) -> List[Any]:
        """Load comments from DB via controller, or fall back to mock data."""
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            return db_comments if db_comments else []
        elif self._controller:
            return []
        return list(md.COMMENTS)

    def reload_comments(self) -> None:
        """Reload table contents from the database. Call after new PDF is loaded."""
        self.reload_drawings()
        self._comments = self._load_comments()
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for c in self._comments:
            self._append_row(c)

    # ── Model builder ─────────────────────────────────────────────

    def _build_model(self) -> QStandardItemModel:
        model = QStandardItemModel(0, 7)
        model.setHorizontalHeaderLabels(
            ["Comment ID", "Page", "OCR Text", "BBox (X, Y, W, H)", "OCR Conf.", "Engine", "Status"]
        )
        for c in self._comments:
            self._append_row(c, model)
        return model

    def _append_row(
        self,
        c: Union[Dict[str, Any], Any],
        model: Optional[QStandardItemModel] = None,
    ) -> None:
        """Append a single comment row with Page, BBox, and Engine telemetry to the model."""
        if model is None:
            model = self._model

        cid        = _get(c, "id", "")
        ocr_text   = _get(c, "ocr_text", "") or _get(c, "cleaned_text", "") or _get(c, "raw_text", "")
        ocr_conf   = _get(c, "ocr_confidence", None)
        if ocr_conf is None:
            ocr_conf = _get(c, "confidence", 0.0)
        confidence = float(ocr_conf)
        status     = _get(c, "status", "Pending")
        drawing_id = _get(c, "drawing_id", "")
        drawing_no = _get(c, "drawing_no", "")

        # Page extraction
        raw_p = _get(c, "page_number", None)
        if raw_p is None:
            raw_p = _get(c, "page", 1)
        try:
            page_val = int(raw_p)
        except Exception:
            page_val = 1
        page_str = str(page_val)

        # Engine extraction & attribution
        engine_str = _get(c, "ocr_engine", "")
        if not engine_str:
            engine_str = "Tesseract OCR"

        # Bounding box & spatial telemetry (X, Y, W, H)
        raw_bbox = _get(c, "bbox", None)
        if not raw_bbox:
            bx0 = _get(c, "bbox_x0", 0.0)
            by0 = _get(c, "bbox_y0", 0.0)
            bx1 = _get(c, "bbox_x1", 0.0)
            by1 = _get(c, "bbox_y1", 0.0)
            raw_bbox = (bx0, by0, bx1, by1)

        x, y, w, h = 0.0, 0.0, 0.0, 0.0
        if raw_bbox and isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
            b0, b1, b2, b3 = float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])
            is_mock = str(cid).startswith("C-")
            if is_mock:
                # Mock format: (x, y, w, h)
                x, y, w, h = b0, b1, b2, b3
            else:
                # Pipeline / Database format: (x0, y0, x1, y1)
                x = b0
                y = b1
                w = max(0.0, b2 - b0)
                h = max(0.0, b3 - b1)

        if max(x, y, w, h) <= 1.0 and (x > 0 or y > 0 or w > 0 or h > 0):
            bbox_str = f"[{x:.2f}, {y:.2f}, {w:.2f}, {h:.2f}]"
        else:
            bbox_str = f"[{int(round(x))}, {int(round(y))}, {int(round(w))}, {int(round(h))}]"

        # 0. Comment ID
        id_item = QStandardItem(cid)
        id_item.setFont(QFont("Cascadia Code", 12))
        id_item.setForeground(QColor("#38BDF8"))
        id_item.setData(c, Qt.ItemDataRole.UserRole)
        tooltip = f"Drawing: {drawing_no or drawing_id}\nClick to view and edit in Human Review"
        id_item.setToolTip(tooltip)
        id_item.setEditable(False)

        # 1. Page
        page_item = QStandardItem(page_str)
        page_item.setToolTip(f"Drawing Page {page_str}")
        page_item.setEditable(False)

        # 2. OCR Text
        text_item = QStandardItem(ocr_text)
        is_ocr_failed_placeholder = (
            "OCR Failed" in ocr_text or
            "Needs Manual Transcription" in ocr_text or
            "fail" in engine_str.lower()
        )
        if is_ocr_failed_placeholder:
            text_item.setForeground(QColor("#F87171"))
            text_item.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
            text_item.setToolTip(
                "OCR could not transcribe text in this detected markup region.\n"
                "Double-click to manually transcribe in Human Review, or edit directly in this cell."
            )
        text_item.setEditable(True)   # Inline editing enabled

        # 3. BBox (X, Y, W, H)
        bbox_item = QStandardItem(bbox_str)
        bbox_item.setFont(QFont("Cascadia Code", 11))
        bbox_item.setForeground(QColor("#94A3B8"))
        bbox_item.setToolTip(
            f"Spatial Telemetry (Bounding Box):\n"
            f"• X (Left): {x:.2f}\n"
            f"• Y (Top): {y:.2f}\n"
            f"• Width: {w:.2f}\n"
            f"• Height: {h:.2f}"
        )
        bbox_item.setEditable(False)

        # 4. OCR Conf.
        conf_item = QStandardItem()
        conf_item.setData(float(confidence), Qt.ItemDataRole.UserRole)
        conf_item.setToolTip(f"OCR Recognition Confidence: {int(float(confidence) * 100)}%")
        conf_item.setEditable(False)

        # 5. Engine
        engine_item = QStandardItem(engine_str)
        engine_item.setToolTip(f"OCR Engine Attribution: {engine_str}")
        engine_item.setEditable(False)

        # 6. Status
        status_item = QStandardItem(status)
        status_item.setEditable(False)

        for item in [id_item, page_item, text_item, bbox_item, conf_item, engine_item, status_item]:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
        model.appendRow([id_item, page_item, text_item, bbox_item, conf_item, engine_item, status_item])

    # ── Comment Navigation Slots ──────────────────────────────────

    def _resolve_comment_data(self, proxy_index: QModelIndex) -> tuple[Optional[str], Optional[str]]:
        """Resolve comment ID and drawing ID from a proxy model index."""
        if not proxy_index.isValid():
            return None, None
        proxy_row = proxy_index.row()
        status_idx = self._proxy.mapToSource(self._proxy.index(proxy_row, 0))
        source_idx = self._status_proxy.mapToSource(status_idx)
        source_row = source_idx.row()
        item = self._model.item(source_row, 0)
        if not item:
            return None, None
        cid = item.text().strip()
        c_obj = item.data(Qt.ItemDataRole.UserRole)
        c_dwg_id = _get(c_obj, "drawing_id", "") if c_obj else None
        return cid, c_dwg_id

    def _emit_jump_to_review(self, cid: Optional[str], c_dwg_id: Optional[str]) -> None:
        if not cid:
            return
        if c_dwg_id and self._controller and c_dwg_id != self._controller.current_drawing_id:
            self._controller.switch_current_drawing(c_dwg_id)
        self.comment_selected.emit(cid)

    def _on_table_clicked(self, index: QModelIndex) -> None:
        """Single-clicking Column 0 (Comment ID) redirects directly to Human Review."""
        if index.column() == 0:
            cid, c_dwg_id = self._resolve_comment_data(index)
            self._emit_jump_to_review(cid, c_dwg_id)

    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        """Double-clicking any non-text column redirects directly to Human Review."""
        if index.column() != 2:  # Keep column 2 (OCR Text) for inline text editing
            cid, c_dwg_id = self._resolve_comment_data(index)
            self._emit_jump_to_review(cid, c_dwg_id)

    def view_selected_in_review(self) -> None:
        """Emit comment_selected for the currently selected row to jump to Human Review."""
        selection = self._table.selectionModel().selectedRows()
        if selection:
            cid, c_dwg_id = self._resolve_comment_data(selection[0])
            self._emit_jump_to_review(cid, c_dwg_id)
            return
        curr = self._table.currentIndex()
        if curr.isValid():
            cid, c_dwg_id = self._resolve_comment_data(curr)
            self._emit_jump_to_review(cid, c_dwg_id)
            return
        if self._model.rowCount() > 0:
            item = self._model.item(0, 0)
            if item:
                cid = item.text().strip()
                c_obj = item.data(Qt.ItemDataRole.UserRole)
                c_dwg_id = _get(c_obj, "drawing_id", "") if c_obj else None
                self._emit_jump_to_review(cid, c_dwg_id)

    # ── Text Cleaning & Persistence slots ─────────────────────────

    def clean_selected_comment(self) -> None:
        """
        Clean OCR text for the currently selected comment and display corrections dialog.
        Saves cleaned text back to the database when confirmed by the user.
        """
        # Determine the selected row
        selection = self._table.selectionModel().selectedRows()
        if not selection:
            current = self._table.currentIndex()
            if current.isValid():
                proxy_row = current.row()
            elif self._model.rowCount() > 0:
                proxy_row = 0
            else:
                QMessageBox.information(
                    self,
                    "Clean Text",
                    "No comments available to clean.",
                )
                return
        else:
            proxy_row = selection[0].row()

        status_idx = self._proxy.mapToSource(self._proxy.index(proxy_row, 0))
        source_idx = self._status_proxy.mapToSource(status_idx)
        source_row = source_idx.row()

        id_item = self._model.item(source_row, 0)
        text_item = self._model.item(source_row, 2)
        if not id_item or not text_item:
            return

        comment_id = id_item.text()
        raw_text = text_item.text()

        # Call text cleaning service via controller
        if self._controller and hasattr(self._controller, "text_cleaning_service") and self._controller.text_cleaning_service:
            cleaning_service = self._controller.text_cleaning_service
        else:
            cleaning_service = TextCleaningService()

        cleaned_dto = cleaning_service.clean_text(raw_text)

        dialog = CleanTextDialog(
            comment_id=comment_id,
            original_text=raw_text,
            cleaned_dto=cleaned_dto,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = dialog.get_cleaned_text()
            # Update the table cell
            text_item.setText(new_text)

            # Persist to database via controller
            if self._controller and hasattr(self._controller, "update_comment_text"):
                if not comment_id.startswith("C-"):
                    self._controller.update_comment_text(comment_id, new_text)

            # Update local in-memory comment list
            for c in self._comments:
                if _get(c, "id") == comment_id:
                    if isinstance(c, dict):
                        c["ocr_text"] = new_text
                    elif hasattr(c, "ocr_text"):
                        setattr(c, "ocr_text", new_text)
                    break

    def _on_text_edited(self, top_left, bottom_right, roles) -> None:
        """
        Persist inline OCR text edits to the database.

        INTEGRATION NOTE:
        Only column 1 (OCR Text) is editable. When the edit role fires,
        we retrieve the comment ID from column 0 of the same row and call
        AppController.update_comment_text().

        Mock data IDs (format "C-NNNN") are skipped — they cannot be
        persisted because they are not in the database.
        """
        if Qt.ItemDataRole.EditRole not in roles:
            return
        if top_left.column() != 2:
            return

        row = top_left.row()
        id_item   = self._model.item(row, 0)
        text_item = self._model.item(row, 2)
        if id_item is None or text_item is None:
            return

        comment_id = id_item.text()
        new_text   = text_item.text()

        # Skip mock data — IDs in mock data use "C-NNNN" format
        if self._controller and comment_id and not comment_id.startswith("C-"):
            self._controller.update_comment_text(comment_id, new_text)

    def _on_status_filter_changed(self, text: str) -> None:
        if text == "All Status":
            self._status_proxy.setFilterRegularExpression("")
        else:
            self._status_proxy.setFilterRegularExpression(f"^{text}$")

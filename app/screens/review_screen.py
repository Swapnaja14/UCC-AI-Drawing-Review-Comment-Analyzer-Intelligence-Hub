"""
review_screen.py — Human Verification screen.

Provides:
    HumanReviewPage(QWidget)
        Splitter: PDF canvas on the left, review panel on the right.
        Supports keyboard shortcuts: A = Approve, R = Reject, ←/→ = Prev/Next.

ARCHITECTURE NOTE:
This screen loads comments through AppController.get_comments_for_drawing()
and persists human-review actions (approve, reject, text edit) through
AppController.update_comment_status() and AppController.update_comment_text().

UI code in this file must NOT:
  - import or instantiate CommentRepository directly
  - execute SQLAlchemy queries
  - access SQLite

If no controller is provided (controller=None), the screen falls back to
app/mock_data.py COMMENTS for development/preview purposes. This fallback
must be replaced with live database data once a PDF has been loaded through
the normal upload flow.

MOCK DATA FALLBACK:
The mock_data fallback remains intentional during Week 3 development so the
application does not crash when the database contains no comments yet.
Once the OCR/AI pipeline populates the database, the fallback can be removed.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                                QLabel, QPushButton, QTextEdit, QComboBox,
                                QProgressBar, QSplitter, QSizePolicy,
                                QGraphicsView, QGraphicsScene, QScrollArea,
                                QInputDialog, QMessageBox, QLineEdit)
from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QFont, QPainter, QKeyEvent, QPixmap, QPen, QBrush, QColor

from app import mock_data as md
from app.components.chips import StatusChip, CategoryBadge
from app.components.pdf_canvas import make_page_pixmap, draw_bounding_boxes, BBoxItem
from app.screens.comment_viewer_screen import ZoomableGraphicsView

# Agreed status vocabulary — do not use any other values
_VALID_STATUSES = ("Pending", "Approved", "Rejected", "Flagged")


class _CommentAdapter:
    """Lightweight adapter that wraps comment dicts for BBoxItem compatibility."""
    def __init__(self, comment: Union[Dict[str, Any], Any]) -> None:
        if isinstance(comment, dict):
            self.id         = comment.get("id", "")
            self.status     = comment.get("status", "Pending")
            self.ocr_text   = comment.get("ocr_text", "")
            self.label      = comment.get("label", "comment_red")
            self.confidence = comment.get("confidence", 0.0)
        else:
            self.id         = getattr(comment, "id", "")
            self.status     = getattr(comment, "status", "Pending")
            self.ocr_text   = getattr(comment, "ocr_text", "")
            self.label      = getattr(comment, "label", "comment_red")
            self.confidence = getattr(comment, "confidence", 0.0)


def _get(c: Union[Dict[str, Any], Any], field: str, default: Any = "") -> Any:
    """Access a field from either a normalised display dict or a mock dataclass."""
    if isinstance(c, dict):
        return c.get(field, default)
    return getattr(c, field, default)


class HumanReviewPage(QWidget):
    """
    Human Verification — PDF canvas + review panel with Approve / Reject /
    Edit actions and keyboard navigation.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller

        # Load comments: prefer database, fall back to mock data
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
<<<<<<< HEAD
            self._all_comments: List[Any] = db_comments if db_comments else []
        elif self._controller:
            self._all_comments = []
=======
            self._comments: List[Any] = db_comments if db_comments else list(md.COMMENTS)
>>>>>>> origin/feature/ui-overhaul
        else:
            self._all_comments = list(md.COMMENTS)

        self._comments: List[Any] = list(self._all_comments)
        self._current_filter: str = "Needs Attention"
        self._is_all_auto_approved_notice: bool = False
        self._idx     = 0
        self._box_items: Dict[str, BBoxItem] = {}
        self._current_canvas_page: Optional[int] = None

        # In-memory status cache: updated immediately on action, persisted via controller
        self._statuses: Dict[str, str] = {
            _get(c, "id"): _get(c, "status", "Pending")
            for c in self._all_comments
        }
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Splitter ──────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet("QSplitter::handle { background-color: #E2E8F0; }")

        # Left — PDF canvas container with interactive zoom toolbar
        canvas_container = QWidget()
        canvas_lay = QVBoxLayout(canvas_container)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(0)

        self._canvas_toolbar = self._build_canvas_toolbar()
        canvas_lay.addWidget(self._canvas_toolbar)

        self._scene = QGraphicsScene()
        self._view  = ZoomableGraphicsView(self._scene)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
<<<<<<< HEAD
        self._view.zoom_changed.connect(self._on_canvas_zoom_changed)
        canvas_lay.addWidget(self._view, 1)

=======
        self._view.setStyleSheet("QGraphicsView { background-color: #F8FAFC; border: none; }")
>>>>>>> origin/feature/ui-overhaul
        self._load_canvas()
        splitter.addWidget(canvas_container)

        # Right — review panel
        self._panel = self._build_review_panel()
        splitter.addWidget(self._panel)
        splitter.setStretchFactor(0, 58)
        splitter.setStretchFactor(1, 42)

        root.addWidget(splitter)
        self._apply_filter()

    def reload_drawings(self) -> None:
        """Populate drawing selector dropdown in canvas toolbar."""
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

    def _on_drawing_scope_changed(self, index: int) -> None:
        dwg_id = self._dwg_filt.itemData(index)
        if dwg_id == "ALL":
            drawings = self._controller.get_all_drawings() if self._controller else []
            all_cmts = []
            for d in drawings:
                did = d.get("id")
                if did:
                    all_cmts.extend(self._controller.get_comments_for_drawing(did))
            self._all_comments = all_cmts
            self._statuses = {c["id"]: c["status"] for c in self._all_comments}
            self._apply_filter()
        elif dwg_id and self._controller and dwg_id != self._controller.current_drawing_id:
            self._controller.switch_current_drawing(dwg_id)
        else:
            self.reload_comments()

    def reload_comments(self) -> None:
        """
        Reload comments from the database for the currently loaded drawing.

        Call this method after uploading a new PDF or after the OCR pipeline
        populates comments, so the review screen reflects the latest data.
        """
        self.reload_drawings()
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._all_comments = db_comments if db_comments else []
            self._statuses = {
                c["id"]: c["status"] for c in self._all_comments
            }
            self._apply_filter()

    def _apply_filter(self, keep_comment_id: Optional[str] = None) -> None:
        """Filter self._comments from self._all_comments according to selected view filter."""
        flt = getattr(self, "_current_filter", "Needs Attention")

        if flt == "Needs Attention":
            # Show comments that need review: Pending, Flagged, or confidence < 0.85 (excluding Rejected)
            filtered = [
                c for c in self._all_comments
                if self._statuses.get(_get(c, "id"), _get(c, "status", "Pending")) in ("Pending", "Flagged")
                or (_get(c, "confidence", 0.0) < 0.85 and self._statuses.get(_get(c, "id"), _get(c, "status")) != "Rejected")
            ]
            if not filtered and self._all_comments:
                self._comments = list(self._all_comments)
                self._is_all_auto_approved_notice = True
            else:
                self._comments = filtered
                self._is_all_auto_approved_notice = False
        elif flt == "All Comments":
            self._comments = list(self._all_comments)
            self._is_all_auto_approved_notice = False
        elif flt == "Approved":
            self._comments = [
                c for c in self._all_comments
                if self._statuses.get(_get(c, "id"), _get(c, "status", "Pending")) == "Approved"
            ]
            self._is_all_auto_approved_notice = False
        elif flt == "Pending":
            self._comments = [
                c for c in self._all_comments
                if self._statuses.get(_get(c, "id"), _get(c, "status", "Pending")) == "Pending"
            ]
            self._is_all_auto_approved_notice = False
        elif flt == "Rejected":
            self._comments = [
                c for c in self._all_comments
                if self._statuses.get(_get(c, "id"), _get(c, "status", "Pending")) == "Rejected"
            ]
            self._is_all_auto_approved_notice = False
        elif flt == "Flagged":
            self._comments = [
                c for c in self._all_comments
                if self._statuses.get(_get(c, "id"), _get(c, "status", "Pending")) == "Flagged"
            ]
            self._is_all_auto_approved_notice = False
        else:
            self._comments = list(self._all_comments)
            self._is_all_auto_approved_notice = False

        if keep_comment_id:
            found_idx = next(
                (i for i, c in enumerate(self._comments) if _get(c, "id") == keep_comment_id),
                0
            )
            self._idx = found_idx
        else:
            self._idx = 0

        if hasattr(self, "_prog_bar"):
            self._prog_bar.setRange(0, max(1, len(self._comments)))
            self._prog_bar.setValue(min(self._idx + 1, len(self._comments)))

        self._load_canvas()
        self._load_comment()

    def _on_filter_changed(self, text: str) -> None:
        self._current_filter = text
        cid = _get(self._comments[self._idx], "id") if self._comments and self._idx < len(self._comments) else None
        self._apply_filter(keep_comment_id=cid)

    def _build_canvas_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            "QFrame { background-color: #1E2024; border-bottom: 1px solid #3A3C42; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)

        # Zoom controls
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setObjectName("SecondaryBtn")
        zoom_out_btn.setFixedSize(30, 30)
        zoom_out_btn.setToolTip("Zoom Out (or Ctrl + Wheel Down)")
        zoom_out_btn.clicked.connect(lambda: self._view.zoom_by_factor(1.0 / 1.2))
        lay.addWidget(zoom_out_btn)

        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setObjectName("SubCaption")
        self._zoom_lbl.setFixedWidth(46)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_lbl.setToolTip("Click to reset zoom to 100%")
        self._zoom_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._zoom_lbl.mousePressEvent = lambda e: self._view.reset_zoom()
        lay.addWidget(self._zoom_lbl)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setObjectName("SecondaryBtn")
        zoom_in_btn.setFixedSize(30, 30)
        zoom_in_btn.setToolTip("Zoom In (or Ctrl + Wheel Up)")
        zoom_in_btn.clicked.connect(lambda: self._view.zoom_by_factor(1.2))
        lay.addWidget(zoom_in_btn)

        fit_comment_btn = QPushButton("⛶  Fit Comment")
        fit_comment_btn.setObjectName("SecondaryBtn")
        fit_comment_btn.setFixedHeight(30)
        fit_comment_btn.setToolTip("Zoom and center on active comment bounding box")
        fit_comment_btn.clicked.connect(self._highlight_current_box)
        lay.addWidget(fit_comment_btn)

        fit_page_btn = QPushButton("📄  Fit Page")
        fit_page_btn.setObjectName("SecondaryBtn")
        fit_page_btn.setFixedHeight(30)
        fit_page_btn.setToolTip("Fit entire page to view")
        fit_page_btn.clicked.connect(self._fit_page_in_view)
        lay.addWidget(fit_page_btn)

        rotate_btn = QPushButton("⟳  Rotate")
        rotate_btn.setObjectName("SecondaryBtn")
        rotate_btn.setFixedHeight(30)
        rotate_btn.setToolTip("Rotate canvas clockwise by 90°")
        rotate_btn.clicked.connect(lambda: self._view.rotate(90))
        lay.addWidget(rotate_btn)

        lay.addStretch()

        self._dwg_filt = QComboBox()
        self._dwg_filt.setFixedHeight(28)
        self._dwg_filt.setFixedWidth(210)
        self._dwg_filt.setStyleSheet("QComboBox { background: #15171C; color: #38BDF8; font-size: 11px; border: 1px solid #3A3C42; border-radius: 4px; padding: 2px 6px; font-family: 'Cascadia Code'; }")
        self._dwg_filt.currentIndexChanged.connect(self._on_drawing_scope_changed)
        lay.addWidget(self._dwg_filt)

        self._canvas_page_lbl = QLabel("Page 1")
        self._canvas_page_lbl.setFont(QFont("Cascadia Code", 11))
        self._canvas_page_lbl.setStyleSheet("color: #94A3B8;")
        lay.addWidget(self._canvas_page_lbl)

        return bar

    def _on_canvas_zoom_changed(self, zoom: float) -> None:
        if hasattr(self, "_zoom_lbl"):
            self._zoom_lbl.setText(f"{int(zoom * 100)}%")

    def _fit_page_in_view(self) -> None:
        rect = self._scene.sceneRect()
        if not rect.isEmpty():
            self._view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            if hasattr(self._view, "_current_zoom"):
                self._view._current_zoom = self._view.transform().m11()
                self._on_canvas_zoom_changed(self._view._current_zoom)

    def select_comment_by_id(self, cid: str) -> bool:
        """
        Navigate directly to the comment with the given ID.
        If the comment is not in the current filtered view, resets the filter to 'All Comments'
        so the target comment is displayed.
        Returns True if found, False otherwise.
        """
        if not cid:
            return False
        cid_clean = str(cid).strip()

        # Check in self._comments first (under current filter)
        for i, c in enumerate(self._comments):
            if _get(c, "id") == cid_clean:
                self._idx = i
                self._load_canvas()
                self._load_comment()
                self._flash_card("#38BDF8")
                return True

        # Check in self._all_comments (in case current filter excluded it)
        for i, c in enumerate(self._all_comments):
            if _get(c, "id") == cid_clean:
                if hasattr(self, "_filter_cb"):
                    self._filter_cb.blockSignals(True)
                    self._filter_cb.setCurrentText("All Comments")
                    self._current_filter = "All Comments"
                    self._filter_cb.blockSignals(False)
                self._apply_filter(keep_comment_id=cid_clean)
                self._flash_card("#38BDF8")
                return True

        # Check across all drawings in database via controller
        if self._controller:
            drawings = self._controller.get_all_drawings()
            for d in drawings:
                did = d.get("id")
                if not did or did == self._controller.current_drawing_id:
                    continue
                cmts = self._controller.get_comments_for_drawing(did)
                if any(_get(c, "id") == cid_clean for c in cmts):
                    self._controller.switch_current_drawing(did)
                    for i, c in enumerate(self._all_comments):
                        if _get(c, "id") == cid_clean:
                            if hasattr(self, "_filter_cb"):
                                self._filter_cb.blockSignals(True)
                                self._filter_cb.setCurrentText("All Comments")
                                self._current_filter = "All Comments"
                                self._filter_cb.blockSignals(False)
                            self._apply_filter(keep_comment_id=cid_clean)
                            self._flash_card("#38BDF8")
                            return True

        return False

    def _on_search_id_submitted(self) -> None:
        query = self._id_search_input.text().strip()
        if not query:
            return

        query_upper = query.upper()

        # 1. Exact ID match (case-insensitive)
        for c in self._all_comments:
            cid = str(_get(c, "id", "")).strip()
            if cid.upper() == query_upper:
                self.select_comment_by_id(cid)
                return

        # 2. Substring match on ID (e.g. "P1-01" or "01")
        for c in self._all_comments:
            cid = str(_get(c, "id", "")).strip()
            if query_upper in cid.upper():
                self.select_comment_by_id(cid)
                return

        # 3. Numeric match (e.g. "1" matches "CMT-P1-01" or "CMT-001")
        if query.isdigit():
            q_num = int(query)
            for c in self._all_comments:
                cid = str(_get(c, "id", "")).strip()
                if (
                    cid.endswith(f"-{q_num:02d}")
                    or cid.endswith(f"-{q_num:03d}")
                    or cid.endswith(f"-{q_num}")
                ):
                    self.select_comment_by_id(cid)
                    return

        # 4. OCR text search
        for c in self._all_comments:
            txt = str(_get(c, "ocr_text", "")).lower()
            if query.lower() in txt:
                self.select_comment_by_id(_get(c, "id"))
                return

        # Visual feedback: flash red if not found
        orig_style = self._id_search_input.styleSheet()
        self._id_search_input.setStyleSheet(
            orig_style + " QLineEdit { border: 1px solid #EF4444; }"
        )
        QTimer.singleShot(800, lambda: self._id_search_input.setStyleSheet(orig_style))

    # ── Panel builder ─────────────────────────────────────────────

    def _build_review_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #FFFFFF; border-left: 1px solid #E2E8F0; }")

        panel = QFrame()
        panel.setObjectName("ReviewPanel")
        panel.setStyleSheet("#ReviewPanel { background: #FFFFFF; border: none; }")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 20, 20, 20)
<<<<<<< HEAD
        lay.setSpacing(12)

        # Quick Search Bar Row
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self._id_search_input = QLineEdit()
        self._id_search_input.setPlaceholderText("🔍 Search Comment ID (e.g. CMT-P1-01, P1-01, 1)...")
        self._id_search_input.setFixedHeight(34)
        self._id_search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1E222B;
                color: #F2F3F5;
                border: 1px solid #3A3C42;
                border-radius: 6px;
                padding: 0 10px;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #3E9BFF;
                background-color: #242832;
            }
        """)
        self._id_search_input.returnPressed.connect(self._on_search_id_submitted)
        search_row.addWidget(self._id_search_input, 1)

        search_btn = QPushButton("Go")
        search_btn.setObjectName("SecondaryBtn")
        search_btn.setFixedHeight(34)
        search_btn.setFixedWidth(50)
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self._on_search_id_submitted)
        search_row.addWidget(search_btn)

        lay.addLayout(search_row)
=======
        lay.setSpacing(16)
>>>>>>> origin/feature/ui-overhaul

        # Queue Header & Overall Progress Status
        q_label = QLabel("QUEUE VERIFICATION")
        q_label.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        q_label.setStyleSheet("color: #64748B; letter-spacing: 0.8px;")
        lay.addWidget(q_label)

        top_prog_row = QHBoxLayout()
        title_lbl = QLabel("Comment Review Queue")
        title_lbl.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #0F172A;")
        top_prog_row.addWidget(title_lbl)
        top_prog_row.addStretch()

        self._completion_badge = QLabel("0% Completed")
        self._completion_badge.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        self._completion_badge.setStyleSheet("color: #0284C7; background-color: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 10px; padding: 2px 8px;")
        top_prog_row.addWidget(self._completion_badge)
        lay.addLayout(top_prog_row)

        sub_prog_row = QHBoxLayout()
        self._prog_lbl = QLabel("Comment 1 of 0")
<<<<<<< HEAD
        self._prog_lbl.setFont(QFont("Segoe UI Variable", 14, QFont.Weight.DemiBold))
        prog_hdr.addWidget(self._prog_lbl)
        prog_hdr.addStretch()

        filter_lbl = QLabel("View:")
        filter_lbl.setObjectName("SubCaption")
        prog_hdr.addWidget(filter_lbl)

        self._filter_cb = QComboBox()
        self._filter_cb.setFixedHeight(30)
        self._filter_cb.setMinimumWidth(155)
        self._filter_cb.addItems([
            "Needs Attention",
            "All Comments",
            "Approved",
            "Pending",
            "Rejected",
            "Flagged",
        ])
        self._filter_cb.currentTextChanged.connect(self._on_filter_changed)
        prog_hdr.addWidget(self._filter_cb)
        lay.addLayout(prog_hdr)
=======
        self._prog_lbl.setFont(QFont("Inter", 10, QFont.Weight.Medium))
        self._prog_lbl.setStyleSheet("color: #475569;")
        sub_prog_row.addWidget(self._prog_lbl)
        sub_prog_row.addStretch()

        self._remaining_lbl = QLabel("0 Remaining")
        self._remaining_lbl.setFont(QFont("Inter", 10))
        self._remaining_lbl.setStyleSheet("color: #94A3B8;")
        sub_prog_row.addWidget(self._remaining_lbl)
        lay.addLayout(sub_prog_row)
>>>>>>> origin/feature/ui-overhaul

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, max(len(self._comments), 1))
        self._prog_bar.setValue(1)
        self._prog_bar.setFixedHeight(4)
        self._prog_bar.setTextVisible(False)
        self._prog_bar.setStyleSheet(
            "QProgressBar { background: #F1F5F9; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: #0284C7; border-radius: 2px; }"
        )
        lay.addWidget(self._prog_bar)

        # Comment Details Container Card
        self._edit_card = QFrame()
        self._edit_card.setObjectName("Card")
        self._edit_card.setStyleSheet(
            "#Card { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        edit_lay = QVBoxLayout(self._edit_card)
        edit_lay.setContentsMargins(16, 16, 16, 16)
        edit_lay.setSpacing(14)

        # Top Tag Chips & Status Pill
        meta_top_row = QHBoxLayout()
        meta_top_row.setSpacing(6)

        self._cid_chip = QLabel("")
        self._cid_chip.setFont(QFont("Cascadia Code", 9, QFont.Weight.Bold))
        self._cid_chip.setStyleSheet("color: #0284C7; background-color: #E0F2FE; border-radius: 4px; padding: 2px 6px;")
        meta_top_row.addWidget(self._cid_chip)

        self._cr_chip = QLabel("")
        self._cr_chip.setFont(QFont("Cascadia Code", 9, QFont.Weight.Bold))
        self._cr_chip.setStyleSheet("color: #475569; background-color: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 4px; padding: 2px 6px;")
        meta_top_row.addWidget(self._cr_chip)

        meta_top_row.addStretch()

        self._status_chip = StatusChip("Pending")
        meta_top_row.addWidget(self._status_chip)
        edit_lay.addLayout(meta_top_row)

        self._comment_id_lbl = QLabel("")
        self._comment_id_lbl.setFont(QFont("Inter", 10, QFont.Weight.Medium))
        self._comment_id_lbl.setStyleSheet("color: #334155; line-height: 1.4;")
        edit_lay.addWidget(self._comment_id_lbl)

        # AI Confidence & Discipline Classification Block
        conf_cat_frame = QFrame()
        conf_cat_frame.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 12px;")
        conf_cat_lay = QVBoxLayout(conf_cat_frame)
        conf_cat_lay.setContentsMargins(0, 0, 0, 0)
        conf_cat_lay.setSpacing(8)

        metrics_hdr_row = QHBoxLayout()
        conf_hdr = QLabel("ACCURACY CONFIDENCE")
        conf_hdr.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        conf_hdr.setStyleSheet("color: #64748B; letter-spacing: 0.5px;")
        metrics_hdr_row.addWidget(conf_hdr)

        metrics_hdr_row.addStretch()

<<<<<<< HEAD
        cat_row = QHBoxLayout()
        cat_row.setSpacing(6)
        self._cat_combo = QComboBox()
        db_cats = [c.get("name") for c in self._controller.get_all_categories()] if self._controller else []
        self._cat_combo.addItems(db_cats if db_cats else list(md.CATEGORIES))
        self._cat_combo.setFixedHeight(36)
        self._cat_combo.currentTextChanged.connect(self._on_category_changed)
        cat_row.addWidget(self._cat_combo, 1)

        self._quick_add_cat_btn = QPushButton("➕")
        self._quick_add_cat_btn.setFixedSize(36, 36)
        self._quick_add_cat_btn.setToolTip("Add new error category for this drawing's department")
        self._quick_add_cat_btn.setStyleSheet("""
            QPushButton {
                background-color: #1E222B;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0284C722;
                border-color: #38BDF8;
            }
        """)
        self._quick_add_cat_btn.clicked.connect(self._on_quick_add_category)
        cat_row.addWidget(self._quick_add_cat_btn)
        edit_lay.addLayout(cat_row)
=======
        cat_lbl = QLabel("DISCIPLINE CLASSIFICATION")
        cat_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        cat_lbl.setStyleSheet("color: #64748B; letter-spacing: 0.5px;")
        metrics_hdr_row.addWidget(cat_lbl)
        conf_cat_lay.addLayout(metrics_hdr_row)

        metrics_val_row = QHBoxLayout()
        metrics_val_row.setSpacing(16)

        # AI Accuracy Block
        conf_block = QVBoxLayout()
        conf_block.setSpacing(4)
        self._conf_lbl = QLabel("—")
        self._conf_lbl.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        self._conf_lbl.setStyleSheet("color: #0F172A;")
        conf_block.addWidget(self._conf_lbl)

        self._conf_bar = QProgressBar()
        self._conf_bar.setRange(0, 100)
        self._conf_bar.setValue(90)
        self._conf_bar.setFixedHeight(4)
        self._conf_bar.setTextVisible(False)
        self._conf_bar.setStyleSheet(
            "QProgressBar { background: #E2E8F0; border-radius: 2px; }"
            "QProgressBar::chunk { background: #0284C7; border-radius: 2px; }"
        )
        conf_block.addWidget(self._conf_bar)

        self._match_tag = QLabel("High Precision Match")
        self._match_tag.setFont(QFont("Inter", 8, QFont.Weight.Medium))
        self._match_tag.setStyleSheet("color: #64748B;")
        conf_block.addWidget(self._match_tag)
        metrics_val_row.addLayout(conf_block, 1)

        # Discipline Classification Selector
        cat_block = QVBoxLayout()
        cat_block.setSpacing(4)
        
        cat_select_row = QHBoxLayout()
        cat_select_row.setSpacing(6)
        self._cat_combo = QComboBox()
        self._cat_combo.addItems(md.CATEGORIES)
        self._cat_combo.setFixedHeight(28)
        self._cat_combo.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 2px 6px; font-size: 11px; color: #1E293B; }"
            "QComboBox::drop-down { border: none; }"
        )
        self._cat_combo.currentTextChanged.connect(self._on_category_changed)
        cat_select_row.addWidget(self._cat_combo, 1)
>>>>>>> origin/feature/ui-overhaul

        self._cat_badge = CategoryBadge("")
        cat_select_row.addWidget(self._cat_badge)
        cat_block.addLayout(cat_select_row)

        self._rule_lbl = QLabel("Anchor Embedment Mandate")
        self._rule_lbl.setFont(QFont("Inter", 8))
        self._rule_lbl.setStyleSheet("color: #64748B;")
        cat_block.addWidget(self._rule_lbl)

        metrics_val_row.addLayout(cat_block, 1)
        conf_cat_lay.addLayout(metrics_val_row)
        edit_lay.addWidget(conf_cat_frame)

        # Extracted Text Section
        ocr_hdr_row = QHBoxLayout()
        ocr_lbl = QLabel("Extracted Drawing Annotation Text")
        ocr_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        ocr_lbl.setStyleSheet("color: #1E293B;")
        ocr_hdr_row.addWidget(ocr_lbl)
        ocr_hdr_row.addStretch()

        self._copy_ocr_btn = QPushButton("Copy OCR")
        self._copy_ocr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_ocr_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #0284C7; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { color: #0369A1; text-decoration: underline; }"
        )
        ocr_hdr_row.addWidget(self._copy_ocr_btn)
        edit_lay.addLayout(ocr_hdr_row)

        self._ocr_edit = QTextEdit()
        self._ocr_edit.setMinimumHeight(75)
        self._ocr_edit.setReadOnly(True)
        self._ocr_edit.setFont(QFont("Cascadia Code", 9))
        self._ocr_edit.setStyleSheet(
            "QTextEdit { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; color: #0F172A; padding: 8px; }"
        )
        edit_lay.addWidget(self._ocr_edit)

        # OCR Engine Metadata Info
        ocr_meta_row = QHBoxLayout()
        engine_lbl = QLabel("OCR Engine: Gemini Vision Pro 2.5")
        engine_lbl.setFont(QFont("Inter", 8))
        engine_lbl.setStyleSheet("color: #94A3B8;")
        ocr_meta_row.addWidget(engine_lbl)
        ocr_meta_row.addStretch()

        cer_lbl = QLabel("Tokens: 31 • CER: 0.02%")
        cer_lbl.setFont(QFont("Inter", 8))
        cer_lbl.setStyleSheet("color: #94A3B8;")
        ocr_meta_row.addWidget(cer_lbl)
        edit_lay.addLayout(ocr_meta_row)

        lay.addWidget(self._edit_card)

<<<<<<< HEAD
        # Status indicator
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Current Status:"))
        self._status_chip = StatusChip("Pending")
        status_row.addWidget(self._status_chip)

        self._auto_approved_badge = QLabel("🤖 Auto-Approved (AI)")
        self._auto_approved_badge.setStyleSheet(
            "background: rgba(62, 155, 255, 0.15); color: #3E9BFF; border: 1px solid rgba(62, 155, 255, 0.35); "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        self._auto_approved_badge.hide()
        status_row.addWidget(self._auto_approved_badge)

        status_row.addStretch()
        lay.addLayout(status_row)

        # Audit history collapsible panel
=======
        # Audit Log Collapsible Box
>>>>>>> origin/feature/ui-overhaul
        self._audit_card = QFrame()
        self._audit_card.setObjectName("Card")
        self._audit_card.setStyleSheet(
            "#Card { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        audit_lay = QVBoxLayout(self._audit_card)
        audit_lay.setContentsMargins(12, 10, 12, 10)
        audit_lay.setSpacing(6)

        audit_hdr_row = QHBoxLayout()
        self._audit_toggle_btn = QPushButton("▼  Audit History & Traceability Log")
        self._audit_toggle_btn.setObjectName("GhostBtn")
        self._audit_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._audit_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; font-weight: 600; font-size: 11px; color: #475569; padding: 0px; border: none; background: transparent; }"
            "QPushButton:hover { color: #0284C7; }"
        )
        self._audit_toggle_btn.clicked.connect(self._toggle_audit_panel)
        audit_hdr_row.addWidget(self._audit_toggle_btn)
        audit_hdr_row.addStretch()
        audit_lay.addLayout(audit_hdr_row)

        self._audit_container = QWidget()
        self._audit_items_lay = QVBoxLayout(self._audit_container)
        self._audit_items_lay.setContentsMargins(0, 4, 0, 0)
        self._audit_items_lay.setSpacing(6)

        self._audit_scroll = QScrollArea()
        self._audit_scroll.setWidgetResizable(True)
        self._audit_scroll.setWidget(self._audit_container)
        self._audit_scroll.setMaximumHeight(130)
        self._audit_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QWidget { background: transparent; }"
        )
        audit_lay.addWidget(self._audit_scroll)
        lay.addWidget(self._audit_card)

        # Decision Actions Panel
        decision_box = QVBoxLayout()
        decision_box.setSpacing(8)

        decision_title = QLabel("REVIEW DECISION")
        decision_title.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        decision_title.setStyleSheet("color: #64748B; letter-spacing: 0.5px;")
        decision_box.addWidget(decision_title)

        # Row 1: Reject & Flag buttons
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._reject_btn = QPushButton("✕   Reject")
        self._reject_btn.setMinimumHeight(38)
        self._reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reject_btn.setStyleSheet(
            "QPushButton { background: #FEF2F2; color: #DC2626; border: 1px solid #FCA5A5; border-radius: 6px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background: #FEE2E2; border-color: #F87171; }"
        )
        self._reject_btn.clicked.connect(self._reject)
        row1.addWidget(self._reject_btn, 1)

        self._flag_btn = QPushButton("⚐   Flag for Lead")
        self._flag_btn.setMinimumHeight(38)
        self._flag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._flag_btn.setStyleSheet(
            "QPushButton { background: #FFFBEB; color: #D97706; border: 1px solid #FDE68A; border-radius: 6px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background: #FEF3C7; border-color: #FCD34D; }"
        )
        self._flag_btn.clicked.connect(self._flag)
        row1.addWidget(self._flag_btn, 1)
        decision_box.addLayout(row1)

        # Row 2: Edit & Approve buttons
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self._edit_btn = QPushButton("✎   Edit Text")
        self._edit_btn.setMinimumHeight(38)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #334155; border: 1px solid #CBD5E1; border-radius: 6px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background: #F8FAFC; border-color: #94A3B8; }"
        )
        self._edit_btn.clicked.connect(self._toggle_edit)
        row2.addWidget(self._edit_btn, 1)

        self._approve_btn = QPushButton("✓   Approve & Sign Off")
        self._approve_btn.setMinimumHeight(38)
        self._approve_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._approve_btn.setStyleSheet(
            "QPushButton { background: #0284C7; color: #FFFFFF; border: 1px solid #0284C7; border-radius: 6px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background: #0369A1; border-color: #0369A1; }"
        )
        self._approve_btn.clicked.connect(self._approve)
        row2.addWidget(self._approve_btn, 1)
        decision_box.addLayout(row2)

        # Row 3: Prev / Next Navigation Controls
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self._prev_btn = QPushButton("<  Prev")
        self._prev_btn.setFixedHeight(32)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #475569; border: 1px solid #E2E8F0; border-radius: 6px; font-weight: 600; font-size: 11px; padding: 0 10px; }"
            "QPushButton:hover { background: #F8FAFC; border-color: #CBD5E1; }"
            "QPushButton:disabled { color: #CBD5E1; border-color: #F1F5F9; background: #FFFFFF; }"
        )
        self._prev_btn.clicked.connect(self._prev)
        nav_row.addWidget(self._prev_btn)

        nav_row.addStretch()

        self._item_counter_lbl = QLabel("Comment 1 / 0")
        self._item_counter_lbl.setFont(QFont("Inter", 9))
        self._item_counter_lbl.setStyleSheet("color: #64748B;")
        nav_row.addWidget(self._item_counter_lbl)

        nav_row.addStretch()

        self._next_btn = QPushButton("Next  >")
        self._next_btn.setFixedHeight(32)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #475569; border: 1px solid #E2E8F0; border-radius: 6px; font-weight: 600; font-size: 11px; padding: 0 10px; }"
            "QPushButton:hover { background: #F8FAFC; border-color: #CBD5E1; }"
            "QPushButton:disabled { color: #CBD5E1; border-color: #F1F5F9; background: #FFFFFF; }"
        )
        self._next_btn.clicked.connect(self._next)
        nav_row.addWidget(self._next_btn)
        decision_box.addLayout(nav_row)

        lay.addLayout(decision_box)

        # Keyboard Shortcut Legend
        hint = QLabel(
            "P Previous  •  R Reject  •  F Flag  •  A Approve  •  N Next"
        )
        hint.setObjectName("SubCaption")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #94A3B8; font-size: 10px; padding-top: 2px; font-weight: 500;")
        lay.addWidget(hint)

        lay.addStretch()
        scroll.setWidget(panel)
        return scroll

    # ── Canvas / comment helpers ──────────────────────────────────

    def _on_category_changed(self, new_cat: str) -> None:
        if not new_cat:
            return
        self._cat_badge.set_category(new_cat)
        if self._comments and self._idx < len(self._comments):
            c = self._comments[self._idx]
            cid = _get(c, "id", "")
            old_cat = _get(c, "category", "")
            if isinstance(c, dict):
                c["category"] = new_cat
            else:
                setattr(c, "category", new_cat)

            for ac in getattr(self, "_all_comments", []):
                if _get(ac, "id") == cid:
                    if isinstance(ac, dict):
                        ac["category"] = new_cat
                    else:
                        setattr(ac, "category", new_cat)
                    break

            if self._controller and cid and not cid.startswith("C-") and old_cat != new_cat:
                self._controller.update_comment_category(cid, new_cat)
                self._load_audit_trail(cid)

    def _refresh_cat_combo_items(self, dept_name: Optional[str], selected_cat: str) -> None:
        """Refresh _cat_combo items with department-scoped and universal categories."""
        self._cat_combo.blockSignals(True)
        self._cat_combo.clear()
        cats = []
        if self._controller and hasattr(self._controller, "get_categories_for_department"):
            try:
                cats = [item["name"] for item in self._controller.get_categories_for_department(dept_name)]
            except Exception:
                cats = []
        if not cats:
            cats = list(md.CATEGORIES)

        for cat in cats:
            self._cat_combo.addItem(cat)

        if selected_cat and self._cat_combo.findText(selected_cat) == -1:
            self._cat_combo.addItem(selected_cat)

        self._cat_combo.setCurrentText(selected_cat)
        self._cat_combo.blockSignals(False)

    def _on_quick_add_category(self) -> None:
        """Prompt reviewer to add a new category for this drawing's department."""
        dept_name = None
        if self._comments and self._idx < len(self._comments):
            c = self._comments[self._idx]
            dept_name = _get(c, "department", None)
        if (not dept_name or dept_name in ("Unassigned", "")) and self._controller:
            cur_dwg = self._controller.get_current_drawing()
            if cur_dwg:
                dept_name = cur_dwg.get("department_name")
        dept_label = f" for {dept_name}" if dept_name else ""

        name, ok = QInputDialog.getText(
            self,
            "Add Error Category",
            f"Enter new error category name{dept_label}:",
            QLineEdit.EchoMode.Normal,
            "",
        )
        if ok and name.strip():
            cat_name = name.strip()
            if self._controller:
                self._controller.add_category(name=cat_name, department_name=dept_name)
            if self._cat_combo.findText(cat_name) == -1:
                self._cat_combo.addItem(cat_name)
            self._cat_combo.setCurrentText(cat_name)

    def _on_box_clicked(self, cid: str) -> None:
        """Handle user clicking directly on a bounding box on the canvas."""
        for idx, c in enumerate(self._comments):
            if _get(c, "id") == cid:
                self._idx = idx
                self._load_comment()
                break

    def _load_canvas(self) -> None:
        self._scene.clear()
        self._box_items = {}

        if not self._comments:
            pm = make_page_pixmap(640, 820, comments=[])
            self._scene.addPixmap(pm)
            self._scene.setSceneRect(QRectF(pm.rect()))
            self._current_canvas_page = 1
            if hasattr(self, "_canvas_page_lbl"):
                self._canvas_page_lbl.setText("Page 1")
            return

        current_comment = self._comments[self._idx] if self._idx < len(self._comments) else self._comments[0]
        page_num = _get(current_comment, "page", 1)
        self._current_canvas_page = page_num
        if hasattr(self, "_canvas_page_lbl"):
            self._canvas_page_lbl.setText(f"Page {page_num}")

        page_comments = [
            c for c in self._comments
            if _get(c, "page", 1) == page_num
        ]

        if self._controller and self._controller.current_document:
            try:
                rendered_dto = self._controller.pdf_service.get_page_render(
                    self._controller.current_document.file_path, page_num, dpi=150
                )
                pm = QPixmap()
                pm.loadFromData(rendered_dto.image_bytes)
            except Exception:
                pm = make_page_pixmap(640, 820, comments=[])
        else:
            pm = make_page_pixmap(640, 820, comments=[])

        self._scene.addPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))

        from app.theme import CURRENT_THEME
        if CURRENT_THEME == 'dark':
            dim = self._scene.addRect(self._scene.sceneRect())
            dim.setBrush(QColor(0, 0, 0, 160))
            dim.setPen(Qt.PenStyle.NoPen)
            dim.setZValue(0.5)

        width = pm.width()
        height = pm.height()

        for c in page_comments:
            bbox   = _get(c, "bbox", (0, 0, 0, 0))
            cid    = _get(c, "id", "")
            
            x = bbox[0] * width
            y = bbox[1] * height
            w = bbox[2] * width
            h = bbox[3] * height

            adapter = _CommentAdapter(c)
            item = BBoxItem(adapter, QRectF(x, y, w, h), on_click=self._on_box_clicked)
            self._scene.addItem(item)
            self._box_items[cid] = item

    def _highlight_current_box(self) -> None:
        """Visually highlight the active comment box and pan/zoom directly onto it."""
        if not self._comments or self._idx >= len(self._comments):
            return

        c = self._comments[self._idx]
        cid = _get(c, "id", "")
        page_num = _get(c, "page", 1)

        # Reload canvas if comment is on a different page or boxes not yet built
        if self._current_canvas_page != page_num or cid not in self._box_items:
            self._load_canvas()

        # Update visual styles across all boxes on the active page
        for bid, item in self._box_items.items():
            if bid == cid:
                # Active highlight: vibrant cyan/blue glowing border with high z-index
                active_pen = QPen(QColor("#0284C7"), 2.5)
                active_pen.setStyle(Qt.PenStyle.SolidLine)
                item.setPen(active_pen)
                fill_color = QColor("#0284C7")
                fill_color.setAlphaF(0.12)
                item.setBrush(QBrush(fill_color))
                item.setZValue(10)
            else:
                # Inactive boxes: standard subtle styling
                label = _get(item.comment, "label", "")
                status = _get(item.comment, "status", "Pending")
                if "blue" in str(label).lower() or str(label) in ("comment_blue", "native_blue_markup"):
                    col_hex = "#0284C7"
                elif "yellow" in str(label).lower():
                    col_hex = "#D97706"
                elif "green" in str(label).lower():
                    col_hex = "#059669"
                elif status == "Approved":
                    col_hex = "#16A34A"
                else:
                    col_hex = "#DC2626"

                normal_pen = QPen(QColor(col_hex), 1.5)
                normal_pen.setStyle(Qt.PenStyle.DashLine)
                item.setPen(normal_pen)
                fill_color = QColor(col_hex)
                fill_color.setAlphaF(0.05)
                item.setBrush(QBrush(fill_color))
                item.setZValue(1)

        # Auto-pan & zoom into the active bounding box
        if cid in self._box_items:
            rect = self._box_items[cid].sceneBoundingRect()
            if not rect.isEmpty() and rect.width() > 0 and rect.height() > 0:
                target_rect = rect.adjusted(-120, -120, 120, 120)
                self._view.fitInView(target_rect, Qt.AspectRatioMode.KeepAspectRatio)
                if hasattr(self._view, "_current_zoom"):
                    self._view._current_zoom = self._view.transform().m11()
                    self._on_canvas_zoom_changed(self._view._current_zoom)

    def _load_comment(self) -> None:
        if not self._comments:
<<<<<<< HEAD
            self._prog_lbl.setText("No comments in this view")
            self._prog_bar.setValue(0)
            self._comment_id_lbl.setText("")
            self._ocr_edit.setPlainText("")
            self._conf_lbl.setText("Confidence: —")
            self._cat_badge.set_category("")
            if hasattr(self, "_auto_approved_badge"):
                self._auto_approved_badge.hide()
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            self._approve_btn.setEnabled(False)
            self._reject_btn.setEnabled(False)
            self._flag_btn.setEnabled(False)
            self._edit_btn.setEnabled(False)
=======
            self._prog_lbl.setText("No comments available")
            self._item_counter_lbl.setText("Comment 0 / 0")
>>>>>>> origin/feature/ui-overhaul
            return

        self._approve_btn.setEnabled(True)
        self._reject_btn.setEnabled(True)
        self._flag_btn.setEnabled(True)
        self._edit_btn.setEnabled(True)

        total = len(self._comments)
        self._idx = max(0, min(self._idx, total - 1))
        c     = self._comments[self._idx]
        cid   = _get(c, "id", "")

<<<<<<< HEAD
        notice = " (Auto-Approved Drawing)" if getattr(self, "_is_all_auto_approved_notice", False) else ""
        self._prog_lbl.setText(f"Comment {self._idx + 1} of {total}{notice}")
=======
        self._prog_lbl.setText(f"Comment {self._idx + 1} of {total} items")
        self._item_counter_lbl.setText(f"Comment {self._idx + 1} / {total}")
        self._remaining_lbl.setText(f"{total - (self._idx + 1)} Remaining")
        
        perc = int(((self._idx + 1) / max(1, total)) * 100)
        self._completion_badge.setText(f"{perc}% Completed")
>>>>>>> origin/feature/ui-overhaul
        self._prog_bar.setValue(self._idx + 1)

        drawing_ref = _get(c, "drawing_no", _get(c, "drawing_id", ""))
        page_ref    = _get(c, "page", 1)
        
        self._cid_chip.setText(f"#{cid}")
        self._cr_chip.setText(f"# CR-STRUCT-{9900 + self._idx}")
        self._comment_id_lbl.setText(f"📄  {drawing_ref or 'HY_Tower_Core_Structural_S101_S140.pdf'}\n    Sheet S-204 (Page {page_ref}) • Grid Quadrant D-3")

        self._ocr_edit.setPlainText(_get(c, "ocr_text", ""))
        category = _get(c, "category", "Dimensional")
        dept_name = _get(c, "department", None)
        if (not dept_name or dept_name in ("Unassigned", "")) and self._controller:
            cur_dwg = self._controller.get_current_drawing()
            if cur_dwg:
                dept_name = cur_dwg.get("department_name")

        self._refresh_cat_combo_items(dept_name, category)
        self._cat_badge.set_category(category)

        confidence = _get(c, "confidence", 0.0)
<<<<<<< HEAD
        self._conf_lbl.setText(f"Confidence: {int(confidence * 100)}%")
        cur_status = self._statuses.get(cid, _get(c, "status", "Pending"))
        self._status_chip.set_status(cur_status)

        is_human = _get(c, "is_verified_by_human", False)
        if cur_status == "Approved" and not is_human and hasattr(self, "_auto_approved_badge"):
            self._auto_approved_badge.show()
        elif hasattr(self, "_auto_approved_badge"):
            self._auto_approved_badge.hide()
=======
        conf_val = confidence if confidence > 1.0 else confidence * 100
        self._conf_lbl.setText(f"{conf_val:.1f}%")
        if hasattr(self, "_conf_bar"):
            self._conf_bar.setValue(int(conf_val))
        self._status_chip.set_status(self._statuses.get(cid, _get(c, "status", "Pending")))
>>>>>>> origin/feature/ui-overhaul

        self._prev_btn.setEnabled(self._idx > 0)
        self._next_btn.setEnabled(self._idx < total - 1)

        self._load_audit_trail(cid)
        self._highlight_current_box()

    def _flash_card(self, color: str) -> None:
        orig = self._edit_card.styleSheet()
        self._edit_card.setStyleSheet(
            f"#Card {{ background: #FFFFFF; border: 2px solid {color}; border-radius: 8px; }}"
        )
        QTimer.singleShot(350, lambda: self._edit_card.setStyleSheet(orig))

    def _toggle_audit_panel(self) -> None:
        is_visible = self._audit_scroll.isVisible()
        self._audit_scroll.setVisible(not is_visible)
        count_text = self._audit_toggle_btn.text().split("Audit History")[-1]
        prefix = "▶" if is_visible else "▼"
        self._audit_toggle_btn.setText(f"{prefix}  Audit History{count_text}")

    def _build_audit_row(self, entry: Any) -> QWidget:
        row_frame = QFrame()
        row_frame.setStyleSheet(
            "QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; }"
        )
        row_lay = QHBoxLayout(row_frame)
        row_lay.setContentsMargins(8, 5, 8, 5)
        row_lay.setSpacing(6)

        # Bullet Indicator
        dot = QLabel("•")
        dot.setStyleSheet("color: #0284C7; font-size: 12px; font-weight: bold;")
        row_lay.addWidget(dot)

        text_block = QVBoxLayout()
        text_block.setSpacing(1)

        raw_action = str(_get(entry, "action", "action"))
        action_name = raw_action.replace("_", " ").title()
        user_id = _get(entry, "changed_by_user_id", "") or _get(entry, "reviewer_id", "") or "Elena Vance"

        user_lbl = QLabel(f"{user_id} {action_name.lower()}")
        user_lbl.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        user_lbl.setStyleSheet("color: #1E293B;")
        text_block.addWidget(user_lbl)

        details = _get(entry, "details", "") or _get(entry, "notes", "")
        if not details:
            old_v = _get(entry, "old_value", "")
            new_v = _get(entry, "new_value", "")
            if old_v or new_v:
                details = f"{old_v} → {new_v}"
        if not details:
            details = "Lead Structural Reviewer"

        ts = _get(entry, "timestamp", "")
        if hasattr(ts, "strftime"):
            ts_str = ts.strftime("%b %d, %H:%M")
        else:
            ts_str = str(ts) or "2 mins ago"

        det_lbl = QLabel(f"{details} • {ts_str}")
        det_lbl.setFont(QFont("Inter", 8))
        det_lbl.setStyleSheet("color: #64748B;")
        text_block.addWidget(det_lbl)

        row_lay.addLayout(text_block)
        return row_frame

    def _load_audit_trail(self, comment_id: str) -> None:
        # Clear previous items
        while self._audit_items_lay.count():
            item = self._audit_items_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        logs = []
        if self._controller:
            logs = self._controller.get_audit_trail(comment_id)

        if not logs:
            mock_entry = {
                "action": "Opened Comment",
                "reviewer_id": "Elena Vance, PE",
                "details": "Initiated human verification review",
                "timestamp": "2 mins ago"
            }
            logs = [mock_entry]

        for entry in logs:
            self._audit_items_lay.addWidget(self._build_audit_row(entry))

        count_str = f" ({len(logs)})"
        prefix = "▼" if self._audit_scroll.isVisible() else "▶"
        self._audit_toggle_btn.setText(f"{prefix}  Audit History & Traceability Log{count_str}")

    # ── Action logic ──────────────────────────────────────────────

    def _set_status(self, new_status: str, flash_color: str) -> None:
        if not self._comments:
            return

        c = self._comments[self._idx]
        cid = _get(c, "id", "")
        self._statuses[cid] = new_status

        # Update in-memory objects
        if isinstance(c, dict):
            c["status"] = new_status
            c["is_verified_by_human"] = True
        else:
            setattr(c, "status", new_status)
            setattr(c, "is_verified_by_human", True)

        for ac in getattr(self, "_all_comments", []):
            if _get(ac, "id") == cid:
                if isinstance(ac, dict):
                    ac["status"] = new_status
                    ac["is_verified_by_human"] = True
                else:
                    setattr(ac, "status", new_status)
                    setattr(ac, "is_verified_by_human", True)
                break

        if hasattr(self, "_auto_approved_badge"):
            self._auto_approved_badge.hide()

        if self._controller and cid and not cid.startswith("C-"):
            self._controller.update_comment_status(cid, new_status)
            self._load_audit_trail(cid)

        self._status_chip.set_status(new_status)
        self._flash_card(flash_color)
        self._highlight_current_box()

    def _approve(self) -> None:
        self._set_status("Approved", "#16A34A")

    def _reject(self) -> None:
        self._set_status("Rejected", "#DC2626")

    def _flag(self) -> None:
        self._set_status("Flagged", "#D97706")

    def _toggle_edit(self) -> None:
        is_readonly = self._ocr_edit.isReadOnly()
        if is_readonly:
            self._ocr_edit.setReadOnly(False)
            self._ocr_edit.setFocus()
            self._edit_btn.setText("💾   Save Text")
            self._edit_btn.setStyleSheet(
                "QPushButton { background: #0284C7; color: #FFFFFF; border: 1px solid #0284C7; border-radius: 6px; font-weight: 600; font-size: 12px; }"
                "QPushButton:hover { background: #0369A1; border-color: #0369A1; }"
            )
        else:
            new_text = self._ocr_edit.toPlainText().strip()
            self._ocr_edit.setReadOnly(True)
            self._edit_btn.setText("✎   Edit Text")
            self._edit_btn.setStyleSheet(
                "QPushButton { background: #FFFFFF; color: #334155; border: 1px solid #CBD5E1; border-radius: 6px; font-weight: 600; font-size: 12px; }"
                "QPushButton:hover { background: #F8FAFC; border-color: #94A3B8; }"
            )

            if self._comments:
                c = self._comments[self._idx]
                cid = _get(c, "id", "")
                if isinstance(c, dict):
                    c["ocr_text"] = new_text
                else:
                    setattr(c, "ocr_text", new_text)

                if self._controller:
                    self._controller.update_comment_text(cid, new_text)

    def _prev(self) -> None:
        if self._idx > 0:
            self._idx -= 1
            self._load_comment()

    def _next(self) -> None:
        if self._idx < len(self._comments) - 1:
            self._idx += 1
            self._load_comment()

    # ── Key handling ──────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Ignore hotkeys while actively editing OCR text
        if not self._ocr_edit.isReadOnly():
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in (Qt.Key.Key_A,):
            self._approve()
        elif key in (Qt.Key.Key_R,):
            self._reject()
        elif key in (Qt.Key.Key_F,):
            self._flag()
        elif key in (Qt.Key.Key_N, Qt.Key.Key_Right):
            self._next()
        elif key in (Qt.Key.Key_P, Qt.Key.Key_Left):
            self._prev()
        else:
            super().keyPressEvent(event)
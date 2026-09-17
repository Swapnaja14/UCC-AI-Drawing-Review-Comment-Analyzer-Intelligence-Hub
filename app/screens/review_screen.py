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
                                QInputDialog, QMessageBox)
from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QFont, QPainter, QKeyEvent, QPixmap, QPen, QBrush, QColor

from app import mock_data as md
from app.components.chips import StatusChip, CategoryBadge
from app.components.pdf_canvas import make_page_pixmap, draw_bounding_boxes, BBoxItem

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

        # Load comments: prefer database, fall back to empty list when drawing is loaded
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._all_comments: List[Any] = db_comments if db_comments else []
        elif self._controller:
            self._all_comments = []
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

        # Left — PDF canvas (simulated; real page rendering via PdfViewerPage)
        self._scene = QGraphicsScene()
        self._view  = QGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._load_canvas()
        splitter.addWidget(self._view)

        # Right — review panel
        self._panel = self._build_review_panel()
        splitter.addWidget(self._panel)
        splitter.setStretchFactor(0, 55)
        splitter.setStretchFactor(1, 45)

        root.addWidget(splitter)
        self._apply_filter()

    def reload_comments(self) -> None:
        """
        Reload comments from the database for the currently loaded drawing.

        Call this method after uploading a new PDF or after the OCR pipeline
        populates comments, so the review screen reflects the latest data.
        """
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

    # ── Panel builder ─────────────────────────────────────────────

    def _build_review_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setStyleSheet("#Card { border-radius:0; }")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        # Progress header
        prog_hdr = QHBoxLayout()
        self._prog_lbl = QLabel("Comment 1 of 0")
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

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, max(len(self._comments), 1))
        self._prog_bar.setValue(1)
        self._prog_bar.setFixedHeight(4)
        self._prog_bar.setStyleSheet(
            "QProgressBar { background:#3A3C42; border-radius:2px; }"
            "QProgressBar::chunk { background: #3E9BFF; border-radius:2px; }"
        )
        lay.addWidget(self._prog_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # Comment edit card
        self._edit_card = QFrame()
        self._edit_card.setObjectName("Card")
        edit_lay = QVBoxLayout(self._edit_card)
        edit_lay.setContentsMargins(16, 16, 16, 16)
        edit_lay.setSpacing(10)

        self._comment_id_lbl = QLabel("")
        self._comment_id_lbl.setFont(QFont("Cascadia Code", 12))
        self._comment_id_lbl.setStyleSheet("color:#A6A9B1;")
        edit_lay.addWidget(self._comment_id_lbl)

        ocr_lbl = QLabel("OCR Text")
        ocr_lbl.setObjectName("FormLabel")
        edit_lay.addWidget(ocr_lbl)

        self._ocr_edit = QTextEdit()
        self._ocr_edit.setFixedHeight(90)
        self._ocr_edit.setReadOnly(True)
        self._ocr_edit.setFont(QFont("Cascadia Code", 12))
        edit_lay.addWidget(self._ocr_edit)

        cat_lbl = QLabel("Category")
        cat_lbl.setObjectName("FormLabel")
        edit_lay.addWidget(cat_lbl)

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

        conf_row = QHBoxLayout()
        self._conf_lbl = QLabel("Confidence: —")
        self._conf_lbl.setObjectName("SubCaption")
        conf_row.addWidget(self._conf_lbl)
        conf_row.addStretch()
        self._cat_badge = CategoryBadge("")
        conf_row.addWidget(self._cat_badge)
        edit_lay.addLayout(conf_row)

        lay.addWidget(self._edit_card)

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
        self._audit_card = QFrame()
        self._audit_card.setObjectName("Card")
        audit_lay = QVBoxLayout(self._audit_card)
        audit_lay.setContentsMargins(14, 10, 14, 10)
        audit_lay.setSpacing(6)

        audit_hdr_row = QHBoxLayout()
        self._audit_toggle_btn = QPushButton("▼  Audit History (0)")
        self._audit_toggle_btn.setObjectName("GhostBtn")
        self._audit_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._audit_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; font-weight: 600; font-size: 13px; padding: 2px 0px; height: 24px; border: none; }"
        )
        self._audit_toggle_btn.clicked.connect(self._toggle_audit_panel)
        audit_hdr_row.addWidget(self._audit_toggle_btn)
        audit_hdr_row.addStretch()
        audit_lay.addLayout(audit_hdr_row)

        self._audit_container = QWidget()
        self._audit_items_lay = QVBoxLayout(self._audit_container)
        self._audit_items_lay.setContentsMargins(0, 2, 0, 0)
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

        # Action bar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self._prev_btn = QPushButton("◀  Prev")
        self._prev_btn.setObjectName("SecondaryBtn")
        self._prev_btn.setFixedHeight(36)
        self._prev_btn.clicked.connect(self._prev)
        action_bar.addWidget(self._prev_btn)

        action_bar.addStretch()

        self._reject_btn = QPushButton("✕  Reject")
        self._reject_btn.setObjectName("DangerBtn")
        self._reject_btn.setFixedHeight(36)
        self._reject_btn.clicked.connect(self._reject)
        action_bar.addWidget(self._reject_btn)

        self._flag_btn = QPushButton("⚐  Flag")
        self._flag_btn.setObjectName("SecondaryBtn")
        self._flag_btn.setStyleSheet(
            "QPushButton#SecondaryBtn { color:#FBBF24; border:1px solid #FBBF24; }"
            "QPushButton#SecondaryBtn:hover { background-color:#FBBF241A; }"
        )
        self._flag_btn.setFixedHeight(36)
        self._flag_btn.clicked.connect(self._flag)
        action_bar.addWidget(self._flag_btn)

        self._edit_btn = QPushButton("✎  Edit")
        self._edit_btn.setObjectName("SecondaryBtn")
        self._edit_btn.setFixedHeight(36)
        self._edit_btn.clicked.connect(self._toggle_edit)
        action_bar.addWidget(self._edit_btn)

        self._approve_btn = QPushButton("✓  Approve")
        self._approve_btn.setObjectName("SuccessBtn")
        self._approve_btn.setFixedHeight(36)
        self._approve_btn.clicked.connect(self._approve)
        action_bar.addWidget(self._approve_btn)

        action_bar.addStretch()

        self._next_btn = QPushButton("Next  ▶")
        self._next_btn.setObjectName("SecondaryBtn")
        self._next_btn.setFixedHeight(36)
        self._next_btn.clicked.connect(self._next)
        action_bar.addWidget(self._next_btn)

        lay.addLayout(action_bar)

        hint = QLabel(
            "Keyboard: A = Approve  ·  R = Reject  ·  F = Flag  ·  ← / → = Prev / Next"
        )
        hint.setObjectName("SubCaption")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

        lay.addStretch()
        return panel

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
            return

        current_comment = self._comments[self._idx] if self._idx < len(self._comments) else self._comments[0]
        page_num = _get(current_comment, "page", 1)
        self._current_canvas_page = page_num

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
                active_pen = QPen(QColor("#00E5FF"), 3.5)
                active_pen.setStyle(Qt.PenStyle.SolidLine)
                item.setPen(active_pen)
                fill_color = QColor("#00E5FF")
                fill_color.setAlphaF(0.35)
                item.setBrush(QBrush(fill_color))
                item.setZValue(10)
            else:
                # Inactive boxes: standard subtle styling
                label = _get(item.comment, "label", "")
                status = _get(item.comment, "status", "Pending")
                if "blue" in str(label).lower() or str(label) in ("comment_blue", "native_blue_markup"):
                    col_hex = "#3B82F6"
                elif "yellow" in str(label).lower():
                    col_hex = "#FBBF24"
                elif "green" in str(label).lower():
                    col_hex = "#10B981"
                elif status == "Approved":
                    col_hex = "#4ADE80"
                else:
                    col_hex = "#EF4444"

                normal_pen = QPen(QColor(col_hex), 1.5)
                normal_pen.setStyle(Qt.PenStyle.SolidLine)
                item.setPen(normal_pen)
                fill_color = QColor(col_hex)
                fill_color.setAlphaF(0.15)
                item.setBrush(QBrush(fill_color))
                item.setZValue(1)

        # Auto-pan & zoom into the active bounding box
        if cid in self._box_items:
            rect = self._box_items[cid].sceneBoundingRect()
            if not rect.isEmpty() and rect.width() > 0 and rect.height() > 0:
                target_rect = rect.adjusted(-120, -120, 120, 120)
                self._view.fitInView(target_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _load_comment(self) -> None:
        if not self._comments:
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
            return

        self._approve_btn.setEnabled(True)
        self._reject_btn.setEnabled(True)
        self._flag_btn.setEnabled(True)
        self._edit_btn.setEnabled(True)

        total = len(self._comments)
        self._idx = max(0, min(self._idx, total - 1))
        c     = self._comments[self._idx]
        cid   = _get(c, "id", "")

        notice = " (Auto-Approved Drawing)" if getattr(self, "_is_all_auto_approved_notice", False) else ""
        self._prog_lbl.setText(f"Comment {self._idx + 1} of {total}{notice}")
        self._prog_bar.setValue(self._idx + 1)

        drawing_ref = _get(c, "drawing_no", _get(c, "drawing_id", ""))
        page_ref    = _get(c, "page", 1)
        self._comment_id_lbl.setText(f"{cid}  ·  {drawing_ref}  ·  pg {page_ref}")

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
        self._conf_lbl.setText(f"Confidence: {int(confidence * 100)}%")
        cur_status = self._statuses.get(cid, _get(c, "status", "Pending"))
        self._status_chip.set_status(cur_status)

        is_human = _get(c, "is_verified_by_human", False)
        if cur_status == "Approved" and not is_human and hasattr(self, "_auto_approved_badge"):
            self._auto_approved_badge.show()
        elif hasattr(self, "_auto_approved_badge"):
            self._auto_approved_badge.hide()

        self._prev_btn.setEnabled(self._idx > 0)
        self._next_btn.setEnabled(self._idx < total - 1)

        self._load_audit_trail(cid)
        self._highlight_current_box()

    def _flash_card(self, color: str) -> None:
        orig = self._edit_card.styleSheet()
        self._edit_card.setStyleSheet(
            f"#Card {{ border:2px solid {color}; border-radius:8px; }}"
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
            "QFrame { background: #26272B; border: 1px solid #3A3C42; border-radius: 6px; }"
        )
        row_lay = QHBoxLayout(row_frame)
        row_lay.setContentsMargins(8, 5, 8, 5)
        row_lay.setSpacing(8)

        raw_action = str(_get(entry, "action", "action"))
        action_name = raw_action.upper()
        badge_styles = {
            "APPROVE": ("#4ADE80", "#1a3d26"),
            "REJECT": ("#F87171", "#3d1a1a"),
            "FLAG": ("#FBBF24", "#3d2e0a"),
            "EDIT_TEXT": ("#3E9BFF", "#0d2540"),
            "EDIT_CATEGORY": ("#A78BFA", "#2a1a4d"),
            "BULK_APPROVE": ("#2DD4BF", "#0a2d2a"),
        }
        fg, bg = badge_styles.get(action_name, ("#A6A9B1", "#3A3C42"))
        action_lbl = QLabel(action_name)
        action_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        action_lbl.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border-radius: 3px; padding: 2px 6px;"
        )
        row_lay.addWidget(action_lbl)

        user_id = _get(entry, "changed_by_user_id", "") or _get(entry, "reviewer_id", "") or "anonymous"
        user_lbl = QLabel(f"by {user_id}")
        user_lbl.setFont(QFont("Segoe UI Variable", 11, QFont.Weight.DemiBold))
        user_lbl.setStyleSheet("color: #F2F3F5;")
        row_lay.addWidget(user_lbl)

        details = _get(entry, "details", "") or _get(entry, "notes", "")
        if not details:
            old_v = _get(entry, "old_value", "")
            new_v = _get(entry, "new_value", "")
            if old_v or new_v:
                details = f"{old_v} → {new_v}"
        if details:
            detail_lbl = QLabel(str(details))
            detail_lbl.setFont(QFont("Segoe UI Variable", 11))
            detail_lbl.setStyleSheet("color: #A6A9B1;")
            detail_lbl.setWordWrap(True)
            row_lay.addWidget(detail_lbl)

        row_lay.addStretch()

        ts = _get(entry, "timestamp", "")
        if hasattr(ts, "strftime"):
            ts_str = ts.strftime("%H:%M:%S")
        else:
            ts_str = str(ts)
        ts_lbl = QLabel(ts_str)
        ts_lbl.setFont(QFont("Cascadia Code", 10))
        ts_lbl.setStyleSheet("color: #717680;")
        row_lay.addWidget(ts_lbl)

        return row_frame

    def _load_audit_trail(self, cid: str) -> None:
        """Fetch and render the audit history for the specified comment."""
        while self._audit_items_lay.count() > 0:
            item = self._audit_items_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not cid:
            self._audit_toggle_btn.setText("▼  Audit History (0)")
            empty_lbl = QLabel("No comment selected.")
            empty_lbl.setFont(QFont("Segoe UI", 11))
            empty_lbl.setStyleSheet("color: #717680; padding: 2px 4px;")
            self._audit_items_lay.addWidget(empty_lbl)
            return

        entries: List[Any] = []
        if self._controller and hasattr(self._controller, "get_audit_trail"):
            try:
                entries = self._controller.get_audit_trail(cid) or []
            except Exception:
                entries = []

        count = len(entries)
        prefix = "▼" if self._audit_scroll.isVisible() else "▶"
        self._audit_toggle_btn.setText(f"{prefix}  Audit History ({count})")

        if not entries:
            empty_lbl = QLabel("No audit history recorded yet.")
            empty_lbl.setFont(QFont("Segoe UI", 11))
            empty_lbl.setStyleSheet("color: #717680; padding: 2px 4px;")
            self._audit_items_lay.addWidget(empty_lbl)
        else:
            for entry in reversed(entries):
                self._audit_items_lay.addWidget(self._build_audit_row(entry))

    def _set_status(self, status: str) -> None:
        """Update status in memory and persist to database via controller."""
        if not self._comments:
            return
        c   = self._comments[self._idx]
        cid = _get(c, "id", "")
        self._statuses[cid] = status
        self._status_chip.set_status(status)

        # Update in-memory objects
        if isinstance(c, dict):
            c["status"] = status
            c["is_verified_by_human"] = True
        else:
            setattr(c, "status", status)
            setattr(c, "is_verified_by_human", True)

        for ac in getattr(self, "_all_comments", []):
            if _get(ac, "id") == cid:
                if isinstance(ac, dict):
                    ac["status"] = status
                    ac["is_verified_by_human"] = True
                else:
                    setattr(ac, "status", status)
                    setattr(ac, "is_verified_by_human", True)
                break

        if hasattr(self, "_auto_approved_badge"):
            self._auto_approved_badge.hide()

        # INTEGRATION NOTE:
        # Status is persisted through AppController → CommentRepository.
        # Only statuses from the agreed vocabulary are accepted:
        # "Pending", "Approved", "Rejected", "Flagged"
        if self._controller and cid and not cid.startswith("C-"):
            # cid starting with "C-" indicates mock data — do not persist
            self._controller.update_comment_status(cid, status)
            self._load_audit_trail(cid)

    # ── Action slots ──────────────────────────────────────────────

    def _approve(self) -> None:
        self._set_status("Approved")
        self._flash_card("#4ADE80")
        QTimer.singleShot(400, self._next)

    def _reject(self) -> None:
        self._set_status("Rejected")
        self._flash_card("#F87171")
        QTimer.singleShot(400, self._next)

    def _flag(self) -> None:
        self._set_status("Flagged")
        self._flash_card("#FBBF24")
        QTimer.singleShot(400, self._next)

    def _toggle_edit(self) -> None:
        ro = self._ocr_edit.isReadOnly()
        if ro:
            # Switching to edit mode
            self._ocr_edit.setReadOnly(False)
            self._edit_btn.setText("💾  Save")
        else:
            # Switching back to read-only = user intends to save
            self._ocr_edit.setReadOnly(True)
            self._edit_btn.setText("✎  Edit")

            # INTEGRATION NOTE:
            # Persist the edited OCR text through AppController.
            # Only persists for real database comments (not mock data).
            if self._comments:
                c   = self._comments[self._idx]
                cid = _get(c, "id", "")
                if self._controller and cid and not cid.startswith("C-"):
                    self._controller.update_comment_text(
                        cid, self._ocr_edit.toPlainText()
                    )
                    self._load_audit_trail(cid)

    def _prev(self) -> None:
        if self._idx > 0:
            self._idx -= 1
            self._load_comment()

    def _next(self) -> None:
        if self._idx < len(self._comments) - 1:
            self._idx += 1
            self._load_comment()

    # ── Keyboard navigation ───────────────────────────────────────

    def keyPressEvent(self, e: QKeyEvent) -> None:
        key = e.key()
        if key == Qt.Key.Key_A:
            self._approve()
        elif key == Qt.Key.Key_R:
            self._reject()
        elif key == Qt.Key.Key_F:
            self._flag()
        elif key == Qt.Key.Key_Left:
            self._prev()
        elif key == Qt.Key.Key_Right:
            self._next()
        else:
            super().keyPressEvent(e)

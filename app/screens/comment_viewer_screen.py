"""
comment_viewer_screen.py — Redesigned Comment Highlight Viewer screen.

Provides:
    CommentHighlightPage(QWidget)
        Annotated drawing canvas with floating viewport controls on top,
        and an independently scrollable, filterable comment review panel on the right.
"""
from __future__ import annotations
from typing import Any, Dict, List, Union

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QGraphicsView,
    QGraphicsScene,
    QPushButton,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QFont, QPainter, QPixmap, QColor

from app import mock_data as md
from app.components.pdf_canvas import make_page_pixmap, BBoxItem
from app.components.chips import StatusChip, CategoryBadge


def _get(c: Union[Dict[str, Any], Any], field: str, default: Any = "") -> Any:
    """Access a field from either a normalised display dict or a mock dataclass."""
    if isinstance(c, dict):
        return c.get(field, default)
    return getattr(c, field, default)


def _card(parent=None) -> QFrame:
    """Creates a light rounded card matching the clean dashboard style."""
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


class CommentHighlightPage(QWidget):
    """
    Comment Highlight Viewer — annotated drawing canvas with a
    synchronised, filterable comment review panel.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._active_filter = "All"
        self._filtered_comments: List[Any] = []

        # Load comments from DB or fall back to mock data
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._comments: List[Any] = db_comments if db_comments else list(md.COMMENTS)
        else:
            self._comments = list(md.COMMENTS)

        self.setObjectName("CommentViewerRoot")
        self.setStyleSheet(
            """
            QWidget#CommentViewerRoot {
                background-color: #F8FAFC;
            }
            QLabel {
                background-color: transparent;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ── 1. Top Context Header Bar ─────────────────────────────────────────
        header_bar = _card()
        hb_lay = QHBoxLayout(header_bar)
        hb_lay.setContentsMargins(12, 10, 12, 10)
        hb_lay.setSpacing(12)

        doc_icon_frame = QFrame()
        doc_icon_frame.setStyleSheet("background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px;")
        doc_icon_frame.setFixedSize(32, 32)
        doc_icon_lay = QHBoxLayout(doc_icon_frame)
        doc_icon_lay.setContentsMargins(0, 0, 0, 0)
        doc_icon = QLabel("🔍")
        doc_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        doc_icon.setFont(QFont("Inter", 11))
        doc_icon_lay.addWidget(doc_icon)
        hb_lay.addWidget(doc_icon_frame)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        dwg_title_row = QHBoxLayout()
        dwg_title_row.setSpacing(8)

        lbl_dwg_name = QLabel("Highland Tower Core B — Foundation & Grade Beams")
        lbl_dwg_name.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        lbl_dwg_name.setStyleSheet("color: #0F172A;")

        badge_version = QLabel("Set v3.1 Synced")
        badge_version.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        badge_version.setStyleSheet(
            "background: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; border-radius: 4px; padding: 1px 6px;"
        )

        dwg_title_row.addWidget(lbl_dwg_name)
        dwg_title_row.addWidget(badge_version)
        dwg_title_row.addStretch()

        lbl_dwg_meta = QLabel("Doc ID: DWG-S-204-REV04  •  Model OCR Confidence: 96.8% aggregate")
        lbl_dwg_meta.setFont(QFont("Inter", 8.5))
        lbl_dwg_meta.setStyleSheet("color: #64748B;")

        title_vbox.addLayout(dwg_title_row)
        title_vbox.addWidget(lbl_dwg_meta)
        hb_lay.addLayout(title_vbox, 1)

        # Right Action Buttons
        btn_thresh = QPushButton("⚙ Detection Thresholds")
        btn_thresh.setFixedHeight(30)
        btn_thresh.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 0 10px; color: #334155; font-weight: 500; font-size: 10.5px; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )

        btn_commit = QPushButton("🚀 Commit Review Batch")
        btn_commit.setFixedHeight(30)
        btn_commit.setStyleSheet(
            "QPushButton { background: #0284C7; border: none; border-radius: 6px; padding: 0 12px; color: #FFFFFF; font-weight: 600; font-size: 10.5px; }"
            "QPushButton:hover { background: #0369A1; }"
        )

        hb_lay.addWidget(btn_thresh)
        hb_lay.addWidget(btn_commit)

        root.addWidget(header_bar)

        # ── 2. Main Workspace Split: Canvas Box & Comment Panel ──────────────
        workspace_lay = QHBoxLayout()
        workspace_lay.setSpacing(12)

        # Left Canvas Outer Container Card
        canvas_card = _card()
        canvas_card_lay = QVBoxLayout(canvas_card)
        canvas_card_lay.setContentsMargins(1, 1, 1, 1)
        canvas_card_lay.setSpacing(0)

        # Canvas Header Toolbar Overlay Widget
        canvas_header = QFrame()
        canvas_header.setFixedHeight(38)
        canvas_header.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #E2E8F0; border-top-left-radius: 7px; border-top-right-radius: 7px;")
        ch_lay = QHBoxLayout(canvas_header)
        ch_lay.setContentsMargins(12, 0, 12, 0)
        ch_lay.setSpacing(8)

        sheet_lbl = QLabel("• SHEET S-204 [PG 14 OF 84] — SCALE 1/4\" = 1'-0\"")
        sheet_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        sheet_lbl.setStyleSheet("color: #0F172A;")

        ch_lay.addWidget(sheet_lbl)
        ch_lay.addStretch()

        # Controls Container
        ctrl_box = QFrame()
        ctrl_box.setStyleSheet("background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;")
        ctrl_lay = QHBoxLayout(ctrl_box)
        ctrl_lay.setContentsMargins(4, 2, 4, 2)
        ctrl_lay.setSpacing(4)

        zoom_out = QPushButton("−")
        zoom_out.setFixedSize(22, 22)
        zoom_out.setStyleSheet("QPushButton { background: transparent; border: none; color: #475569; font-weight: bold; font-size: 12px; }"
                               "QPushButton:hover { background: #E2E8F0; border-radius: 3px; }")
        zoom_out.clicked.connect(self._zoom_out)

        zoom_lbl = QLabel("100%")
        zoom_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        zoom_lbl.setStyleSheet("color: #334155; padding: 0 4px;")

        zoom_in = QPushButton("+")
        zoom_in.setFixedSize(22, 22)
        zoom_in.setStyleSheet("QPushButton { background: transparent; border: none; color: #475569; font-weight: bold; font-size: 12px; }"
                              "QPushButton:hover { background: #E2E8F0; border-radius: 3px; }")
        zoom_in.clicked.connect(self._zoom_in)

        fit_btn = QPushButton("⊡")
        fit_btn.setToolTip("Fit View")
        fit_btn.setFixedSize(22, 22)
        fit_btn.setStyleSheet("QPushButton { background: transparent; border: none; color: #475569; font-weight: bold; font-size: 12px; }"
                              "QPushButton:hover { background: #E2E8F0; border-radius: 3px; }")
        fit_btn.clicked.connect(self._fit_view)

        ctrl_lay.addWidget(zoom_out)
        ctrl_lay.addWidget(zoom_lbl)
        ctrl_lay.addWidget(zoom_in)
        ctrl_lay.addWidget(fit_btn)
        ch_lay.addWidget(ctrl_box)

        canvas_card_lay.addWidget(canvas_header)

        # Scene and GraphicsView
        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setStyleSheet("QGraphicsView { border: none; background: #F1F5F9; border-bottom-left-radius: 7px; border-bottom-right-radius: 7px; }")
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        canvas_card_lay.addWidget(self._view, 1)

        # Canvas Footer Info Bar
        canvas_footer = QFrame()
        canvas_footer.setFixedHeight(28)
        canvas_footer.setStyleSheet("background: #FFFFFF; border-top: 1px solid #E2E8F0; border-bottom-left-radius: 7px; border-bottom-right-radius: 7px;")
        cf_lay = QHBoxLayout(canvas_footer)
        cf_lay.setContentsMargins(12, 0, 12, 0)
        
        lbl_legend = QLabel("DETECTION LEGEND:  ● Active Focus (#C-13)   ● Fire & Life Safety   ● MEP Clash")
        lbl_legend.setFont(QFont("Inter", 7.5, QFont.Weight.Medium))
        lbl_legend.setStyleSheet("color: #64748B;")
        
        lbl_vector = QLabel("⚙ Geometric Vector Map • OCR AI v2.4 Native")
        lbl_vector.setFont(QFont("Inter", 7.5))
        lbl_vector.setStyleSheet("color: #94A3B8;")

        cf_lay.addWidget(lbl_legend)
        cf_lay.addStretch()
        cf_lay.addWidget(lbl_vector)

        canvas_card_lay.addWidget(canvas_footer)

        workspace_lay.addWidget(canvas_card, 1)

        # Right Side: 420px Comment Review Panel
        panel = _card()
        panel.setFixedWidth(420)
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(12, 12, 12, 12)
        panel_lay.setSpacing(8)

        # Panel Header
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        
        self._count_lbl = QLabel("Detected Comments")
        self._count_lbl.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        self._count_lbl.setStyleSheet("color: #0F172A;")

        self._lbl_found = QLabel(f"{len(self._comments)} comments found")
        self._lbl_found.setFont(QFont("Inter", 8))
        self._lbl_found.setStyleSheet("color: #2563EB; background: #EFF6FF; border-radius: 4px; padding: 2px 6px; font-weight: 500;")

        hdr.addWidget(self._count_lbl)
        hdr.addWidget(self._lbl_found)
        hdr.addStretch()

        filter_lbl = QLabel("⚡ Filter by State")
        filter_lbl.setFont(QFont("Inter", 8, QFont.Weight.Medium))
        filter_lbl.setStyleSheet("color: #64748B;")
        hdr.addWidget(filter_lbl)

        panel_lay.addLayout(hdr)

        # Filter Chips Bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(4)

        self._filter_btns: Dict[str, QPushButton] = {}
        for ftag in ["All", "Technical", "General", "Pending", "Approved"]:
            btn = QPushButton(ftag)
            btn.setCheckable(True)
            btn.setChecked(ftag == "All")
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                "QPushButton { background: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; "
                "border-radius: 4px; padding: 0 8px; font-size: 10px; font-weight: 600; }"
                "QPushButton:hover { background: #E2E8F0; color: #0F172A; }"
                "QPushButton:checked { background: #0284C7; color: #FFFFFF; border-color: #0284C7; }"
            )
            btn.clicked.connect(self._make_filter_handler(ftag))
            self._filter_btns[ftag] = btn
            filter_bar.addWidget(btn)

        panel_lay.addLayout(filter_bar)

        # Independently Scrollable Comment List
        self._list = QListWidget()
        self._list.setSpacing(6)
        self._list.setStyleSheet(
            "QListWidget { border: none; background: transparent; padding: 0px; }"
            "QListWidget::item { background: transparent; border-radius: 6px; padding: 0px; margin-bottom: 2px; }"
            "QListWidget::item:hover { background: transparent; }"
            "QListWidget::item:selected { background: transparent; }"
        )
        self._list.currentRowChanged.connect(self._on_list_select)
        panel_lay.addWidget(self._list, 1)

        self._apply_filter("All")
        workspace_lay.addWidget(panel)

        root.addLayout(workspace_lay, 1)
        self._load_canvas()

    def _make_filter_handler(self, tag: str):
        def handler():
            for t, b in self._filter_btns.items():
                b.setChecked(t == tag)
            self._apply_filter(tag)
        return handler

    def _apply_filter(self, tag: str) -> None:
        self._active_filter = tag
        if tag == "All":
            self._filtered_comments = list(self._comments)
        elif tag in ("Pending", "Approved", "Rejected", "Flagged"):
            self._filtered_comments = [
                c for c in self._comments if _get(c, "status", "Pending") == tag
            ]
        elif tag == "Technical":
            self._filtered_comments = [
                c for c in self._comments if _get(c, "category", "") == "Technical"
            ]
        elif tag == "General":
            self._filtered_comments = [
                c for c in self._comments if _get(c, "category", "") != "Technical"
            ]
        else:
            self._filtered_comments = list(self._comments)

        self._lbl_found.setText(f"{len(self._filtered_comments)} comments found")
        self._populate_list()

    def reload_comments(self) -> None:
        """Reload canvas and list from the database after a new PDF is loaded."""
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._comments = db_comments if db_comments else []
            self._apply_filter(self._active_filter)
            self._load_canvas()

    # ── Canvas helpers ────────────────────────────────────────────

    def _load_canvas(self) -> None:
        self._scene.clear()

        if self._controller and self._controller.current_document:
            try:
                page_num = 1
                if self._comments:
                    page_num = _get(self._comments[0], "page", 1)
                rendered_dto = self._controller.pdf_service.get_page_render(
                    self._controller.current_document.file_path, page_num, dpi=150
                )
                pm = QPixmap()
                pm.loadFromData(rendered_dto.image_bytes)
            except Exception:
                pm = make_page_pixmap(780, 1000, comments=[])
        else:
            pm = make_page_pixmap(780, 1000, comments=[])

        self._scene.addPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))
        self._box_items: dict = {}

        width = pm.width()
        height = pm.height()

        for c in self._comments:
            bbox   = _get(c, "bbox", (0, 0, 0, 0))
            cid    = _get(c, "id", "")

            x = bbox[0] * width
            y = bbox[1] * height
            w = bbox[2] * width
            h = bbox[3] * height

            adapter = _CommentAdapter(c)
            item = BBoxItem(adapter, QRectF(x, y, w, h))
            self._scene.addItem(item)
            self._box_items[cid] = item

    def _zoom_in(self):
        self._view.scale(1.2, 1.2)

    def _zoom_out(self):
        self._view.scale(0.83, 0.83)

    def _fit_view(self):
        if not self._scene.items():
            return
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # ── List helpers ──────────────────────────────────────────────

    def _populate_list(self) -> None:
        self._list.clear()
        for c in self._filtered_comments:
            widget = self._make_comment_card(c)
            item   = QListWidgetItem()
            item.setSizeHint(QSize(380, 175))
            item.setData(Qt.ItemDataRole.UserRole, _get(c, "id", ""))
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

    def _make_comment_card(self, c: Union[Dict[str, Any], Any]) -> QFrame:
        card = QFrame()
        card.setObjectName("CommentCard")
        card.setStyleSheet(
            """
            QFrame#CommentCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
            }
            QFrame#CommentCard:hover {
                border-color: #0284C7;
            }
            """
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        cid        = _get(c, "id", "")
        drawing_no = _get(c, "drawing_no", _get(c, "drawing_id", ""))
        page_no    = _get(c, "page", 1)
        ocr_text   = _get(c, "ocr_text", "")
        category   = _get(c, "category", "Other")
        status     = _get(c, "status", "Pending")
        confidence = _get(c, "confidence", 0.0)

        # Header Row: ID Tag + Sheet Badge + Confidence Badge
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(6)

        id_lbl = QLabel(f"#C-{cid}")
        id_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        id_lbl.setStyleSheet(
            "background-color: #0284C7; color: #FFFFFF; border-radius: 3px; padding: 1px 5px;"
        )

        dwg_lbl = QLabel(f"Sheet S-204 (Pg {page_no})")
        dwg_lbl.setFont(QFont("Inter", 8))
        dwg_lbl.setStyleSheet("color: #64748B;")

        hdr_row.addWidget(id_lbl)
        hdr_row.addWidget(dwg_lbl)
        hdr_row.addStretch()

        conf_f = float(confidence)
        conf_percent = int(conf_f * 100) if conf_f <= 1.0 else int(conf_f)
        conf_lbl = QLabel(f"● {conf_percent}% Confidence")
        conf_lbl.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        conf_lbl.setStyleSheet("color: #059669;")
        hdr_row.addWidget(conf_lbl)

        lay.addLayout(hdr_row)

        # Dark OCR Callout Text Box Container
        ocr_box = QFrame()
        ocr_box.setStyleSheet(
            "QFrame { background-color: #0F172A; border-radius: 4px; padding: 6px; }"
        )
        ocr_lay = QVBoxLayout(ocr_box)
        ocr_lay.setContentsMargins(0, 0, 0, 0)
        ocr_lay.setSpacing(2)

        ocr_hdr = QLabel("EXTRACTED PLAN CALLOUT (OCR)")
        ocr_hdr.setFont(QFont("Inter", 6.5, QFont.Weight.Bold))
        ocr_hdr.setStyleSheet("color: #38BDF8;")

        text = str(ocr_text).strip()
        display_text = text if text else "VERIFY EMBEDMENT DEPTH OF 1-1/4\" DIAMETER ANCHOR RODS AT COLUMN BASE PLATE C-4."
        excerpt_lbl = QLabel(f'"{display_text}"')
        excerpt_lbl.setFont(QFont("Inter", 8, QFont.Weight.Medium))
        excerpt_lbl.setStyleSheet("color: #F8FAFC;")
        excerpt_lbl.setWordWrap(True)

        ocr_lay.addWidget(ocr_hdr)
        ocr_lay.addWidget(excerpt_lbl)
        lay.addWidget(ocr_box)

        # Chips & Action Row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        meta_row.addWidget(CategoryBadge(str(category)))
        meta_row.addWidget(StatusChip(str(status)))

        meta_row.addStretch()

        reviewer_lbl = QLabel("EV  Elena Vance")
        reviewer_lbl.setFont(QFont("Inter", 8, QFont.Weight.Medium))
        reviewer_lbl.setStyleSheet("color: #2563EB;")
        meta_row.addWidget(reviewer_lbl)

        lay.addLayout(meta_row)

        # Quick Action Action Row (Approve / Flag / Note)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        btn_note = QPushButton("✏ Add Note")
        btn_note.setFixedHeight(22)
        btn_note.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; color: #334155; font-size: 9.5px; font-weight: 500; padding: 0 6px; }"
            "QPushButton:hover { background: #F1F5F9; }"
        )

        btn_flag = QPushButton("🚩 Flag")
        btn_flag.setFixedHeight(22)
        btn_flag.setStyleSheet(
            "QPushButton { background: #FEF2F2; border: 1px solid #FECACA; border-radius: 4px; color: #DC2626; font-size: 9.5px; font-weight: 500; padding: 0 6px; }"
            "QPushButton:hover { background: #FEE2E2; }"
        )

        btn_approve = QPushButton("✔ Approve & Sign")
        btn_approve.setFixedHeight(22)
        btn_approve.setStyleSheet(
            "QPushButton { background: #0D9488; border: none; border-radius: 4px; color: #FFFFFF; font-size: 9.5px; font-weight: 600; padding: 0 8px; }"
            "QPushButton:hover { background: #0F766E; }"
        )

        btn_row.addWidget(btn_note)
        btn_row.addWidget(btn_flag)
        btn_row.addStretch()
        btn_row.addWidget(btn_approve)

        lay.addLayout(btn_row)

        return card

    # ── Selection handling ────────────────────────────────────────

    def _on_list_select(self, row: int) -> None:
        if 0 <= row < len(self._filtered_comments):
            cid = _get(self._filtered_comments[row], "id", "")
            self._highlight_box(cid)

    def _highlight_box(self, cid: str) -> None:
        for bid, item in self._box_items.items():
            pen = item.pen()
            pen.setWidth(4 if bid == cid else 1.5)
            item.setPen(pen)
        if cid in self._box_items:
            rect = self._box_items[cid].sceneBoundingRect()
            self._view.fitInView(
                rect.adjusted(-90, -90, 90, 90),
                Qt.AspectRatioMode.KeepAspectRatio,
            )


class _CommentAdapter:
    """Adapter bridging dict and object access for BBoxItem."""
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
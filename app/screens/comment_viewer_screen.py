"""
comment_viewer_screen.py — Comment Highlight Viewer screen with interactive zoom and page controls.

Provides:
    CommentHighlightPage(QWidget)
        Annotated PDF canvas with Zoom In/Out toolbar, mouse-wheel zooming,
        fit-width, page navigation, and a scrollable comment list panel.
        Clicking a list item pans & zooms the canvas to the matching bounding box.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFrame,
                                QLabel, QListWidget, QListWidgetItem,
                                QGraphicsView, QGraphicsScene, QComboBox,
                                QSizePolicy)
from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import QFont, QPainter, QPixmap, QWheelEvent, QKeyEvent

from app import mock_data as md
from app.components.pdf_toolbar import PdfToolbar
from app.components.pdf_canvas import make_page_pixmap, BBoxItem
from app.components.chips import StatusChip, CategoryBadge
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _get(c: Union[Dict[str, Any], Any], field: str, default: Any = "") -> Any:
    """Access a field from either a normalised display dict or a mock dataclass."""
    if isinstance(c, dict):
        return c.get(field, default)
    return getattr(c, field, default)


class ZoomableGraphicsView(QGraphicsView):
    """
    Enhanced QGraphicsView supporting:
    - Smooth mouse wheel zooming (centered on cursor)
    - Panning via click-and-drag (ScrollHandDrag)
    - Keyboard zoom shortcuts (+ / - / 0 / F)
    - Zoom signal notification for toolbar sync
    """
    zoom_changed = Signal(float)

    def __init__(self, scene: Optional[QGraphicsScene] = None, parent: Optional[QWidget] = None):
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._current_zoom: float = 1.0

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom in or out centered at mouse cursor on mouse wheel."""
        delta = event.angleDelta().y()
        if delta != 0:
            factor = 1.15 if delta > 0 else (1.0 / 1.15)
            self.zoom_by_factor(factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Keyboard shortcuts for zooming."""
        key = event.key()
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_by_factor(1.2)
            event.accept()
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.zoom_by_factor(1.0 / 1.2)
            event.accept()
        else:
            super().keyPressEvent(event)

    def zoom_by_factor(self, factor: float) -> None:
        """Scale view by a multiplicative factor with clamping between 15% and 600%."""
        new_zoom = self._current_zoom * factor
        if 0.15 <= new_zoom <= 6.0:
            self._current_zoom = new_zoom
            self.scale(factor, factor)
            self.zoom_changed.emit(self._current_zoom)

    def set_zoom_level(self, zoom: float) -> None:
        """Set absolute zoom scale."""
        zoom = max(0.15, min(zoom, 6.0))
        if self._current_zoom > 0:
            factor = zoom / self._current_zoom
            self._current_zoom = zoom
            self.scale(factor, factor)
            self.zoom_changed.emit(self._current_zoom)

    def reset_zoom(self) -> None:
        """Reset view transform to 100%."""
        self.resetTransform()
        self._current_zoom = 1.0
        self.zoom_changed.emit(self._current_zoom)


class CommentHighlightPage(QWidget):
    """
    Comment Highlight Viewer — annotated drawing canvas with Zoom In/Out controls,
    page navigation, and a synchronised comment list panel.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._current_page = 1
        self._total_pages = 1
        self._zoom = 1.0
        self._box_items: Dict[str, BBoxItem] = {}
        self._pm_item = None

        # Load comments from DB or fall back to mock data if standalone
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._comments: List[Any] = db_comments if db_comments else []
        elif self._controller:
            self._comments = []
        else:
            self._comments = list(md.COMMENTS)

        if self._controller and self._controller.current_document:
            self._total_pages = max(1, self._controller.current_document.total_pages)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left Canvas Container (Toolbar + GraphicsView) ───────
        canvas_container = QWidget()
        canvas_lay = QVBoxLayout(canvas_container)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(0)

        # Top PDF / Zoom Toolbar
        self._toolbar = PdfToolbar(total_pages=self._total_pages)
        self._toolbar.zoom_in_requested.connect(self._do_zoom_in)
        self._toolbar.zoom_out_requested.connect(self._do_zoom_out)
        self._toolbar.fit_width_requested.connect(self._fit_width)
        self._toolbar.rotate_requested.connect(self._rotate)
        self._toolbar.prev_page_requested.connect(self._prev_page)
        self._toolbar.next_page_requested.connect(self._next_page)
        self._toolbar.page_changed.connect(self._goto_page)
        canvas_lay.addWidget(self._toolbar)

        # Annotated Canvas View
        self._scene = QGraphicsScene()
        self._view = ZoomableGraphicsView(self._scene)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._view.zoom_changed.connect(self._on_view_zoom_changed)
        canvas_lay.addWidget(self._view, 1)

        self._load_canvas(page_num=1)
        root.addWidget(canvas_container, 3)

        # ── Right Comment List Panel ─────────────────────────────
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setFixedWidth(340)
        panel.setStyleSheet("#Card { border-radius:0; }")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(0)

        # Panel header
        hdr = QFrame()
        hdr.setFixedHeight(80)
        hdr.setStyleSheet(
            "background: #2D2F34; border-bottom: 1px solid #3A3C42;"
        )
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 8, 12, 8)
        hdr_lay.setSpacing(4)

        top_hdr = QHBoxLayout()
        self._count_lbl = QLabel(f"🔍  {len(self._comments)} comments found")
        self._count_lbl.setFont(QFont("Segoe UI Variable", 13, QFont.Weight.DemiBold))
        top_hdr.addWidget(self._count_lbl)
        hdr_lay.addLayout(top_hdr)

        self._dwg_filt = QComboBox()
        self._dwg_filt.setFixedHeight(28)
        self._dwg_filt.setStyleSheet("QComboBox { background: #1E2024; color: #E2E8F0; font-size: 11px; border: 1px solid #3A3C42; border-radius: 4px; padding: 2px 6px; }")
        self._dwg_filt.currentIndexChanged.connect(self._on_drawing_filter_changed)
        hdr_lay.addWidget(self._dwg_filt)

        panel_lay.addWidget(hdr)

        # Comment list
        self._list = QListWidget()
        self._list.setSpacing(4)
        self._list.setStyleSheet(
            "QListWidget { border:none; background:#26272B; padding:8px; }"
            "QListWidget::item { background:transparent; border-radius:8px; }"
            "QListWidget::item:hover { background: #2D2F34; }"
            "QListWidget::item:selected { background: #3E9BFF1A; }"
        )
        self._list.currentRowChanged.connect(self._on_list_select)
        self._populate_list()
        panel_lay.addWidget(self._list, 1)

        root.addWidget(panel)

    # ── Public API ───────────────────────────────────────────────

    def reload_drawings(self) -> None:
        """Populate the drawing selector combo box."""
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

        # Set selection to current drawing
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
            # Load comments across all drawings
            drawings = self._controller.get_all_drawings() if self._controller else []
            all_cmts = []
            for d in drawings:
                did = d.get("id")
                if did:
                    all_cmts.extend(self._controller.get_comments_for_drawing(did))
            self._comments = all_cmts
            self._count_lbl.setText(f"🔍  {len(self._comments)} comments (All Drawings)")
            self._populate_list()
        elif dwg_id and self._controller and dwg_id != self._controller.current_drawing_id:
            self._controller.switch_current_drawing(dwg_id)
        else:
            self.reload_comments()

    def reload_comments(self) -> None:
        """Reload canvas and list from the database after a new PDF is loaded."""
        self.reload_drawings()
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._comments = db_comments if db_comments else []
            if self._controller.current_document:
                self._total_pages = max(1, self._controller.current_document.total_pages)
            if hasattr(self, '_count_lbl'):
                self._count_lbl.setText(f"🔍  {len(self._comments)} comments found")
            if hasattr(self, '_toolbar'):
                self._toolbar.set_total_pages(self._total_pages)
                self._toolbar.set_current_page(self._current_page)
            self._load_canvas(page_num=self._current_page)
            self._populate_list()

    # ── Zoom & Navigation Actions ────────────────────────────────

    def _do_zoom_in(self) -> None:
        """Zoom in on the drawing canvas."""
        self._view.zoom_by_factor(1.2)

    def _do_zoom_out(self) -> None:
        """Zoom out on the drawing canvas."""
        self._view.zoom_by_factor(1.0 / 1.2)

    def _fit_width(self) -> None:
        """Fit drawing width neatly into viewport."""
        if self._pm_item:
            s_rect = self._scene.sceneRect()
            vw = self._view.viewport().width() - 20
            if s_rect.width() > 0 and vw > 0:
                scale_ratio = vw / s_rect.width()
                self._view.resetTransform()
                self._view.scale(scale_ratio, scale_ratio)
                self._view._current_zoom = scale_ratio
                self._toolbar.set_zoom_label(int(scale_ratio * 100))

    def _rotate(self) -> None:
        """Rotate drawing view 90 degrees."""
        self._view.rotate(90)

    def _prev_page(self) -> None:
        """Navigate to previous page."""
        self._goto_page(max(1, self._current_page - 1))

    def _next_page(self) -> None:
        """Navigate to next page."""
        self._goto_page(min(self._total_pages, self._current_page + 1))

    def _goto_page(self, page_num: int) -> None:
        """Switch to specified page and update canvas."""
        page_num = max(1, min(page_num, self._total_pages))
        if page_num != self._current_page or not self._pm_item:
            self._current_page = page_num
            self._toolbar.set_current_page(page_num)
            self._load_canvas(page_num=page_num)

    def _on_view_zoom_changed(self, zoom: float) -> None:
        """Update toolbar zoom label when view scale changes."""
        self._zoom = zoom
        self._toolbar.set_zoom_label(int(round(zoom * 100)))

    # ── Canvas helpers ────────────────────────────────────────────

    def _load_canvas(self, page_num: int = 1) -> None:
        """Render the drawing canvas with comment bounding boxes for the given page."""
        self._scene.clear()
        self._box_items.clear()
        self._current_page = page_num

        # Update total pages if controller has document
        if self._controller and self._controller.current_document:
            self._total_pages = max(1, self._controller.current_document.total_pages)
            if hasattr(self, '_toolbar'):
                self._toolbar.set_total_pages(self._total_pages)
                self._toolbar.set_current_page(self._current_page)

        # Render real PDF page if available
        if self._controller and self._controller.current_document:
            try:
                rendered_dto = self._controller.pdf_service.get_page_render(
                    self._controller.current_document.file_path, page_num, dpi=150
                )
                pm = QPixmap()
                pm.loadFromData(rendered_dto.image_bytes)
            except Exception as e:
                logger.debug(f"Could not render real page {page_num}: {e}")
                pm = make_page_pixmap(740, 960, comments=[])
        else:
            pm = make_page_pixmap(740, 960, comments=[])

        self._pm_item = self._scene.addPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))

        width = pm.width()
        height = pm.height()

        for c in self._comments:
            c_page = _get(c, "page", 1)
            # Filter comments for the current page when multi-page document is loaded
            if self._total_pages > 1 and c_page != page_num:
                continue

            bbox = _get(c, "bbox", (0, 0, 0, 0))
            cid = _get(c, "id", "")

            x = bbox[0] * width
            y = bbox[1] * height
            w = bbox[2] * width
            h = bbox[3] * height

            adapter = _CommentAdapter(c)
            item = BBoxItem(adapter, QRectF(x, y, w, h), on_click=self._on_bbox_clicked)
            self._scene.addItem(item)
            self._box_items[cid] = item

        self._toolbar.set_zoom_label(int(self._view._current_zoom * 100))

    # ── List helpers ──────────────────────────────────────────────

    def _populate_list(self) -> None:
        self._list.clear()
        for c in self._comments:
            widget = self._make_comment_card(c)
            item = QListWidgetItem()
            item.setSizeHint(QSize(300, 90))
            item.setData(Qt.ItemDataRole.UserRole, _get(c, "id", ""))
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

    def _make_comment_card(self, c: Union[Dict[str, Any], Any]) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background:#2D2F34; border-radius:8px; padding:4px; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        cid = _get(c, "id", "")
        drawing_no = _get(c, "drawing_no", _get(c, "drawing_id", ""))
        page_no = _get(c, "page", 1)
        ocr_text = _get(c, "ocr_text", "")
        category = _get(c, "category", "Other")
        status = _get(c, "status", "Pending")
        confidence = _get(c, "confidence", 0.0)

        id_row = QHBoxLayout()
        id_lbl = QLabel(str(cid))
        id_lbl.setFont(QFont("Cascadia Code", 11))
        id_lbl.setStyleSheet("color: #A6A9B1;")
        id_row.addWidget(id_lbl)
        id_row.addStretch()

        page_tag = QLabel(f"Pg {page_no}")
        page_tag.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        page_tag.setStyleSheet("color: #A6A9B1; background: #3A3C42; padding: 1px 6px; border-radius: 4px;")
        id_row.addWidget(page_tag)

        dwg = QLabel(str(drawing_no))
        dwg.setFont(QFont("Cascadia Code", 11))
        dwg.setStyleSheet("color: #3E9BFF;")
        id_row.addWidget(dwg)
        lay.addLayout(id_row)

        text = str(ocr_text)
        excerpt = QLabel(text[:70] + ("…" if len(text) > 70 else ""))
        excerpt.setFont(QFont("Segoe UI", 12))
        excerpt.setWordWrap(True)
        lay.addWidget(excerpt)

        chips_row = QHBoxLayout()
        chips_row.addWidget(CategoryBadge(str(category)))
        chips_row.addStretch()
        chips_row.addWidget(StatusChip(str(status)))
        conf_f = float(confidence)
        conf_color = (
            "#4ADE80" if conf_f >= 0.9
            else "#FBBF24" if conf_f >= 0.7
            else "#F87171"
        )
        conf = QLabel(f"{int(conf_f * 100)}%")
        conf.setStyleSheet(
            f"color:{conf_color}; font-weight:700; font-size:12px;"
        )
        chips_row.addWidget(conf)
        lay.addLayout(chips_row)
        return card

    # ── Selection handling ────────────────────────────────────────

    def _on_list_select(self, row: int) -> None:
        """Handle comment selection from the right-hand panel."""
        if 0 <= row < len(self._comments):
            comment = self._comments[row]
            c_page = _get(comment, "page", 1)
            cid = _get(comment, "id", "")
            c_dwg_id = _get(comment, "drawing_id", "")

            # Check if comment belongs to a different drawing
            if c_dwg_id and self._controller and c_dwg_id != self._controller.current_drawing_id:
                self._controller.switch_current_drawing(c_dwg_id)
                return

            # If comment is on a different page, navigate to that page first
            if c_page != self._current_page and self._total_pages > 1:
                self._goto_page(c_page)

            self._highlight_box(cid)

    def _on_bbox_clicked(self, cid: str) -> None:
        """Handle clicking directly on a bounding box in the drawing canvas."""
        for row, c in enumerate(self._comments):
            if _get(c, "id", "") == cid:
                self._list.setCurrentRow(row)
                break

    def _highlight_box(self, cid: str) -> None:
        """Highlight target bounding box and center view smoothly on it."""
        for bid, item in self._box_items.items():
            pen = item.pen()
            pen.setWidth(3 if bid == cid else 1.5)
            item.setPen(pen)
        if cid in self._box_items:
            rect = self._box_items[cid].sceneBoundingRect()
            self._view.fitInView(
                rect.adjusted(-120, -120, 120, 120),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            transform = self._view.transform()
            current_scale = transform.m11()
            self._view._current_zoom = current_scale
            self._toolbar.set_zoom_label(int(round(current_scale * 100)))


# ---------------------------------------------------------------------------
# Adapter: gives BBoxItem a consistent attribute interface for DB dicts
# ---------------------------------------------------------------------------

class _CommentAdapter:
    """
    Lightweight adapter that wraps a normalised comment dict so that
    BBoxItem (which expects .id, .status, .ocr_text attributes) can work
    with both mock dataclass objects and database display dicts.
    """

    def __init__(self, comment: Union[Dict[str, Any], Any]) -> None:
        if isinstance(comment, dict):
            self.id         = comment.get("id", "")
            self.status     = comment.get("status", "Pending")
            self.ocr_text   = comment.get("ocr_text", "")
            self.label      = comment.get("label", "comment_red")
            self.confidence = comment.get("confidence", 0.0)
            self.page       = comment.get("page", 1)
        else:
            self.id         = getattr(comment, "id", "")
            self.status     = getattr(comment, "status", "Pending")
            self.ocr_text   = getattr(comment, "ocr_text", "")
            self.label      = getattr(comment, "label", "comment_red")
            self.confidence = getattr(comment, "confidence", 0.0)
            self.page       = getattr(comment, "page", 1)

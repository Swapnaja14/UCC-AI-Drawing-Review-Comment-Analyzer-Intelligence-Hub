"""
pdf_viewer_screen.py — PDF Viewer screen.

Provides:
    PdfViewerPage(QWidget)
        Renders real PDF pages using PyMuPDF backend via AppController,
        zoom / page controls via PdfToolbar, metadata panel, and thumbnail strip.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, List, Optional
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QGraphicsView, QGraphicsScene,
                                QListWidget, QListWidgetItem,
                                QSizePolicy)
from PySide6.QtCore import Qt, QRectF, QSize, QThread, Signal
from PySide6.QtGui import QPainter, QPixmap, QIcon

from app import mock_data as md
from app.components.pdf_toolbar    import PdfToolbar
from app.components.pdf_canvas     import make_page_pixmap, draw_bounding_boxes, draw_annotation_regions
from app.components.metadata_panel import DrawingMetadataPanel
from src.core.dtos.pdf_dtos import PDFDocumentDTO


class AnnotationWorker(QThread):
    """Background worker for non-blocking annotation detection."""
    finished_signal = Signal(object)
    error_signal = Signal(str)

    def __init__(self, annotation_service, file_path: Path, parent=None):
        super().__init__(parent)
        self._service = annotation_service
        self._file_path = file_path

    def run(self):
        try:
            result = self._service.detect_all_pages(
                self._file_path,
                method='hybrid',
                filter_template_regions=False
            )
            self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))


class PdfViewerPage(QWidget):
    """
    PDF Viewer screen displaying real PDF drawing pages rendered via PyMuPDF backend.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._doc_dto: PDFDocumentDTO | None = None
        self._annotation_result = None  # NEW: Store annotation detection result
        self._show_annotations = False  # NEW: Toggle for annotation visualization
        self._annotation_worker: Optional[AnnotationWorker] = None
        self._zoom         = 1.0
        self._current_page = 1
        self._total_pages  = 1

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────
        self._toolbar = PdfToolbar(total_pages=self._total_pages)
        self._toolbar.zoom_in_requested.connect(self._do_zoom_in)
        self._toolbar.zoom_out_requested.connect(self._do_zoom_out)
        self._toolbar.fit_width_requested.connect(self._fit_width)
        self._toolbar.rotate_requested.connect(self._rotate)
        self._toolbar.prev_page_requested.connect(self._prev_page)
        self._toolbar.next_page_requested.connect(self._next_page)
        self._toolbar.page_changed.connect(self._goto_page)
        self._toolbar.show_annotations_toggled.connect(self._toggle_annotations)  # NEW
        root.addWidget(self._toolbar)

        # ── Viewer split ──────────────────────────────────────────
        viewer_row = QHBoxLayout()
        viewer_row.setSpacing(0)
        viewer_row.setContentsMargins(0, 0, 0, 0)

        # Canvas
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
        self._pm_item = None
        self._load_page(1)
        viewer_row.addWidget(self._view, 3)

        # Metadata panel
        self._meta_panel = DrawingMetadataPanel()
        viewer_row.addWidget(self._meta_panel)

        root.addLayout(viewer_row, 1)

        # ── Thumbnail strip ───────────────────────────────────────
        self._thumb_strip = self._build_thumbnail_strip()
        root.addWidget(self._thumb_strip)

    def set_document(self, doc_dto: PDFDocumentDTO) -> None:
        """Sets the active PDFDocumentDTO and updates page count, metadata, & canvas."""
        self._doc_dto = doc_dto
        self._total_pages = doc_dto.total_pages
        self._current_page = 1
        
        # Check if controller already has cached annotation results from workflow
        if self._controller and getattr(self._controller, 'last_annotation_result', None):
            last_res = self._controller.last_annotation_result
            if getattr(last_res, 'file_name', '') == doc_dto.file_name:
                self._annotation_result = last_res
            else:
                self._annotation_result = None
        else:
            self._annotation_result = None
        
        # Update toolbar page count
        self._toolbar.set_total_pages(self._total_pages)
        self._toolbar.set_current_page(1)

        # Update right-side metadata panel with real drawing properties
        fields = [
            ("File Name", doc_dto.file_name),
            ("File Size", f"{round(doc_dto.file_size_bytes / (1024*1024), 2)} MB"),
            ("Total Pages", str(doc_dto.total_pages)),
            ("Format", "Scanned Image" if doc_dto.is_scanned else "Native Digital Vector"),
            ("Title", doc_dto.title or "Engineering Drawing"),
            ("Author", doc_dto.author or "CAD System"),
            ("File Digest", f"{doc_dto.file_hash_sha256[:12]}..."),
        ]
        
        # Add annotation count if available, or comments found in DB
        if self._annotation_result:
            fields.append(("Detected Regions", f"{self._annotation_result.total_regions} annotation boxes"))
            fields.append(("Detection Method", "Color Segmentation (HSV)"))
            fields.append(("Coverage", "All colored markup and annotations"))
        else:
            db_comments = []
            if self._controller and self._controller.current_drawing_id:
                try:
                    db_comments = self._controller.get_comments_for_drawing(self._controller.current_drawing_id) or []
                except Exception:
                    db_comments = []
            if db_comments:
                fields.append(("Review Comments", f"{len(db_comments)} comments saved in database"))
            else:
                fields.append(("Detected Regions", "Click 🔍 to inspect raw markup"))
        
        self._meta_panel.update_fields(fields)

        # Sync thumbnails & render page 1
        self._sync_thumbnails()
        self._load_page(1)

    def reload_comments(self) -> None:
        """Reload page and thumbnails when comments are loaded/updated."""
        self._load_page(self._current_page)
        self._sync_thumbnails()

    # ── Page / zoom helpers ───────────────────────────────────────

    def _get_page_comments(self, page_num: int) -> List[Any]:
        """Fetch normalised comments for the specified 1-based page number."""
        all_comments: List[Any] = []
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            if db_comments:
                all_comments = db_comments
            else:
                all_comments = []
        else:
            all_comments = []

        page_comments = []
        for c in all_comments:
            c_page = c.get("page", 1) if isinstance(c, dict) else getattr(c, "page", 1)
            if c_page == page_num:
                page_comments.append(c)
        return page_comments

    def _load_page(self, page_num: int) -> None:
        self._scene.clear()
        
        # Get page comments (for comment bounding boxes - yellow/green)
        page_comments = self._get_page_comments(page_num)
        
        if self._doc_dto and self._controller:
            try:
                # Render real page using PyMuPDF backend adapter
                rendered_dto = self._controller.pdf_service.get_page_render(
                    self._doc_dto.file_path, page_num, dpi=150
                )
                pm = QPixmap()
                pm.loadFromData(rendered_dto.image_bytes)
                
                # ONLY draw comment bounding boxes if annotations toggle is OFF
                # (comments are different from detected annotation regions)
                if not self._show_annotations:
                    draw_bounding_boxes(pm, page_comments)
                
                # Draw REAL annotation regions if toggle is ON
                if self._show_annotations and self._annotation_result:
                    # Get page dimensions from doc_dto
                    page_idx = page_num - 1
                    if 0 <= page_idx < len(self._doc_dto.pages):
                        page_meta = self._doc_dto.pages[page_idx]
                        page_width_pt = page_meta.width_pt
                        page_height_pt = page_meta.height_pt
                        
                        # Get regions for this specific page
                        page_regions = []
                        for page_result in self._annotation_result.page_results:
                            # Match by page number (0-based in annotation_result)
                            if page_result.page_number == page_idx:
                                page_regions = page_result.regions
                                break
                        
                        if page_regions:
                            print(f"Drawing {len(page_regions)} annotation regions on page {page_num}")
                            draw_annotation_regions(pm, page_regions, page_width_pt, page_height_pt)
                        else:
                            print(f"No annotation regions found for page {page_num}")
                
            except Exception as e:
                print(f"Error loading page: {e}")
                pm = make_page_pixmap(comments=page_comments)
        else:
            pm = make_page_pixmap(comments=page_comments)

        self._pm_item = self._scene.addPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        self._view.resetTransform()
        self._view.scale(self._zoom, self._zoom)
        self._toolbar.set_zoom_label(int(self._zoom * 100))

    def _do_zoom_in(self) -> None:
        self._zoom = min(4.0, self._zoom + 0.2)
        self._apply_zoom()

    def _do_zoom_out(self) -> None:
        self._zoom = max(0.2, self._zoom - 0.2)
        self._apply_zoom()

    def _fit_width(self) -> None:
        if self._pm_item:
            w  = self._pm_item.pixmap().width()
            vw = self._view.viewport().width()
            self._zoom = vw / w * 0.95 if w > 0 else 1.0
            self._apply_zoom()

    def _rotate(self) -> None:
        self._view.rotate(90)

    def _prev_page(self) -> None:
        self._current_page = max(1, self._current_page - 1)
        self._sync_page()

    def _next_page(self) -> None:
        self._current_page = min(self._total_pages, self._current_page + 1)
        self._sync_page()

    def _goto_page(self, page: int) -> None:
        self._current_page = page
        self._load_page(self._current_page)
        if hasattr(self, '_thumb_strip') and self._thumb_strip.count() >= self._current_page:
            self._thumb_strip.setCurrentRow(self._current_page - 1)

    def _sync_page(self) -> None:
        self._toolbar.set_current_page(self._current_page)
        if self._thumb_strip.count() >= self._current_page:
            self._thumb_strip.setCurrentRow(self._current_page - 1)
        self._load_page(self._current_page)

    def _toggle_annotations(self, enabled: bool) -> None:
        """Toggle annotation region visualization on/off."""
        self._show_annotations = enabled
        if enabled and self._annotation_result is None and self._doc_dto and self._controller:
            self._start_background_annotation_detection()
        else:
            self._load_page(self._current_page)  # Redraw current page

    def _start_background_annotation_detection(self) -> None:
        """Runs annotation detection in a non-blocking background worker."""
        if not (self._controller and hasattr(self._controller, 'annotation_service')):
            return
        if self._annotation_worker and self._annotation_worker.isRunning():
            return

        self._meta_panel.update_fields([
            ("File Name", self._doc_dto.file_name if self._doc_dto else ""),
            ("Detected Regions", "Detecting markup in background..."),
        ])

        self._annotation_worker = AnnotationWorker(
            self._controller.annotation_service,
            self._doc_dto.file_path,
            parent=self
        )
        self._annotation_worker.finished_signal.connect(self._on_annotations_detected)
        self._annotation_worker.error_signal.connect(lambda err: print(f"Annotation worker error: {err}"))
        self._annotation_worker.start()

    def _on_annotations_detected(self, result) -> None:
        """Callback when background annotation worker completes."""
        self._annotation_result = result
        if self._controller:
            self._controller.last_annotation_result = result
        if self._doc_dto:
            self.set_document(self._doc_dto)
        else:
            self._load_page(self._current_page)

    # ── Thumbnail strip ───────────────────────────────────────────

    def _build_thumbnail_strip(self) -> QListWidget:
        lst = QListWidget()
        lst.setFlow(QListWidget.Flow.LeftToRight)
        lst.setFixedHeight(110)
        lst.setIconSize(QSize(64, 80))
        lst.setViewMode(QListWidget.ViewMode.IconMode)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        lst.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.setStyleSheet(
            "QListWidget { border-top: 1px solid #3A3C42; border-radius:0;"
            " background:#26272B; }"
            "QListWidget::item { border:2px solid transparent;"
            " border-radius:4px; margin:4px; }"
            "QListWidget::item:selected { border-color:#3E9BFF; }"
        )
        lst.currentRowChanged.connect(
            lambda r: self._goto_page(r + 1) if r >= 0 else None
        )
        self._populate_thumbs(lst)
        return lst

    def _populate_thumbs(self, lst: QListWidget) -> None:
        lst.clear()
        for i in range(self._total_pages):
            page_comments = self._get_page_comments(i + 1)
            if self._doc_dto and self._controller:
                try:
                    r_dto = self._controller.pdf_service.get_page_render(
                        self._doc_dto.file_path, i + 1, dpi=30
                    )
                    pm = QPixmap()
                    pm.loadFromData(r_dto.image_bytes)
                    draw_bounding_boxes(pm, page_comments)
                except Exception:
                    pm = make_page_pixmap(70, 88, comments=page_comments)
            else:
                pm = make_page_pixmap(70, 88, comments=page_comments)

            item = QListWidgetItem(f" Page {i + 1}")
            item.setIcon(QIcon(pm))
            lst.addItem(item)
        if lst.count() > 0:
            lst.setCurrentRow(0)

    def _sync_thumbnails(self) -> None:
        self._populate_thumbs(self._thumb_strip)

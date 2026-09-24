"""
pdf_viewer_screen.py — Redesigned PDF Viewer screen matching Stitch UI.

Provides:
    PdfViewerPage(QWidget)
        Renders real PDF pages using PyMuPDF backend via AppController,
        custom action toolbar, metadata sidebar, and thumbnail navigation strip.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, List, Optional
<<<<<<< HEAD
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QGraphicsView, QGraphicsScene,
                                QListWidget, QListWidgetItem,
                                QSizePolicy, QComboBox, QLabel, QFrame)
from PySide6.QtCore import Qt, QRectF, QSize, QThread, Signal
from PySide6.QtGui import QPainter, QPixmap, QIcon, QFont
=======
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsView,
    QGraphicsScene,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QGraphicsDropShadowEffect,
    QScrollArea,
    QProgressBar,
)
from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import QPainter, QPixmap, QIcon, QFont, QColor
>>>>>>> origin/feature/ui-overhaul

from app.components.pdf_canvas import (
    make_page_pixmap,
    draw_bounding_boxes,
    draw_annotation_regions,
)
from src.core.dtos.pdf_dtos import PDFDocumentDTO


<<<<<<< HEAD
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
=======
def _card(parent=None) -> QFrame:
    """Creates a light rounded card with a soft shadow and subtle border matching modern dashboard style."""
    f = QFrame(parent)
    f.setObjectName("ViewerCard")
    f.setStyleSheet(
        """
        QFrame#ViewerCard {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
        }
        """
    )
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(16)
    shadow.setColor(QColor(15, 23, 42, 10))
    shadow.setOffset(0, 2)
    f.setGraphicsEffect(shadow)
    return f
>>>>>>> origin/feature/ui-overhaul


class PdfViewerPage(QWidget):
    """
<<<<<<< HEAD
    PDF Viewer screen displaying real PDF drawing pages rendered via PyMuPDF backend,
    with multi-drawing selector dropdown and drawing list sidebar.
=======
    PDF Viewer screen displaying real PDF drawing pages rendered via PyMuPDF backend
    with enterprise drawing context header and AI metadata sidebar matching modern Stitch UI layout.
>>>>>>> origin/feature/ui-overhaul
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
<<<<<<< HEAD
        self._doc_dto: PDFDocumentDTO | None = None
        self._annotation_result = None  # Store annotation detection result
        self._show_annotations = False  # Toggle for annotation visualization
        self._annotation_worker: Optional[AnnotationWorker] = None
        self._zoom         = 1.0
        self._current_page = 1
        self._total_pages  = 1
        self._is_updating_dwg_list = False
=======
        self._doc_dto: Optional[PDFDocumentDTO] = None
        self._annotation_result = None
        self._show_annotations = False
        self._zoom = 1.0
        self._current_page = 1
        self._total_pages = 48

        self.setObjectName("PdfViewerRoot")
        self.setStyleSheet(
            """
            QWidget#PdfViewerRoot {
                background-color: #F8FAFC;
            }
            QLabel {
                background-color: transparent;
            }
            """
        )
>>>>>>> origin/feature/ui-overhaul

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

<<<<<<< HEAD
        # ── Drawing Selector Top Header ───────────────────────────
        dwg_header = QFrame()
        dwg_header.setFixedHeight(42)
        dwg_header.setStyleSheet("background: #1A1C23; border-bottom: 1px solid #2D313A;")
        dh_lay = QHBoxLayout(dwg_header)
        dh_lay.setContentsMargins(16, 0, 16, 0)
        dh_lay.setSpacing(12)

        dh_lbl = QLabel("📐 Drawing:")
        dh_lbl.setFont(QFont("Segoe UI Variable", 11, QFont.Weight.Bold))
        dh_lbl.setStyleSheet("color: #38BDF8;")
        dh_lay.addWidget(dh_lbl)

        self._dwg_combo = QComboBox()
        self._dwg_combo.setFixedHeight(30)
        self._dwg_combo.setMinimumWidth(320)
        self._dwg_combo.setStyleSheet("""
            QComboBox {
                background-color: #252830;
                color: #F8FAFC;
                border: 1px solid #333742;
                border-radius: 4px;
                padding: 2px 10px;
                font-family: 'Cascadia Code', 'Segoe UI', monospace;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #252830;
                color: #F8FAFC;
                selection-background-color: #0284C7;
            }
        """)
        self._dwg_combo.currentIndexChanged.connect(self._on_drawing_selected_from_combo)
        dh_lay.addWidget(self._dwg_combo)

        self._dwg_count_lbl = QLabel("0 drawings available")
        self._dwg_count_lbl.setFont(QFont("Segoe UI", 11))
        self._dwg_count_lbl.setStyleSheet("color: #94A3B8;")
        dh_lay.addWidget(self._dwg_count_lbl)

        dh_lay.addStretch()
        root.addWidget(dwg_header)

        # ── Toolbar ───────────────────────────────────────────────
        self._toolbar = PdfToolbar(total_pages=self._total_pages)
        self._toolbar.zoom_in_requested.connect(self._do_zoom_in)
        self._toolbar.zoom_out_requested.connect(self._do_zoom_out)
        self._toolbar.fit_width_requested.connect(self._fit_width)
        self._toolbar.rotate_requested.connect(self._rotate)
        self._toolbar.prev_page_requested.connect(self._prev_page)
        self._toolbar.next_page_requested.connect(self._next_page)
        self._toolbar.page_changed.connect(self._goto_page)
        self._toolbar.show_annotations_toggled.connect(self._toggle_annotations)
        self._toolbar.toggle_sidebar_requested.connect(self.toggle_sidebar)
        root.addWidget(self._toolbar)
=======
        # ── 1. Top Integrated Control Header (Title, Nav & Tools) ────────────
        top_bar = _card()
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(16, 10, 16, 10)
        tb_lay.setSpacing(12)
>>>>>>> origin/feature/ui-overhaul

        # Title & Revision tag
        title_box = QHBoxLayout()
        title_box.setSpacing(8)

        self._lbl_dwg_no = QLabel("S-204")
        self._lbl_dwg_no.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        self._lbl_dwg_no.setStyleSheet("color: #0F172A;")

        self._lbl_dwg_title = QLabel("TYPICAL BEAM-COLUMN MOMENT CONNECTIONS")
        self._lbl_dwg_title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        self._lbl_dwg_title.setStyleSheet("color: #1E293B;")

        self._rev_badge = QLabel("REV 4")
        self._rev_badge.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        self._rev_badge.setStyleSheet(
            "background-color: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; border-radius: 4px; padding: 2px 6px;"
        )

        title_box.addWidget(self._lbl_dwg_no)
        title_box.addWidget(self._lbl_dwg_title)
        title_box.addWidget(self._rev_badge)

        # Sub-info scale / grid
        self._lbl_scale_info = QLabel("Scale: 1/4\" = 1'-0\"  •  Coordinate Grid: Col C4-D6")
        self._lbl_scale_info.setFont(QFont("Inter", 8.5))
        self._lbl_scale_info.setStyleSheet("color: #64748B;")

        left_header = QVBoxLayout()
        left_header.setSpacing(2)
        left_header.addLayout(title_box)
        left_header.addWidget(self._lbl_scale_info)
        tb_lay.addLayout(left_header, 1)

        # Page Switcher Controls
        page_ctrl = QHBoxLayout()
        page_ctrl.setSpacing(4)

        self._btn_prev_page = QPushButton("‹")
        self._btn_prev_page.setFixedSize(28, 28)
        self._btn_prev_page.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; color: #334155; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        self._btn_prev_page.clicked.connect(self._prev_page)

        lbl_pg_tag = QLabel("Page")
        lbl_pg_tag.setFont(QFont("Inter", 8.5))
        lbl_pg_tag.setStyleSheet("color: #64748B;")

        self._lbl_page_num = QLabel("1")
        self._lbl_page_num.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        self._lbl_page_num.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 2px 8px; color: #0F172A;"
        )

        self._lbl_total_pages = QLabel("/ 48")
        self._lbl_total_pages.setFont(QFont("Inter", 9))
        self._lbl_total_pages.setStyleSheet("color: #64748B;")

        self._btn_next_page = QPushButton("›")
        self._btn_next_page.setFixedSize(28, 28)
        self._btn_next_page.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; color: #334155; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        self._btn_next_page.clicked.connect(self._next_page)

        page_ctrl.addWidget(self._btn_prev_page)
        page_ctrl.addWidget(lbl_pg_tag)
        page_ctrl.addWidget(self._lbl_page_num)
        page_ctrl.addWidget(self._lbl_total_pages)
        page_ctrl.addWidget(self._btn_next_page)
        tb_lay.addLayout(page_ctrl)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #E2E8F0;")
        tb_lay.addWidget(sep1)

        # Zoom & Navigation Controls
        zoom_ctrl = QHBoxLayout()
        zoom_ctrl.setSpacing(4)

        self._btn_zoom_out = QPushButton("−")
        self._btn_zoom_out.setFixedSize(28, 28)
        self._btn_zoom_out.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; color: #334155; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        self._btn_zoom_out.clicked.connect(self._do_zoom_out)

        self._lbl_zoom = QLabel("125%")
        self._lbl_zoom.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        self._lbl_zoom.setStyleSheet("color: #334155; min-width: 38px;")
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setFixedSize(28, 28)
        self._btn_zoom_in.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; color: #334155; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        self._btn_zoom_in.clicked.connect(self._do_zoom_in)

        self._btn_fit = QPushButton("⤢")
        self._btn_fit.setToolTip("Fit Width")
        self._btn_fit.setFixedSize(28, 28)
        self._btn_fit.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; color: #334155; font-size: 11px; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        self._btn_fit.clicked.connect(self._fit_width)

        self._btn_rotate = QPushButton("🔄")
        self._btn_rotate.setFixedSize(28, 28)
        self._btn_rotate.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; color: #334155; font-size: 11px; }"
            "QPushButton:hover { background: #F1F5F9; border-color: #94A3B8; }"
        )
        self._btn_rotate.clicked.connect(self._rotate)

        zoom_ctrl.addWidget(self._btn_zoom_out)
        zoom_ctrl.addWidget(self._lbl_zoom)
        zoom_ctrl.addWidget(self._btn_zoom_in)
        zoom_ctrl.addWidget(self._btn_fit)
        zoom_ctrl.addWidget(self._btn_rotate)
        tb_lay.addLayout(zoom_ctrl)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #E2E8F0;")
        tb_lay.addWidget(sep2)

        # Action Tools Alignment (Find, Annotations, OCR)
        action_ctrl = QHBoxLayout()
        action_ctrl.setSpacing(6)

        self._txt_find = QLineEdit()
        self._txt_find.setPlaceholderText("🔍 Find text on sheet...")
        self._txt_find.setFixedHeight(30)
        self._txt_find.setMinimumWidth(180)
        self._txt_find.setStyleSheet(
            "QLineEdit { background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 5px; padding: 0 8px; color: #0F172A; font-size: 11px; }"
            "QLineEdit:focus { background: #FFFFFF; border-color: #0284C7; }"
        )

        self._btn_annot_toggle = QPushButton("⚛ Annotations (4)")
        self._btn_annot_toggle.setFixedHeight(30)
        self._btn_annot_toggle.setCheckable(True)
        self._btn_annot_toggle.setFont(QFont("Inter", 8.5, QFont.Weight.Medium))
        self._btn_annot_toggle.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 5px; padding: 0 10px; color: #0284C7; font-weight: 600; }"
            "QPushButton:checked { background: #E0F2FE; border-color: #0284C7; color: #0369A1; font-weight: bold; }"
            "QPushButton:hover { background: #F0F9FF; }"
        )
        self._btn_annot_toggle.toggled.connect(self._toggle_annotations)

        self._btn_ocr = QPushButton("⚏ OCR Heatmap")
        self._btn_ocr.setFixedHeight(30)
        self._btn_ocr.setFont(QFont("Inter", 8.5, QFont.Weight.Medium))
        self._btn_ocr.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 5px; padding: 0 10px; color: #475569; }"
            "QPushButton:hover { background: #F1F5F9; color: #0F172A; }"
        )

        self._btn_fullscreen = QPushButton("⛶")
        self._btn_fullscreen.setFixedSize(30, 30)
        self._btn_fullscreen.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 5px; color: #475569; font-size: 12px; }"
            "QPushButton:hover { background: #F1F5F9; color: #0F172A; }"
        )

        action_ctrl.addWidget(self._txt_find)
        action_ctrl.addWidget(self._btn_annot_toggle)
        action_ctrl.addWidget(self._btn_ocr)
        action_ctrl.addWidget(self._btn_fullscreen)
        tb_lay.addLayout(action_ctrl)

        root.addWidget(top_bar)

        # ── 2. Main Viewer Area: Canvas + AI Metadata Sidebar ────────────────
        viewer_row = QHBoxLayout()
        viewer_row.setSpacing(12)

<<<<<<< HEAD
        # Left Sidebar: Drawing List Panel
        self._dwg_sidebar = QFrame()
        self._dwg_sidebar.setFixedWidth(230)
        self._dwg_sidebar.setStyleSheet("background: #1E2026; border-right: 1px solid #2D313A;")
        sb_lay = QVBoxLayout(self._dwg_sidebar)
        sb_lay.setContentsMargins(8, 8, 8, 8)
        sb_lay.setSpacing(6)

        self._sb_title = QLabel("PROJECT DRAWINGS")
        self._sb_title.setFont(QFont("Segoe UI Variable", 10, QFont.Weight.Bold))
        self._sb_title.setStyleSheet("color: #64748B; letter-spacing: 0.5px;")
        sb_lay.addWidget(self._sb_title)

        self._dwg_list_widget = QListWidget()
        self._dwg_list_widget.setStyleSheet("""
            QListWidget {
                background: #1A1C23;
                border: 1px solid #2D313A;
                border-radius: 6px;
                color: #E2E8F0;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #262932;
            }
            QListWidget::item:selected {
                background-color: #0284C722;
                color: #38BDF8;
                border-left: 3px solid #38BDF8;
            }
            QListWidget::item:hover {
                background-color: #252830;
            }
        """)
        self._dwg_list_widget.currentRowChanged.connect(self._on_drawing_selected_from_list)
        sb_lay.addWidget(self._dwg_list_widget, 1)

        viewer_row.addWidget(self._dwg_sidebar)
        self._sidebar_manually_toggled = False
        self._dwg_sidebar.hide()

        # Canvas
=======
        # Drawing Canvas Box
        canvas_card = _card()
        canvas_lay = QVBoxLayout(canvas_card)
        canvas_lay.setContentsMargins(1, 1, 1, 1)
        canvas_lay.setSpacing(0)

        # Telemetry & Status Legend Bar
        telem_bar = QFrame()
        telem_bar.setFixedHeight(32)
        telem_bar.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border-bottom: 1px solid #E2E8F0; border-top-left-radius: 7px; border-top-right-radius: 7px; }"
        )
        tb_inner = QHBoxLayout(telem_bar)
        tb_inner.setContentsMargins(12, 0, 12, 0)
        tb_inner.setSpacing(12)

        lbl_engine = QLabel("🟢 CAD VECTOR ACCELERATED (OpenGL 4.6) | 120 FPS")
        lbl_engine.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        lbl_engine.setStyleSheet("color: #16A34A;")

        tb_inner.addWidget(lbl_engine)
        tb_inner.addStretch()

        # Legend badges matching Stitch UI status tags
        leg_appr = QLabel("■ Approved (1)")
        leg_appr.setFont(QFont("Inter", 7.5, QFont.Weight.Medium))
        leg_appr.setStyleSheet("color: #16A34A;")

        leg_warn = QLabel("■ Warning (1)")
        leg_warn.setFont(QFont("Inter", 7.5, QFont.Weight.Medium))
        leg_warn.setStyleSheet("color: #D97706;")

        leg_rev = QLabel("■ Review (1)")
        leg_rev.setFont(QFont("Inter", 7.5, QFont.Weight.Medium))
        leg_rev.setStyleSheet("color: #0284C7;")

        leg_ocr = QLabel("■ Pending OCR (1)")
        leg_ocr.setFont(QFont("Inter", 7.5, QFont.Weight.Medium))
        leg_ocr.setStyleSheet("color: #0D9488;")

        tb_inner.addWidget(leg_appr)
        tb_inner.addWidget(leg_warn)
        tb_inner.addWidget(leg_rev)
        tb_inner.addWidget(leg_ocr)

        canvas_lay.addWidget(telem_bar)

        # Interactive Scene Canvas View (Blueprint CAD pattern backdrop)
>>>>>>> origin/feature/ui-overhaul
        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setStyleSheet(
            "QGraphicsView { border: none; background-color: #F1F5F9; }"
        )
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pm_item = None
        canvas_lay.addWidget(self._view, 1)

        viewer_row.addWidget(canvas_card, 4)

        # Drawing Metadata & AI Sidebar
        meta_card = _card()
        meta_card.setFixedWidth(320)
        meta_lay = QVBoxLayout(meta_card)
        meta_lay.setContentsMargins(14, 14, 14, 14)
        meta_lay.setSpacing(12)

        # Sidebar Header
        sb_hdr = QHBoxLayout()
        sb_title = QLabel("Drawing Metadata & AI")
        sb_title.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        sb_title.setStyleSheet("color: #0F172A;")

        ready_badge = QLabel("READY")
        ready_badge.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        ready_badge.setStyleSheet(
            "background-color: #DCFCE7; color: #15803D; border-radius: 4px; padding: 2px 6px;"
        )

        sb_hdr.addWidget(sb_title)
        sb_hdr.addStretch()
        sb_hdr.addWidget(ready_badge)
        meta_lay.addLayout(sb_hdr)

        # Meta Fields Container wrapped in ScrollArea for responsive sidebar
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; }")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        self._meta_container = QVBoxLayout(scroll_widget)
        self._meta_container.setContentsMargins(0, 0, 0, 0)
        self._meta_container.setSpacing(8)

        self._build_sidebar_fields(
            [
                ("FILE NAME", "HY_Tower_Core_Structural_S101_S140.pdf", True),
                ("FILE SIZE", "142.8 MB", False),
                ("TOTAL PAGES", "48 Sheets", False),
                ("FORMAT", "PDF 1.7 (Vector CAD Print)", False),
                ("SHEET TITLE", "S-204 TYPICAL MOMENT CONNECTIONS", False),
                ("AUTHOR", "Thornton Tomasetti Engineers", False),
                ("DATE MODIFIED", "Oct 24, 2024 14:32 EST", False),
                ("FILE DIGEST", "SHA256: 8f92a17cb2049e...4d9e", True),
            ]
        )

        scroll_area.setWidget(scroll_widget)
        meta_lay.addWidget(scroll_area, 1)

        # AI Diagnostics Section Box
        ai_box = QFrame()
        ai_box.setStyleSheet(
            "QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 10px; }"
        )
        ai_lay = QVBoxLayout(ai_box)
        ai_lay.setContentsMargins(0, 0, 0, 0)
        ai_lay.setSpacing(6)

        ai_hdr = QHBoxLayout()
        lbl_ai_title = QLabel("AI DIAGNOSTICS ENGINE")
        lbl_ai_title.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        lbl_ai_title.setStyleSheet("color: #475569;")
        ai_hdr.addWidget(lbl_ai_title)
        ai_hdr.addStretch()
        ai_lay.addLayout(ai_hdr)

        reg_row = QHBoxLayout()
        lbl_reg_txt = QLabel("Detected Regions")
        lbl_reg_txt.setFont(QFont("Inter", 8.5))
        lbl_reg_txt.setStyleSheet("color: #334155;")
        lbl_reg_val = QLabel("71 Comments")
        lbl_reg_val.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        lbl_reg_val.setStyleSheet("color: #0284C7;")
        reg_row.addWidget(lbl_reg_txt)
        reg_row.addStretch()
        reg_row.addWidget(lbl_reg_val)
        ai_lay.addLayout(reg_row)

        lbl_pipe = QLabel("Detection Pipeline\nYOLOv8-CAD-Annotate + Tesseract-Engine")
        lbl_pipe.setFont(QFont("Inter", 7.5))
        lbl_pipe.setStyleSheet("color: #64748B;")
        ai_lay.addWidget(lbl_pipe)

        conf_row = QHBoxLayout()
        lbl_conf_txt = QLabel("OCR Coverage Confidence")
        lbl_conf_txt.setFont(QFont("Inter", 7.5, QFont.Weight.Medium))
        lbl_conf_txt.setStyleSheet("color: #475569;")
        lbl_conf_val = QLabel("99.1%")
        lbl_conf_val.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        lbl_conf_val.setStyleSheet("color: #16A34A;")
        conf_row.addWidget(lbl_conf_txt)
        conf_row.addStretch()
        conf_row.addWidget(lbl_conf_val)
        ai_lay.addLayout(conf_row)

        conf_bar = QProgressBar()
        conf_bar.setFixedHeight(4)
        conf_bar.setTextVisible(False)
        conf_bar.setValue(99)
        conf_bar.setStyleSheet(
            "QProgressBar { background: #E2E8F0; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: #16A34A; border-radius: 2px; }"
        )
        ai_lay.addWidget(conf_bar)

        meta_lay.addWidget(ai_box)

        # Primary Action Button
        btn_verify = QPushButton("⚡ Run Verification")
        btn_verify.setFixedHeight(34)
        btn_verify.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        btn_verify.setStyleSheet(
            "QPushButton { background: #0284C7; border: none; border-radius: 6px; color: #FFFFFF; }"
            "QPushButton:hover { background: #0369A1; }"
        )
        meta_lay.addWidget(btn_verify)

        viewer_row.addWidget(meta_card)
        root.addLayout(viewer_row, 1)

        # ── 3. Thumbnail Sheet Index Carousel Strip ──────────────────────────
        carousel_card = _card()
        car_lay = QVBoxLayout(carousel_card)
        car_lay.setContentsMargins(10, 8, 10, 8)
        car_lay.setSpacing(4)

        car_hdr = QHBoxLayout()
        lbl_car_title = QLabel("SHEET INDEX CAROUSEL (STRUCTURAL CORE SET)")
        lbl_car_title.setFont(QFont("Inter", 7.5, QFont.Weight.Bold))
        lbl_car_title.setStyleSheet("color: #475569;")

        lbl_car_range = QLabel("Showing Sheets S-201 to S-207")
        lbl_car_range.setFont(QFont("Inter", 7.5))
        lbl_car_range.setStyleSheet("color: #64748B;")

        car_hdr.addWidget(lbl_car_title)
        car_hdr.addStretch()
        car_hdr.addWidget(lbl_car_range)
        car_lay.addLayout(car_hdr)

        self._thumb_strip = self._build_thumbnail_strip()
        car_lay.addWidget(self._thumb_strip)

        root.addWidget(carousel_card)

        self._load_page(1)

    def _build_sidebar_fields(self, items: List[tuple[str, str, bool]]) -> None:
        """Populates structured metadata cards inside the right sidebar."""
        while self._meta_container.count():
            item = self._meta_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for label, val, highlight in items:
            box = QFrame()
            box.setStyleSheet(
                "QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 8px; }"
            )
            b_lay = QVBoxLayout(box)
            b_lay.setContentsMargins(0, 0, 0, 0)
            b_lay.setSpacing(2)

            lbl = QLabel(label)
            lbl.setFont(QFont("Inter", 7, QFont.Weight.Bold))
            lbl.setStyleSheet("color: #64748B;")

            val_lbl = QLabel(val)
            val_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold if highlight else QFont.Weight.Medium))
            val_lbl.setStyleSheet("color: #0284C7;" if highlight else "color: #1E293B;")
            val_lbl.setWordWrap(True)

            b_lay.addWidget(lbl)
            b_lay.addWidget(val_lbl)
            self._meta_container.addWidget(box)


    def set_document(self, doc_dto: PDFDocumentDTO) -> None:
        """Sets the active PDFDocumentDTO and updates header, total pages, metadata, & canvas."""
        self._doc_dto = doc_dto
        self._total_pages = doc_dto.total_pages
        self._current_page = 1
<<<<<<< HEAD
        
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
=======

        self._lbl_dwg_no.setText(doc_dto.title or "S-204")
        self._lbl_dwg_title.setText(doc_dto.file_name)
        self._lbl_total_pages.setText(f"/ {self._total_pages}")
        self._lbl_page_num.setText("1")

        if self._controller and hasattr(self._controller, "annotation_service"):
            try:
                self._annotation_result = self._controller.annotation_service.detect_all_pages(
                    doc_dto.file_path, method="hybrid", filter_template_regions=False
                )
            except Exception as e:
                print(f"⚠ Could not run annotation detection: {e}")
                self._annotation_result = None
>>>>>>> origin/feature/ui-overhaul

        fields = [
            ("FILE NAME", doc_dto.file_name, True),
            ("FILE SIZE", f"{round(doc_dto.file_size_bytes / (1024*1024), 2)} MB", False),
            ("TOTAL PAGES", f"{doc_dto.total_pages} Sheets", False),
            ("FORMAT", "Scanned Image" if doc_dto.is_scanned else "PDF 1.7 (Vector CAD Print)", False),
            ("SHEET TITLE", doc_dto.title or "Engineering Drawing", False),
            ("AUTHOR", doc_dto.author or "Thornton Tomasetti Engineers", False),
            ("FILE DIGEST", f"{doc_dto.file_hash_sha256[:12]}...", True),
        ]
<<<<<<< HEAD
        
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
=======
>>>>>>> origin/feature/ui-overhaul

        if self._annotation_result:
            fields.append(("DETECTED REGIONS", f"{self._annotation_result.total_regions} markup boxes", False))

        self._build_sidebar_fields(fields)
        self._sync_thumbnails()
        self._load_page(1)
        self.reload_drawings()

    def set_sidebar_visible(self, visible: bool) -> None:
        """Set drawing list sidebar visibility and sync toolbar button state."""
        self._dwg_sidebar.setVisible(visible)
        self._toolbar.set_sidebar_button_checked(visible)

    def toggle_sidebar(self) -> None:
        """Toggle drawing list sidebar visibility."""
        self._sidebar_manually_toggled = True
        # Note: in Qt, isVisible() is false if parent isn't shown, so not isHidden() gives the widget's own visibility state
        is_currently_visible = not self._dwg_sidebar.isHidden()
        self.set_sidebar_visible(not is_currently_visible)

    def apply_context_visibility(self) -> None:
        """Apply context-aware visibility based on upload mode (Single vs Batch)."""
        self._sidebar_manually_toggled = False
        is_batch = getattr(self._controller, "active_upload_mode", "SINGLE") == "BATCH"
        batch_ids = getattr(self._controller, "current_batch_drawing_ids", [])
        if is_batch and batch_ids:
            self.set_sidebar_visible(True)
        else:
            self.set_sidebar_visible(False)

    def reload_drawings(self) -> None:
        """Fetch drawings from controller, populate combo box & sidebar list, and highlight current drawing."""
        if not self._controller or self._is_updating_dwg_list:
            return

        self._is_updating_dwg_list = True
        try:
            is_batch = getattr(self._controller, "active_upload_mode", "SINGLE") == "BATCH"
            batch_ids = getattr(self._controller, "current_batch_drawing_ids", [])

            if is_batch and batch_ids:
                drawings = self._controller.get_batch_drawings()
                if not drawings:
                    drawings = self._controller.get_all_drawings()
                    self._sb_title.setText("PROJECT DRAWINGS")
                    self._dwg_count_lbl.setText(f"{len(drawings)} drawings available")
                else:
                    self._sb_title.setText(f"BATCH DRAWINGS ({len(drawings)})")
                    self._dwg_count_lbl.setText(f"{len(drawings)} batch drawings")
                if not self._sidebar_manually_toggled:
                    self.set_sidebar_visible(True)
            else:
                drawings = self._controller.get_all_drawings()
                self._sb_title.setText("PROJECT DRAWINGS")
                self._dwg_count_lbl.setText(f"{len(drawings)} drawings available")
                if not self._sidebar_manually_toggled:
                    self.set_sidebar_visible(False)

            self._dwg_combo.blockSignals(True)
            self._dwg_list_widget.blockSignals(True)

            self._dwg_combo.clear()
            self._dwg_list_widget.clear()

            curr_id = self._controller.current_drawing_id
            target_idx = 0

            for idx, dwg in enumerate(drawings):
                dwg_id = dwg.get("id", "")
                fname = dwg.get("file_name", "Drawing")
                pages = dwg.get("total_pages", 1)
                cmts = dwg.get("comments_count", 0)
                dept = dwg.get("department_name", "General")

                combo_label = f"{fname} ({pages}p, {cmts} cmts)"
                self._dwg_combo.addItem(combo_label, dwg_id)

                item_label = f"📄 {fname}\n    {pages} pages · {cmts} comments ({dept})"
                item = QListWidgetItem(item_label)
                item.setData(Qt.ItemDataRole.UserRole, dwg_id)
                self._dwg_list_widget.addItem(item)

                if dwg_id == curr_id:
                    target_idx = idx

            if drawings:
                self._dwg_combo.setCurrentIndex(target_idx)
                self._dwg_list_widget.setCurrentRow(target_idx)

        finally:
            self._dwg_combo.blockSignals(False)
            self._dwg_list_widget.blockSignals(False)
            self._is_updating_dwg_list = False

    def _on_drawing_selected_from_combo(self, idx: int) -> None:
        if self._is_updating_dwg_list or idx < 0:
            return
        dwg_id = self._dwg_combo.itemData(idx, Qt.ItemDataRole.UserRole)
        if dwg_id and self._controller:
            self._controller.switch_current_drawing(dwg_id)

    def _on_drawing_selected_from_list(self, row: int) -> None:
        if self._is_updating_dwg_list or row < 0:
            return
        item = self._dwg_list_widget.item(row)
        if item:
            dwg_id = item.data(Qt.ItemDataRole.UserRole)
            if dwg_id and self._controller:
                self._controller.switch_current_drawing(dwg_id)

    def reload_comments(self) -> None:
        """Reload page and thumbnails when comments are loaded/updated."""
        self.reload_drawings()
        self._load_page(self._current_page)
        self._sync_thumbnails()

    def _toggle_annotations(self, enabled: bool) -> None:
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

    # ── Thumbnail Strip ──────────────────────────────────────────

    # ── Thumbnail Strip ──────────────────────────────────────────
    def _build_thumbnail_strip(self) -> QListWidget:
        lst = QListWidget()
        lst.setFlow(QListWidget.Flow.LeftToRight)
        lst.setFixedHeight(82)
        lst.setIconSize(QSize(52, 64))
        lst.setViewMode(QListWidget.ViewMode.IconMode)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        lst.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.setStyleSheet(
            """
            QListWidget {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QListWidget::item {
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                margin-right: 8px;
                background: #FFFFFF;
                color: #475569;
                font-size: 10px;
                font-weight: 600;
                padding: 2px;
            }
            QListWidget::item:hover {
                background: #F8FAFC;
                border-color: #94A3B8;
            }
            QListWidget::item:selected {
                border: 2px solid #0284C7;
                background: #F0F9FF;
                color: #0369A1;
            }
            """
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
                    pm = make_page_pixmap(60, 75, comments=page_comments)
            else:
                pm = make_page_pixmap(60, 75, comments=page_comments)

            item = QListWidgetItem(f"S-{201 + i}")
            item.setIcon(QIcon(pm))
            lst.addItem(item)
        if lst.count() > 0:
            lst.setCurrentRow(0)

    def _sync_thumbnails(self) -> None:
        self._populate_thumbs(self._thumb_strip)
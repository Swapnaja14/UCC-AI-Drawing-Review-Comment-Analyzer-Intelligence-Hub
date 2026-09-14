"""
MainWindow — application shell: sidebar + topbar + stacked pages.
Integrates backend AppController with PySide6 GUI screens.

ARCHITECTURE NOTE:
MainWindow is responsible for:
  - Instantiating AppController (the single controller instance)
  - Passing controller=self.controller to every screen that needs DB access
  - Wiring top-level signals between the controller and screens

All screens that display comment data receive the controller through their
constructor. They must NOT instantiate repositories or services themselves.

INTEGRATION NOTE:
When a PDF is loaded (_on_document_loaded), AppController.current_drawing_id
is set to the database DrawingModel.id for the newly loaded drawing. Screens
with a reload_comments() method are called automatically so their data
reflects the newly loaded drawing.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                                QStackedWidget)
from PySide6.QtCore import Qt

from app.components.sidebar         import SidebarNav
from app.components.topbar          import TopBar
from app.components.status_bar      import AppStatusBar
from app.screens.dashboard_screen      import DashboardPage
from app.screens.upload_screen         import UploadPage
from app.screens.pdf_viewer_screen     import PdfViewerPage
from app.screens.comment_viewer_screen import CommentHighlightPage
from app.screens.ocr_results_screen    import OcrResultsPage
from app.screens.classification_screen import ClassificationPage
from app.screens.review_screen         import HumanReviewPage
from app.screens.analytics_screen      import AnalyticsPage
from app.screens.export_screen         import ExportPage
from app.screens.settings_screen       import SettingsPage

from app.controllers.app_controller import AppController

_PAGE_TITLES = [
    "Dashboard",
    "Upload Drawing",
    "PDF Viewer",
    "Comment Highlight Viewer",
    "OCR Results",
    "Classification",
    "Human Review",
    "Dashboard Analytics",
    "Export",
    "Settings",
]


class MainWindow(QMainWindow):
    def __init__(self, theme_manager=None):
        super().__init__()
        self._theme = theme_manager
        self.setWindowTitle("UCC AI Drawing Review Comment Analyzer")
        self.showMaximized()

        # ── Backend Controller Initialization ─────────────────────
        self.controller = AppController(self)

        # ── Central widget ────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)

        h_layout = QHBoxLayout(central)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        # Sidebar
        self._sidebar = SidebarNav()
        self._sidebar.nav_changed.connect(self._navigate)
        h_layout.addWidget(self._sidebar)

        # Content area
        content_area = QWidget()
        content_area.setObjectName("ContentArea")
        v_layout = QVBoxLayout(content_area)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)

        # Top bar
        self._topbar = TopBar()
        self._topbar.theme_toggled.connect(self._on_theme_toggle)
        v_layout.addWidget(self._topbar)

        # Stacked pages
        self._stack = QStackedWidget()
        self.upload_page = UploadPage(controller=self.controller)
        self.pdf_viewer_page = PdfViewerPage(controller=self.controller)
        self.dashboard_page = DashboardPage(controller=self.controller)

        # Connect Upload controller signals to navigate to PDF Viewer
        self.controller.document_loaded_signal.connect(self._on_document_loaded)
        self.upload_page.open_viewer_requested.connect(self._open_pdf_viewer)

        self._pages = [
            self.dashboard_page,
            self.upload_page,
            self.pdf_viewer_page,
            CommentHighlightPage(controller=self.controller),
            OcrResultsPage(controller=self.controller),
            ClassificationPage(controller=self.controller),
            HumanReviewPage(controller=self.controller),
            AnalyticsPage(controller=self.controller),
            ExportPage(controller=self.controller),
            SettingsPage(theme_manager=self._theme),
        ]
        for page in self._pages:
            self._stack.addWidget(page)
        v_layout.addWidget(self._stack, 1)

        h_layout.addWidget(content_area, 1)

        # ── Status bar ────────────────────────────────────────────
        self._status_bar = AppStatusBar(version="v1.0.0 — Backend Connected")
        self.setStatusBar(self._status_bar)

    def _navigate(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._topbar.set_breadcrumb(_PAGE_TITLES[idx])
        page = self._pages[idx]
        # Auto-refresh the target page so it always shows the latest DB state
        if hasattr(page, "reload_data"):
            page.reload_data()
        elif hasattr(page, "reload_comments"):
            page.reload_comments()
        page.setFocus()

    def _open_pdf_viewer(self):
        self._navigate(2)
        self._sidebar.set_page(2)

    def _on_theme_toggle(self):
        if self._theme:
            self._theme.toggle()

    def _on_document_loaded(self, doc_dto):
        """Callback when background PDF worker completes loading document.

        INTEGRATION NOTE:
        At this point AppController.current_drawing_id is already set to the
        DrawingModel.id for the loaded PDF. Comment screens that implement
        reload_comments() can be called here to refresh their data.
        """
        self._status_bar.set_message(f"Loaded: {doc_dto.file_name} ({doc_dto.total_pages} pages)")
        # Update PDF Viewer page with loaded document
        self.pdf_viewer_page.set_document(doc_dto)
        # Refresh comment screens with DB data for the newly loaded drawing
        for page in self._pages:
            if hasattr(page, "reload_comments"):
                page.reload_comments()
        # Navigate to PDF Viewer screen (Index 2)
        self._open_pdf_viewer()

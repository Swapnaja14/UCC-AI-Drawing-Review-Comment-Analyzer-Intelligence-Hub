"""
pdf_toolbar.py — Redesigned PDF viewer toolbar with zoom, fit, rotate, and page navigation.

Provides:
    PdfToolbar(QFrame)
        Self-contained 54px horizontal toolbar with fine-grained signals.
"""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QLabel, QToolButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from app.components.toolbar import make_toolbar_btn, ToolbarSeparator


class PdfToolbar(QFrame):
    """
    Horizontal toolbar for the PDF viewer.
    Signals
    -------
    zoom_in_requested()
    zoom_out_requested()
    fit_width_requested()
    rotate_requested()
    prev_page_requested()
    next_page_requested()
    page_changed(int)
        Emitted (1-indexed) when the user edits the page number field.
    toggle_sidebar_requested()
        Emitted when the user clicks the Drawings toggle button.
    """

    zoom_in_requested   = Signal()
    zoom_out_requested  = Signal()
    fit_width_requested = Signal()
    rotate_requested    = Signal()
    prev_page_requested = Signal()
    next_page_requested = Signal()
    page_changed        = Signal(int)
    show_annotations_toggled = Signal(bool)
    toggle_sidebar_requested = Signal()

    def __init__(self, total_pages: int = 1, parent=None):
        super().__init__(parent)
        self._total_pages = total_pages

        self.setFixedHeight(54)
        self.setObjectName("Card")
        self.setStyleSheet(
            "#Card { background: #1E2235; border-radius: 0; border-left: none;"
            " border-right: none; border-top: none; border-bottom: 1px solid #2E3654; }"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(6)

        # ── Zoom controls ─────────────────────────────────────────
        zoom_out_btn = make_toolbar_btn("−", "Zoom Out")
        zoom_out_btn.setFixedSize(36, 36)
        zoom_out_btn.clicked.connect(self.zoom_out_requested)
        lay.addWidget(zoom_out_btn)

        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setFixedWidth(60)
        self._zoom_lbl.setFixedHeight(30)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_lbl.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        self._zoom_lbl.setStyleSheet(
            "color: #3B82F6; background: rgba(59, 130, 246, 0.12); border-radius: 6px;"
        )
        lay.addWidget(self._zoom_lbl)

        zoom_in_btn = make_toolbar_btn("+", "Zoom In")
        zoom_in_btn.setFixedSize(36, 36)
        zoom_in_btn.clicked.connect(self.zoom_in_requested)
        lay.addWidget(zoom_in_btn)

        lay.addWidget(ToolbarSeparator())

        fit_btn = make_toolbar_btn("⊡", "Fit Page to Screen")
        fit_btn.setFixedSize(36, 36)
        fit_btn.clicked.connect(self.fit_width_requested)
        lay.addWidget(fit_btn)

        rot_btn = make_toolbar_btn("↻", "Rotate Drawing 90°")
        rot_btn.setFixedSize(36, 36)
        rot_btn.clicked.connect(self.rotate_requested)
        lay.addWidget(rot_btn)

        lay.addWidget(ToolbarSeparator())

        # ── Annotation toggle ─────────────────────────────────────
        self._annot_btn = make_toolbar_btn("🔍", "Toggle AI Annotations Layer")
        self._annot_btn.setCheckable(True)
        self._annot_btn.setChecked(False)
        self._annot_btn.setFixedHeight(36)
        self._annot_btn.setText("  Markup Layer  ")
        self._annot_btn.clicked.connect(lambda: self.show_annotations_toggled.emit(self._annot_btn.isChecked()))
        lay.addWidget(self._annot_btn)

        lay.addWidget(ToolbarSeparator())

        # ── Sidebar toggle ────────────────────────────────────────
        self._toggle_sidebar_btn = QToolButton()
        self._toggle_sidebar_btn.setText("📁 Drawings")
        self._toggle_sidebar_btn.setToolTip("Toggle Drawings Sidebar (Show / Hide)")
        self._toggle_sidebar_btn.setFixedHeight(34)
        self._toggle_sidebar_btn.setMinimumWidth(95)
        self._toggle_sidebar_btn.setCheckable(True)
        self._toggle_sidebar_btn.setChecked(False)
        self._toggle_sidebar_btn.setStyleSheet("""
            QToolButton {
                background-color: #252830;
                color: #E2E8F0;
                border: 1px solid #333742;
                border-radius: 6px;
                padding: 0 10px;
                font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #2D313A;
                border-color: #38BDF8;
                color: #38BDF8;
            }
            QToolButton:checked {
                background-color: #0284C725;
                border-color: #38BDF8;
                color: #38BDF8;
            }
        """)
        self._toggle_sidebar_btn.clicked.connect(self.toggle_sidebar_requested)
        lay.addWidget(self._toggle_sidebar_btn)

        lay.addWidget(ToolbarSeparator())
        lay.addStretch()

        # ── Page navigation ───────────────────────────────────────
        prev_btn = make_toolbar_btn("◀", "Previous Sheet")
        prev_btn.setFixedSize(36, 36)
        prev_btn.clicked.connect(self.prev_page_requested)
        lay.addWidget(prev_btn)

        self._page_field = QLineEdit("1")
        self._page_field.setFixedWidth(46)
        self._page_field.setFixedHeight(32)
        self._page_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_field.setFont(QFont("Cascadia Code", 12, QFont.Weight.Bold))
        self._page_field.setStyleSheet(
            "QLineEdit { background: #161925; border: 1px solid #2E3654; border-radius: 6px; color: #E2E8F0; }"
        )
        self._page_field.editingFinished.connect(self._on_page_edited)
        lay.addWidget(self._page_field)

        self._page_total_lbl = QLabel(f"of {total_pages}")
        self._page_total_lbl.setFont(QFont("Inter", 13, QFont.Weight.Medium))
        self._page_total_lbl.setStyleSheet("color: #9CA3AF; padding: 0 4px;")
        lay.addWidget(self._page_total_lbl)

        next_btn = make_toolbar_btn("▶", "Next Sheet")
        next_btn.setFixedSize(36, 36)
        next_btn.clicked.connect(self.next_page_requested)
        lay.addWidget(next_btn)

    # ── Public API ────────────────────────────────────────────────

    def set_zoom_label(self, pct: int) -> None:
        self._zoom_lbl.setText(f"{pct}%")

    def set_current_page(self, page: int) -> None:
        self._page_field.setText(str(page))

    def set_total_pages(self, total: int) -> None:
        self._total_pages = total
        self._page_total_lbl.setText(f"of {total}")

    def set_sidebar_button_checked(self, checked: bool) -> None:
        """Update the checked state of the toggle sidebar button."""
        self._toggle_sidebar_btn.blockSignals(True)
        self._toggle_sidebar_btn.setChecked(checked)
        self._toggle_sidebar_btn.blockSignals(False)

    # ── Private ───────────────────────────────────────────────────

    def _on_page_edited(self) -> None:
        try:
            page = int(self._page_field.text())
            page = max(1, min(page, self._total_pages))
        except ValueError:
            page = 1
        self._page_field.setText(str(page))
        self.page_changed.emit(page)

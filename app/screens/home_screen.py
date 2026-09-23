"""
home_screen.py — Home / Welcome landing screen.

Provides:
    HomeScreen(QWidget)
        Application landing page with a hero header and a grid of
        quick-action tiles.  Emits ``navigate_requested(int)`` with the
        target sidebar page index when a tile is clicked.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QFrame)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


# ── Quick-action tile ─────────────────────────────────────────────────────────

class _QuickActionTile(QFrame):
    """Clickable card that highlights on hover."""

    clicked = Signal()

    def __init__(self, icon: str, title: str, desc: str,
                 color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color = color

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 28))
        lay.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI Variable", 14, QFont.Weight.DemiBold))
        lay.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("SubCaption")
        desc_lbl.setWordWrap(True)
        lay.addWidget(desc_lbl)

    def enterEvent(self, e) -> None:
        self.setStyleSheet(
            f"#Card {{ border: 1px solid {self._color}40;"
            f" background-color: {self._color}0A; border-radius:8px; }}"
        )
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self.setStyleSheet("")
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        self.clicked.emit()
        super().mousePressEvent(e)


# ── Tile data: (icon, title, description, accent, sidebar page index) ─────────

_QUICK_ACTIONS = [
    ("📂", "Upload Drawing",   "Import a PDF drawing for analysis",       "#3B82F6", 1),
    ("🔍", "PDF Viewer",       "Open and inspect engineering drawings",    "#ADC6FF", 2),
    ("🏷",  "Review Comments", "Approve, reject, or flag OCR results",    "#4EDEA3", 6),
    ("📊", "Analytics",        "Explore trends and category breakdowns",   "#FFB95F", 7),
    ("📤", "Export Report",    "Export reviewed data to Excel / PDF",      "#FB923C", 8),
    ("⚙",  "Settings",         "Manage application preferences",           "#C2C6D6", 9),
]


# ── HomeScreen ────────────────────────────────────────────────────────────────

class HomeScreen(QWidget):
    """
    Welcome landing screen with a hero header and quick-action tiles.

    Signals
    -------
    navigate_requested : int
        Emitted with the target sidebar page index when a tile is clicked.
    """

    navigate_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(32)

        # ── Hero header ───────────────────────────────────────────
        greet = QLabel("Welcome to UCC Analyzer")
        greet.setFont(QFont("Inter", 28, QFont.Weight.Bold))
        root.addWidget(greet)

        sub = QLabel(
            "AI-powered engineering drawing review and comment analysis platform."
        )
        sub.setObjectName("SubCaption")
        sub.setFont(QFont("Inter", 14))
        root.addWidget(sub)

        # ── Section label ─────────────────────────────────────────
        tiles_lbl = QLabel("Quick Actions")
        tiles_lbl.setFont(QFont("Inter", 17, QFont.Weight.DemiBold))
        tiles_lbl.setObjectName("CardHeader")
        tiles_lbl.setObjectName("CardHeader")
        root.addWidget(tiles_lbl)

        # ── Tile grid (2 rows × 3 cols) ───────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        row2 = QHBoxLayout()
        row2.setSpacing(16)

        for i, (icon, title, desc, color, page_idx) in enumerate(_QUICK_ACTIONS):
            tile = _QuickActionTile(icon, title, desc, color)
            tile.clicked.connect(
                lambda idx=page_idx: self.navigate_requested.emit(idx)
            )
            (row1 if i < 3 else row2).addWidget(tile, 1)

        root.addLayout(row1)
        root.addLayout(row2)
        root.addStretch()
